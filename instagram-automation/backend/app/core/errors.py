"""Domain errors. The API layer maps these to clear HTTP responses."""

from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "app_error"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class InvalidTransitionError(ConflictError):
    code = "invalid_status_transition"


class DuplicatePublishError(ConflictError):
    code = "duplicate_publish"


class PermissionDenied(AppError):
    status_code = 403
    code = "forbidden"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class ExternalServiceError(AppError):
    """A third-party service (LLM, image API, Instagram, Google) failed."""

    status_code = 502
    code = "external_service_error"

    def __init__(self, message: str, *, service: str, transient: bool = False, details: dict | None = None):
        super().__init__(message, details=details)
        self.service = service
        self.transient = transient


class LLMError(ExternalServiceError):
    code = "llm_error"

    def __init__(self, message: str, *, transient: bool = False, details: dict | None = None):
        super().__init__(message, service="llm", transient=transient, details=details)


class ImageGenerationError(ExternalServiceError):
    code = "image_generation_error"

    def __init__(self, message: str, *, transient: bool = False, details: dict | None = None):
        super().__init__(message, service="image_generation", transient=transient, details=details)


class SheetsError(ExternalServiceError):
    code = "google_sheets_error"

    def __init__(self, message: str, *, transient: bool = False, details: dict | None = None):
        super().__init__(message, service="google_sheets", transient=transient, details=details)


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
