"""The application error type plus the exception handlers that render every
failure (AppError, request-validation, HTTP, and unexpected) into one JSON
envelope, with a correlation request id."""

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .observability import current_request_id

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def _envelope(status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    error = {"code": code, "message": message, "details": details or {}}
    request_id = current_request_id()
    if request_id and request_id != "-":
        error["request_id"] = request_id  # correlate the client error with server logs
    return JSONResponse(status_code=status_code, content={"error": error})


async def app_error_handler(request: Request, exc: AppError):
    return _envelope(exc.status_code, exc.code, exc.message, exc.details)


async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Pydantic/FastAPI request validation. Reshape the default {detail:[...]} into
    # the standard {error:{...}} envelope so clients have one contract to parse.
    errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()]
    return _envelope(422, "VALIDATION_ERROR", "Request validation failed.", {"errors": errors})


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return _envelope(exc.status_code, "HTTP_ERROR", message)


async def unhandled_exception_handler(request: Request, exc: Exception):
    # Last-resort catch-all: log the traceback server-side, return a generic
    # envelope (never leak internals) so the client always gets a parseable body.
    logger.exception("Unhandled error processing %s %s", request.method, request.url.path)
    return _envelope(500, "INTERNAL_ERROR", "An unexpected error occurred.")
