"""Categories, brand profile, templates and runtime settings."""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import admin, viewer
from app.core.config import settings
from app.core.errors import ValidationFailed
from app.database.session import get_db
from app.models import ContentCategory, IntegrationLog, Template, User
from app.schemas.api import (
    BrandIn,
    BrandOut,
    CategoryIn,
    CategoryOut,
    CategoryUpdate,
    IntegrationLogOut,
    SettingsUpdate,
    TemplateIn,
    TemplateOut,
    TemplateUpdate,
)
from app.services import app_settings
from app.services.content.generation import get_brand
from app.services.image_generation import MockImageProvider
from app.services.scheduling.recurrence import validate_timezone
from app.services.storage import get_storage
from app.services.templates.renderer import RenderContent, load_uploaded_image, render_template

router = APIRouter()


# ------------------------------------------------------------- categories
@router.get("/categories", response_model=list[CategoryOut], tags=["categories"])
def list_categories(include_inactive: bool = False, _: User = Depends(viewer), db: Session = Depends(get_db)):
    stmt = select(ContentCategory).order_by(ContentCategory.sort_order, ContentCategory.id)
    if not include_inactive:
        stmt = stmt.where(ContentCategory.is_active.is_(True))
    return db.scalars(stmt).all()


@router.post("/categories", response_model=CategoryOut, status_code=201, tags=["categories"])
def create_category(body: CategoryIn, _: User = Depends(admin), db: Session = Depends(get_db)):
    if db.scalars(select(ContentCategory).where(ContentCategory.key == body.key)).first():
        raise HTTPException(409, f"Category key {body.key} already exists.")
    cat = ContentCategory(**body.model_dump())
    db.add(cat)
    db.commit()
    return cat


@router.patch("/categories/{cat_id}", response_model=CategoryOut, tags=["categories"])
def update_category(cat_id: int, body: CategoryUpdate, _: User = Depends(admin), db: Session = Depends(get_db)):
    cat = db.get(ContentCategory, cat_id)
    if cat is None:
        raise HTTPException(404, "Category not found.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    db.commit()
    return cat


# ------------------------------------------------------------------ brand
@router.get("/brand", response_model=BrandOut, tags=["brand"])
def read_brand(_: User = Depends(viewer), db: Session = Depends(get_db)):
    brand = get_brand(db)
    db.commit()
    return brand


@router.put("/brand", response_model=BrandOut, tags=["brand"])
def update_brand(body: BrandIn, _: User = Depends(admin), db: Session = Depends(get_db)):
    brand = get_brand(db)
    data = body.model_dump()
    data["knowledge"] = [k for k in data["knowledge"] if k["label"].strip() or k["value"].strip()]
    for k, v in data.items():
        setattr(brand, k, v)
    db.commit()
    return brand


@router.post("/brand/logo", response_model=BrandOut, tags=["brand"])
async def upload_logo(file: UploadFile = File(...), _: User = Depends(admin), db: Session = Depends(get_db)):
    data = await file.read()
    if not data:
        raise ValidationFailed("Empty file.")
    img = load_uploaded_image(data)
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    brand = get_brand(db)
    brand.logo_url = get_storage().save(buf.getvalue(), folder="brand", extension="png", content_type="image/png")
    db.commit()
    return brand


# -------------------------------------------------------------- templates
@router.get("/templates", response_model=list[TemplateOut], tags=["templates"])
def list_templates(_: User = Depends(viewer), db: Session = Depends(get_db)):
    return db.scalars(select(Template).order_by(Template.id)).all()


@router.post("/templates", response_model=TemplateOut, status_code=201, tags=["templates"])
def create_template(body: TemplateIn, _: User = Depends(admin), db: Session = Depends(get_db)):
    if db.scalars(select(Template).where(Template.key == body.key)).first():
        raise HTTPException(409, "Template key already exists.")
    _validate_layout(body.layout)
    t = Template(**body.model_dump())
    db.add(t)
    db.commit()
    return t


@router.patch("/templates/{template_id}", response_model=TemplateOut, tags=["templates"])
def update_template(template_id: int, body: TemplateUpdate, _: User = Depends(admin), db: Session = Depends(get_db)):
    t = db.get(Template, template_id)
    if t is None:
        raise HTTPException(404, "Template not found.")
    data = body.model_dump(exclude_unset=True)
    if "layout" in data:
        _validate_layout(data["layout"])
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    return t


def _validate_layout(layout: dict) -> None:
    elements = layout.get("elements")
    if not isinstance(elements, list):
        raise ValidationFailed("layout.elements must be a list.")
    for i, el in enumerate(elements):
        if el.get("type") not in {"image", "logo", "rect", "text"}:
            raise ValidationFailed(f"Element {i}: type must be image, logo, rect or text.")
        box = el.get("box")
        if box is not None and (not isinstance(box, list) or len(box) != 4):
            raise ValidationFailed(f"Element {i}: box must be [x, y, width, height].")
    try:
        render_template(layout, RenderContent(headline="Preview"), 540, 675)
    except Exception as exc:
        raise ValidationFailed(f"Template cannot be rendered: {exc}") from exc


@router.get("/templates/{template_id}/preview", tags=["templates"], response_class=Response)
def preview_template(template_id: int, _: User = Depends(viewer), db: Session = Depends(get_db)):
    t = db.get(Template, template_id)
    if t is None:
        raise HTTPException(404, "Template not found.")
    brand = get_brand(db)
    logo = None
    if brand.logo_url:
        try:
            logo = get_storage().read(brand.logo_url)
        except Exception:
            logo = None
    content = RenderContent(
        headline="Your headline appears here",
        subtitle="A supporting line for the post",
        cta="Call to action",
        footer=brand.company_name or "Company name",
        category=t.name,
        company=brand.company_name,
        image=MockImageProvider().generate(t.key, width=768, height=1024).data,
        logo=logo,
        tokens={"primary": brand.primary_color, "secondary": brand.secondary_color},
    )
    data = render_template(t.layout, content, t.width, t.height)
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------- settings
@router.get("/settings", tags=["settings"])
def get_app_settings(_: User = Depends(viewer), db: Session = Depends(get_db)):
    return {
        **app_settings.all_settings(db),
        "providers": {
            "llm": settings.effective_llm_provider,
            "llm_model": settings.llm_model or ("claude-opus-5-5" if settings.effective_llm_provider == "anthropic" else ""),
            "image": settings.effective_image_provider,
            "instagram": "mock" if settings.mock_instagram else f"graph ({settings.meta_login_type} login, {settings.meta_graph_api_version})",
            "google_sheets": "mock" if settings.mock_google_sheets else ("enabled" if settings.google_sheets_enabled else "disabled"),
            "storage": settings.storage_backend,
        },
        "mock": {
            "llm": settings.effective_llm_provider == "mock",
            "image_generation": settings.effective_image_provider == "mock",
            "instagram": settings.mock_instagram,
            "google_sheets": settings.mock_google_sheets,
        },
        "public_base_url": settings.public_base_url,
        "app_env": settings.app_env,
    }


@router.patch("/settings", tags=["settings"])
def update_app_settings(body: SettingsUpdate, user: User = Depends(admin), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "timezone" in data and data["timezone"]:
        try:
            validate_timezone(data["timezone"])
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc
    for k, v in data.items():
        if v is not None:
            app_settings.set_setting(db, k, v)
    db.commit()
    return get_app_settings(user, db)


@router.get("/logs", response_model=list[IntegrationLogOut], tags=["settings"])
def list_logs(source: str | None = None, limit: int = 100, _: User = Depends(viewer), db: Session = Depends(get_db)):
    stmt = select(IntegrationLog).order_by(IntegrationLog.id.desc()).limit(min(limit, 500))
    if source:
        stmt = stmt.where(IntegrationLog.source == source)
    return db.scalars(stmt).all()
