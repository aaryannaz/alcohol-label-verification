import asyncio
import json
import logging

from fastapi import UploadFile
from google.genai import types

from .clients import GEMINI_MODEL, get_gemini_client
from .errors import AppError
from .prompts import EXTRACTION_PROMPT
from .uploads import read_validated_upload


logger = logging.getLogger(__name__)


def _strip_json_fence(raw_output: str) -> str:
    if raw_output.startswith("```json"):
        return raw_output.replace("```json", "").replace("```", "").strip()
    if raw_output.startswith("```"):
        return raw_output.replace("```", "").strip()
    return raw_output


def _generate_content(contents):
    return get_gemini_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
    )


async def extract_label_fields(front_image: UploadFile, back_image: UploadFile | None = None) -> dict:
    front_upload = await read_validated_upload(front_image, "front_image")

    contents = [
        EXTRACTION_PROMPT,
        types.Part.from_bytes(
            data=front_upload.data,
            mime_type=front_upload.mime_type,
        ),
    ]

    if back_image is not None:
        back_upload = await read_validated_upload(back_image, "back_image")
        contents.append(
            types.Part.from_bytes(
                data=back_upload.data,
                mime_type=back_upload.mime_type,
            )
        )

    last_error = None

    for attempt in range(3):
        try:
            response = await asyncio.to_thread(_generate_content, contents)
            break
        except AppError:
            raise
        except Exception as exc:
            last_error = exc
            logger.warning("Gemini extraction attempt %s failed: %s", attempt + 1, exc)
            await asyncio.sleep(5)
    else:
        raise AppError(
            status_code=502,
            code="GEMINI_API_FAILURE",
            message="Gemini extraction failed after 3 attempts.",
            details={"last_error": str(last_error)},
        )

    raw_output = _strip_json_fence((response.text or "").strip())
    logger.info("Received Gemini extraction response")

    if not raw_output:
        raise AppError(
            status_code=502,
            code="GEMINI_EMPTY_RESPONSE",
            message="Gemini returned an empty response.",
            details={"raw_output": raw_output},
        )

    try:
        extracted = json.loads(raw_output)
    except json.JSONDecodeError:
        raise AppError(
            status_code=502,
            code="GEMINI_INVALID_JSON",
            message="Gemini returned a response that could not be parsed as JSON.",
            details={"raw_output": raw_output},
        )

    if not isinstance(extracted, dict):
        raise AppError(
            status_code=502,
            code="GEMINI_INVALID_SCHEMA",
            message="Gemini returned JSON, but not the expected object shape.",
            details={"raw_output": raw_output},
        )

    return extracted
