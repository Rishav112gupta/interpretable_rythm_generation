from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import auth, config_routes, integrations, planning, posts
from app.core.config import settings
from app.core.errors import AppError, ExternalServiceError
from app.core.logging import configure_logging, redact

configure_logging(settings.log_level)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems = settings.validate_for_production()
    if problems:
        for p in problems:
            logger.error("Configuration error: %s", p)
        raise RuntimeError("Refusing to start in production with insecure configuration: " + " ".join(problems))
    if settings.app_env != "test":
        from app.database.session import SessionLocal
        from app.seed import seed

        try:
            with SessionLocal() as db:
                seed(db)
        except SQLAlchemyError:
            logger.exception("Database not ready for seeding - did you run 'alembic upgrade head'?")
    mode = {
        "llm": settings.effective_llm_provider,
        "image": settings.effective_image_provider,
        "instagram": "MOCK" if settings.mock_instagram else "REAL",
        "sheets": "MOCK" if settings.mock_google_sheets else ("on" if settings.google_sheets_enabled else "off"),
    }
    logger.info("Starting %s (%s) providers=%s", settings.app_name, settings.app_env, mode)
    yield


app = FastAPI(
    title="Instagram Automation API",
    version="1.0.0",
    description="AI-assisted Instagram content planning, approval, scheduling and publishing (official Meta APIs only).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    body = {"error": exc.code, "detail": redact(exc.message), "details": exc.details}
    if isinstance(exc, ExternalServiceError):
        body["service"] = exc.service
        body["transient"] = exc.transient
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    summary = "; ".join(f"{e['field']}: {e['message']}" for e in errors[:5])
    return JSONResponse(status_code=422, content={"error": "validation_failed", "detail": f"Invalid input - {summary}", "details": {"errors": errors}})


@app.exception_handler(SQLAlchemyError)
async def db_error_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=503, content={"error": "database_error", "detail": "A database error occurred. The administrator has been notified in the logs."})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "internal_error", "detail": "Unexpected server error. Check the backend logs."})


for r in (auth.router, posts.router, config_routes.router, planning.router, integrations.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health", tags=["health"])
def health():
    from app.database.session import engine

    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "mock_instagram": settings.mock_instagram}


if settings.storage_backend == "local":
    media = Path(settings.media_root)
    media.mkdir(parents=True, exist_ok=True)
    # Public on purpose: Instagram must be able to download post images. File names are random UUIDs.
    app.mount("/media", StaticFiles(directory=str(media)), name="media")
