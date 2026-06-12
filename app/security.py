"""Security hardening for the public, billing-attached API.

Provides per-IP rate limiting and optional bearer-token auth for the
cost-bearing endpoints, baseline security response headers, and a global
request-body size cap. All are configurable via environment variables so the
prototype stays open by default but can be locked down for a real deployment.
"""

import hmac
import ipaddress
import math
import os
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .errors import AppError, _envelope

# If set, the cost-bearing endpoints require `Authorization: Bearer <token>`.
API_TOKEN = os.getenv("APP_API_TOKEN")

# Per-IP sliding-window rate limit. Set RATE_LIMIT_REQUESTS=0 to disable.
# Sized for the brief's 200-300-label batch (each label is one /verify call):
# 120/min lets a paced client clear a full batch in ~2-3 minutes — the frontend
# paces on the 429 Retry-After header — while still capping what one IP can
# spend per minute. Override with RATE_LIMIT_REQUESTS.
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "120"))
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
    "frame-src 'self' blob:; "  # blob: for the in-page PDF preview iframe (app.js)
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "  # self-hosted USWDS fonts (Public Sans, Merriweather)
    "object-src 'none'; "
    "frame-ancestors 'none'; "  # who may embed US (frame-src is who WE may embed)
    "base-uri 'self'; "
    "form-action 'self'"
)


# In-memory request log per client IP. Single-instance only; a multi-instance
# deployment should back this with a shared store (e.g. Redis).
_request_log: dict[str, deque] = defaultdict(deque)

# Hard cap on distinct tracked identifiers. Without it, a client cycling
# X-Forwarded-For values would pin a dict entry per spoofed value forever.
_MAX_TRACKED_IDENTIFIERS = 10_000


def _client_ip(request: Request) -> str:
    # Use the RIGHT-most syntactically valid X-Forwarded-For entry: that hop is
    # appended by the nearest proxy (Vercel sets it from the connection), while
    # everything left of it is client-supplied and trivially spoofable — keying
    # the rate limit on it would let a client mint a fresh bucket per request.
    forwarded = request.headers.get("x-forwarded-for", "")
    for candidate in reversed(forwarded.split(",")):
        try:
            return str(ipaddress.ip_address(candidate.strip()))
        except ValueError:
            continue
    return request.client.host if request.client else "unknown"


def _evict_stale_identifiers(cutoff: float) -> None:
    """Bound _request_log: drop identifiers whose entries have all aged out of
    the window, then — if still over the cap — evict the stalest (oldest
    most-recent request) until back at the cap. Keeps a spoofed-identifier
    flood from growing memory without bound."""
    for identifier in [ip for ip, log in _request_log.items() if not log or log[-1] < cutoff]:
        del _request_log[identifier]
    overflow = len(_request_log) - _MAX_TRACKED_IDENTIFIERS
    if overflow > 0:
        for identifier in sorted(_request_log, key=lambda ip: _request_log[ip][-1])[:overflow]:
            del _request_log[identifier]


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
        # Retry-After = seconds until the oldest logged request leaves the
        # window, i.e. the earliest moment a retry can succeed. The frontend's
        # batch pacing keys off this header.
        retry_after = max(1, math.ceil(log[0] - cutoff))
        raise AppError(
            status_code=429,
            code="RATE_LIMITED",
            message="Too many requests. Please slow down and try again shortly.",
            details={
                "limit": RATE_LIMIT_REQUESTS,
                "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
    log.append(now)
    if len(_request_log) > _MAX_TRACKED_IDENTIFIERS:
        _evict_stale_identifiers(cutoff)


def require_api_token(request: Request) -> None:
    """FastAPI dependency: require a bearer token when APP_API_TOKEN is set."""
    if not API_TOKEN:
        return
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header[:7].lower() == "bearer " else ""
    # Constant-time comparison so the token can't be recovered byte-by-byte
    # from response-timing differences.
    if not hmac.compare_digest(token.encode(), API_TOKEN.encode()):
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


class MaxBodySizeMiddleware:
    """Cap the request body at MAX_REQUEST_BYTES (pure ASGI).

    An over-cap declared Content-Length is rejected before any body is read.
    Bodies without a trustworthy Content-Length (chunked / streamed) are
    counted as they arrive and cut off at the cap mid-stream, so omitting the
    header does not bypass the cap. Raw ASGI rather than BaseHTTPMiddleware so
    the receive channel can be wrapped without buffering the body; the 413 is
    sent directly from here (FastAPI converts any exception raised during its
    body parse into a generic 400, so raising through the app would lose the
    status and code).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > MAX_REQUEST_BYTES:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass  # malformed header: fall through to counted enforcement

        received = 0
        rejected = False
        response_started = False

        async def bounded_receive():
            nonlocal received, rejected
            if rejected:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_REQUEST_BYTES:
                    rejected = True
                    if not response_started:
                        await self._reject(scope, receive, send)
                    # Report the client as disconnected so the app unwinds
                    # instead of waiting on body bytes we will not deliver.
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            nonlocal response_started
            if rejected:
                return  # the 413 already went out; drop the aborted app's response
            response_started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, guarded_send)
        except Exception:
            # The app may abort while unwinding from the synthetic disconnect;
            # the 413 already went out, so don't cascade into a 500.
            if not rejected:
                raise

    @staticmethod
    async def _reject(scope, receive, send):
        # Built via errors._envelope so the 413 carries the standard error
        # envelope — including the request id — like every other failure.
        response = _envelope(413, "REQUEST_TOO_LARGE", "Request body is too large.", {"max_bytes": MAX_REQUEST_BYTES})
        await response(scope, receive, send)
