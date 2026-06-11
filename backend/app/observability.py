"""Structured logging and per-request correlation IDs.

Every request gets an ID (propagated from an inbound `X-Request-ID` or generated)
that is attached to log records, returned in the `X-Request-ID` response header,
and included in error responses — so a reviewer's "it failed" maps to a server
log line. Logging is scoped to the `app` logger namespace so it does not fight
with uvicorn's own access/error loggers.
"""

import logging
import os
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    return _request_id.get()


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = _request_id.get()
        return True


def configure_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"))
    app_logger = logging.getLogger("app")
    app_logger.handlers = [handler]
    app_logger.setLevel(level)
    app_logger.propagate = False


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = _request_id.set(request_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
            elapsed_ms = (time.monotonic() - start) * 1000
            response.headers["X-Request-ID"] = request_id
            logging.getLogger("app.access").info(
                "%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, elapsed_ms
            )
            return response
        finally:
            _request_id.reset(token)
