"""Domain exceptions and a structured error shape (R5.2)."""
from __future__ import annotations


class AppError(Exception):
    """Base for errors that map to a specific HTTP status and error code."""

    status_code = 400
    code = "app_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class FrozenWeekError(AppError):
    """Attempt to edit a week inside the frozen period (R1.5, R6)."""

    status_code = 409
    code = "frozen_week"
