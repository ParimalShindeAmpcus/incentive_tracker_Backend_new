from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, *, details: Optional[Any] = None):
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class DuplicatePaymentError(ConflictError):
    code = "duplicate_payment"

    def __init__(self, message: str = "Incentive line already paid", *, details: Optional[Any] = None):
        super().__init__(message, details=details)


class BlockingValidationError(AppError):
    status_code = 409
    code = "blocking_validation"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
        )

    @app.exception_handler(PermissionError)
    async def permission_handler(_: Request, exc: PermissionError):
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": {"code": "forbidden", "message": str(exc), "details": None},
            },
        )
