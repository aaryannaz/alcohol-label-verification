"""Security hardening for the public, billing-attached API.

Provides per-IP rate limiting and optional bearer-token auth for the
cost-bearing endpoints, baseline security response headers, and a global
request-body size cap. All are configurable via environment variables so the
prototype stays open by default but can be locked down for a real deployment.
"""

import os
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .errors import AppError

# If set, the cost-bearing endpoints require `Authorization: Bearer <token>`.
API_TOKEN = os.getenv("APP_API_TOKEN")

# Per-IP sliding-window rate limit. Set RATE_LIMIT_REQUESTS=0 to disable.
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

# Total request-body ceiling (bytes). Default allows two 10 MB files + overhead.
MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", str(25 * 1024 * 1024)))

# Interactive docs default on for local dev; set ENABLE_DOCS=false in production.
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "true").lower() == "true"

# Explicit CORS allowlist (comma-separated). Empty => same-origin only.
CORS_ALLOW_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if origin.strip()]

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "  # blob: for the in-page label image preview
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "  # self-hosted USWDS fonts (Public Sans, Merriweather)
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


# In-memory request log per client IP. Single-instance only; a multi-instance
# deployment should back this with a shared store (e.g. Redis).
_request_log: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    """FastAPI dependency: throttle a client IP to RATE_LIMIT_REQUESTS per window."""
    if RATE_LIMIT_REQUESTS <= 0:
        return
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    log = _request_log[_client_ip(request)]
    while log and log[0] < cutoff:
        log.popleft()
    if len(log) >= RATE_LIMIT_REQUESTS:
        raise AppError(
            status_code=429,
            code="RATE_LIMITED",
            message="Too many requests. Please slow down and try again shortly.",
            details={"limit": RATE_LIMIT_REQUESTS, "window_seconds": RATE_LIMIT_WINDOW_SECONDS},
        )
    log.append(now)


def require_api_token(request: Request) -> None:
    """FastAPI dependency: require a bearer token when APP_API_TOKEN is set."""
    if not API_TOKEN:
        return
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header[:7].lower() == "bearer " else ""
    if token != API_TOKEN:
        raise AppError(
            status_code=401,
            code="UNAUTHORIZED",
            message="Missing or invalid API token.",
            details={},
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"error": {
                            "code": "REQUEST_TOO_LARGE",
                            "message": "Request body is too large.",
                            "details": {"max_bytes": MAX_REQUEST_BYTES},
                        }},
                    )
            except ValueError:
                pass
        return await call_next(request)
