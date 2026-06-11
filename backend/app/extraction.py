"""Gemini Vision label-field extraction: the prompt plus one or more image/PDF
parts in, a canonical LabelFields dict out — with retries, JSON-mode parsing, and
a response schema scoped to the product category."""

import asyncio
import json
import logging
import os
import re
import time
from functools import lru_cache

from fastapi import UploadFile
from google.genai import types
from pydantic import BaseModel, create_model

from .clients import GEMINI_MODEL, get_gemini_client
from .errors import AppError
from .fields import fields_for_category
from .prompts import COLA_EXTRACTION_PROMPT, EXTRACTION_PROMPT
from .schemas import LabelFields
from .uploads import read_validated_upload

try:  # 4xx client errors (bad key/model/request) will not succeed on retry.
    from google.genai.errors import ClientError
except Exception:  # pragma: no cover - guard against SDK layout changes
    ClientError = ()


logger = logging.getLogger(__name__)

# Retry behaviour is configurable so it can be tuned to the deployment's request
# timeout (e.g. a short budget on serverless). Backoff is exponential.
MAX_ATTEMPTS = int(os.getenv("GEMINI_MAX_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = float(os.getenv("GEMINI_RETRY_BACKOFF_SECONDS", "1.0"))

@lru_cache
def _generation_config(product_category=None):
    """Build the generation config for a product category. Constraining the
    response schema to only the applicable fields (a beer never asks for the
    wine/spirits fields) keeps the model focused and avoids the extraction
    quality loss seen when asking for all 22 fields at once. Temperature 0 keeps
    extraction reproducible since it feeds a field-by-field comparison."""
    keys = fields_for_category(product_category) if product_category else list(LabelFields.model_fields)
    scoped_model = create_model(
        "LabelFieldsScoped",
        __base__=BaseModel,
        **{key: (str, "") for key in keys},
    )
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=scoped_model,
        temperature=0,
        # Reading a label is a perception/transcription task, not a reasoning one,
        # so disable the model's "thinking" phase. On gemini-2.5-flash this cuts
        # latency from ~7s to ~2s with no accuracy loss — the stakeholder bar is
        # ~5s per label (see the brief), and thinking blows past it for no gain.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

# "Imported"/"Domestic" describe origin, not class/type, so strip a leading one
# from class_type as a backstop to the prompt rule (prompts.py).
_ORIGIN_PREFIX = re.compile(r"(?i)^(imported|domestic)\s+")

# A string-typed response schema means the model cannot emit JSON null for an
# absent field; it tends to emit one of these literals instead. Treat them as "".
_NULLISH = {"null", "none", "n/a", "na", "not applicable", "not specified", "not provided", "not present"}

# Defensive cap so a pathological model response can't bloat the payload.
_MAX_FIELD_LENGTH = 4000


def _strip_json_fence(raw_output: str) -> str:
    if raw_output.startswith("```json"):
        return raw_output.replace("```json", "").replace("```", "").strip()
    if raw_output.startswith("```"):
        return raw_output.replace("```", "").strip()
    return raw_output


def _generate_content(contents, config):
    return get_gemini_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=config,
    )


def _coerce_fields(extracted: dict) -> dict:
    """Normalise the raw model output into exactly the LabelFields key set.

    Collapses missing keys / null / non-string values to "" so downstream
    validation sees one consistent shape, and drops any unexpected keys the
    model may have returned.
    """
    cleaned = {}
    for name in LabelFields.model_fields:
        value = extracted.get(name)
        if value is None:
            cleaned[name] = ""
        elif isinstance(value, str):
            cleaned[name] = "" if value.strip().lower() in _NULLISH else value[:_MAX_FIELD_LENGTH]
        else:
            cleaned[name] = str(value)[:_MAX_FIELD_LENGTH]

    fields = LabelFields.model_validate(cleaned).model_dump()

    if fields["class_type"]:
        fields["class_type"] = _ORIGIN_PREFIX.sub("", fields["class_type"]).strip()

    return fields


def build_contents(uploads):
    """Build the Gemini `contents` list from the prompt plus one or more
    (bytes, mime_type) image/PDF parts, in front-then-back order."""
    contents = [EXTRACTION_PROMPT]
    for data, mime_type in uploads:
        contents.append(types.Part.from_bytes(data=data, mime_type=mime_type))
    return contents


async def _run_and_parse(contents, config) -> dict:
    """Call Gemini with retries and return the parsed raw JSON object. Shared by
    label and COLA extraction; callers coerce the dict into their target shape."""
    last_error = None
    start = time.monotonic()

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = await asyncio.to_thread(_generate_content, contents, config)
            break
        except AppError:
            raise
        except ClientError as exc:
            # Bad key / model / request — retrying cannot help, so surface now.
            logger.warning("Gemini rejected the request: %s", exc)
            raise AppError(
                status_code=502,
                code="GEMINI_CLIENT_ERROR",
                message="Gemini rejected the request.",
                details={},
            ) from exc
        except Exception as exc:
            last_error = exc
            logger.warning("Gemini extraction attempt %s/%s failed: %s", attempt + 1, MAX_ATTEMPTS, exc)
            if attempt + 1 < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))
    else:
        logger.error("Gemini extraction failed after %s attempts: %s", MAX_ATTEMPTS, last_error)
        raise AppError(
            status_code=502,
            code="GEMINI_API_FAILURE",
            message=f"Gemini extraction failed after {MAX_ATTEMPTS} attempts.",
            details={},
        )

    logger.info("Gemini extraction succeeded in %.0f ms (attempt %s/%s)",
                (time.monotonic() - start) * 1000, attempt + 1, MAX_ATTEMPTS)
    raw_output = _strip_json_fence((response.text or "").strip())

    if not raw_output:
        logger.error("Gemini returned an empty response")
        raise AppError(
            status_code=502,
            code="GEMINI_EMPTY_RESPONSE",
            message="Gemini returned an empty response.",
            details={},
        )

    try:
        extracted = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        logger.error("Gemini returned non-JSON output: %s", raw_output[:500])
        raise AppError(
            status_code=502,
            code="GEMINI_INVALID_JSON",
            message="Gemini returned a response that could not be parsed as JSON.",
            details={},
        ) from exc

    if not isinstance(extracted, dict):
        logger.error("Gemini returned JSON of the wrong shape: %s", raw_output[:500])
        raise AppError(
            status_code=502,
            code="GEMINI_INVALID_SCHEMA",
            message="Gemini returned JSON, but not the expected object shape.",
            details={},
        )

    return extracted


async def run_extraction(contents, config=None) -> dict:
    """Label extraction: call Gemini and coerce into the canonical LabelFields
    shape. Shared by the API and the eval harness so both exercise the identical
    extraction path. `config` scopes the response schema to a product category;
    defaults to all fields."""
    if config is None:
        config = _generation_config(None)
    return _coerce_fields(await _run_and_parse(contents, config))


async def extract_label_fields(front_image: UploadFile, back_image: UploadFile | None = None, product_category: str | None = None) -> dict:
    front_upload = await read_validated_upload(front_image, "front_image")
    uploads = [(front_upload.data, front_upload.mime_type)]

    if back_image is not None:
        back_upload = await read_validated_upload(back_image, "back_image")
        uploads.append((back_upload.data, back_upload.mime_type))

    return await run_extraction(build_contents(uploads), _generation_config(product_category))


# --- COLA application extraction -------------------------------------------------
# The COLA form states the product type and source, so we don't know the category
# up front: the response schema includes product_category + origin_type alongside
# the label-field keys, and the result is mapped back to canonical enum values.

_COLA_CATEGORY_MAP = {
    "wine": "wine",
    "distilled spirits": "distilled_spirits",
    "distilled_spirits": "distilled_spirits",
    "spirits": "distilled_spirits",
    "malt beverage": "malt_beverage",
    "malt_beverage": "malt_beverage",
    "malt": "malt_beverage",
    "beer": "malt_beverage",
}
_COLA_ORIGIN_MAP = {"domestic": "domestic", "imported": "imported"}


@lru_cache
def _cola_generation_config():
    """Generation config for reading a COLA form: the schema adds product_category
    and origin_type to the label-field keys so the form's own type/source boxes
    drive the category and origin selection."""
    keys = list(LabelFields.model_fields)
    scoped_model = create_model(
        "ColaFieldsScoped",
        __base__=BaseModel,
        product_category=(str, ""),
        origin_type=(str, ""),
        **{key: (str, "") for key in keys},
    )
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=scoped_model,
        temperature=0,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )


def _coerce_cola(raw: dict) -> dict:
    """Split the raw COLA response into {product_category, origin_type, fields},
    mapping the form's type/source strings to canonical enum values (None when
    unrecognised, so the UI keeps its current selection)."""
    category = _COLA_CATEGORY_MAP.get((raw.get("product_category") or "").strip().lower())
    origin = _COLA_ORIGIN_MAP.get((raw.get("origin_type") or "").strip().lower())
    return {
        "product_category": category,
        "origin_type": origin,
        "fields": _coerce_fields(raw),
    }


async def extract_cola_fields(cola_file: UploadFile) -> dict:
    """Extract the application's stated values from an uploaded COLA form."""
    upload = await read_validated_upload(cola_file, "cola_file")
    contents = [COLA_EXTRACTION_PROMPT, types.Part.from_bytes(data=upload.data, mime_type=upload.mime_type)]
    raw = await _run_and_parse(contents, _cola_generation_config())
    return _coerce_cola(raw)
