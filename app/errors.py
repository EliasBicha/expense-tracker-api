"""Domain errors raised by services and mapped to the error envelope in main.py.

Services raise these instead of HTTPException so they stay free of HTTP concerns.
"""

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class InvalidInputError(AppError):
    """Validation that can't be expressed in a Pydantic schema (e.g. cross-field query checks)."""

    status_code = 422
    code = "validation_error"

    def __init__(self, field: str, message: str):
        super().__init__(message, details=[{"field": field, "message": message}])
