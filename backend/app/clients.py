"""Gemini client construction and model / timeout configuration (env-driven)."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .errors import AppError

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=BACKEND_DIR / ".env")

# Single source of truth for the model id. Override per environment with GEMINI_MODEL.
# Default is gemini-2.5-flash with "thinking" disabled (see extraction.py): it is
# noticeably more accurate than flash-lite on judgment-heavy fields (e.g. fanciful
# names) while still returning in ~2s, under the ~5s stakeholder bar.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Per-request timeout (milliseconds) so a hung Gemini call fails fast instead of
# pinning a worker for the whole retry budget. MUST be >= 10000: the Gemini API
# rejects any client deadline under 10s with 400 INVALID_ARGUMENT ("Manually set
# deadline ... is too short. Minimum allowed deadline is 10s."). A typical
# extraction returns in ~2s, so 12s is a safety cap on a genuine hang, not the
# expected latency. Override with GEMINI_TIMEOUT_MS (do not set below 10000).
GEMINI_TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", "12000"))


def _require_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise AppError(
            status_code=500,
            code="MISSING_GEMINI_API_KEY",
            message="GEMINI_API_KEY is not configured.",
            details={"hint": "Add GEMINI_API_KEY to backend/.env or the deployment environment."},
        )
    return api_key


@lru_cache
def _build_client(api_key: str):
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
    )


def get_gemini_client():
    # Key the cache on the API key value so a rotated key is picked up without a
    # restart, while a stable key still reuses one client. The missing-key check
    # runs first and raises (it is never cached).
    return _build_client(_require_api_key())
