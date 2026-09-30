from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import admin, client_ip, get_current_user
from app.core.config import settings
from app.core.rate_limit import rate_limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.database.session import get_db
from app.models import User
from app.schemas.api import LoginIn, PasswordChange, TokenOut, UserCreate, UserOut, UserUpdate

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    rate_limiter.hit(f"login:{client_ip(request)}", settings.login_rate_limit_per_minute)
    user = db.scalars(select(User).where(func.lower(User.email) == body.email.lower())).first()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled.")
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return TokenOut(access_token=create_access_token(str(user.id), {"role": user.role}), user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/auth/change-password", status_code=204)
def change_password(body: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    user.hashed_password = hash_password(body.new_password)
    db.commit()


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(admin), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, _: User = Depends(admin), db: Session = Depends(get_db)):
    if db.scalars(select(User).where(func.lower(User.email) == body.email.lower())).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists.")
    user = User(email=body.email.lower(), full_name=body.full_name, hashed_password=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, current: User = Depends(admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found.")
    if user.id == current.id and (body.is_active is False or (body.role and body.role != user.role)):
        raise HTTPException(400, "You cannot deactivate yourself or change your own role.")
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.hashed_password = hash_password(body.password)
    db.commit()
    return user
