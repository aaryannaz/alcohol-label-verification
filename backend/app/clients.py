from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv
from google import genai

from .errors import AppError


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=BACKEND_DIR / ".env")

GEMINI_MODEL = "gemini-2.5-flash-lite"


@lru_cache
def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise AppError(
            status_code=500,
            code="MISSING_GEMINI_API_KEY",
            message="GEMINI_API_KEY is not configured.",
            details={"hint": "Add GEMINI_API_KEY to backend/.env or the deployment environment."},
        )
    return genai.Client(api_key=api_key)
