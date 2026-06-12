"""FastAPI application: routes, exception handlers, middleware, and app wiring."""

import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .classify import classify_category, classify_origin
from .clients import GEMINI_MODEL
from .errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from .extraction import extract_label_fields
from .fields import field_specs_payload
from .observability import RequestIdMiddleware, configure_logging
from .schemas import OriginType, ProductCategory, VerifyReviewedRequest
from .security import (
    CORS_ALLOW_ORIGINS,
    ENABLE_DOCS,
    MaxBodySizeMiddleware,
    SecurityHeadersMiddleware,
    rate_limit,
    require_api_token,
)
from .validation import compute_label_checks, get_field_requirements, get_wine_path, validate_label_fields

configure_logging()

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Alcohol Label Verification API",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MaxBodySizeMiddleware)
if CORS_ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
# Added last so it is the outermost middleware: the request ID is set before any
# other middleware runs and is available to every handler and log record.
app.add_middleware(RequestIdMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Throttle + optionally authenticate the endpoints that do real work / cost money.
COST_GUARDS = [Depends(rate_limit), Depends(require_api_token)]


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/how-to", include_in_schema=False)
async def how_to():
    return FileResponse(STATIC_DIR / "how-to.html")


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz():
    # Readiness without calling Gemini: just verify the key is configured, so a
    # misconfigured deploy is caught before a reviewer's first upload.
    ready = bool(os.getenv("GEMINI_API_KEY"))
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "model": GEMINI_MODEL},
    )


def build_verification_response(product_category: str, origin_type: str, expected: dict, reviewed: dict) -> dict:
    validation = validate_label_fields(product_category, origin_type, expected, reviewed)
    field_requirements = get_field_requirements(product_category, origin_type)

    wine_path = None
    if product_category == ProductCategory.wine.value:
        wine_path = get_wine_path(origin_type, reviewed.get("alcohol_content"))

    return {
        "product_category": product_category,
        "origin_type": origin_type,
        "wine_path": wine_path,
        "field_requirements": field_requirements,
        "validation": validation,
        "compliance_checks": compute_label_checks(product_category, origin_type, reviewed),
        "expected": expected,
        "reviewed": reviewed,
    }


@app.get("/fields")
async def fields():
    return {"fields": field_specs_payload()}


@app.get("/field-requirements")
async def field_requirements(product_category: ProductCategory, origin_type: OriginType):
    return {
        "product_category": product_category.value,
        "origin_type": origin_type.value,
        "field_requirements": get_field_requirements(product_category.value, origin_type.value),
    }


@app.post("/extract", dependencies=COST_GUARDS)
async def extract(
    product_category: str = Form("auto"),
    origin_type: str = Form("auto"),
    front_image: UploadFile = File(...),
    back_image: UploadFile | None = File(default=None),
):
    """Extract the label fields. Like /verify, accepts "auto" for the category
    and origin: the label is read with the all-fields schema and both are
    inferred from the result, so the single-label flow needs no manual picks."""
    auto_category = product_category not in _CATEGORY_VALUES
    auto_origin = origin_type not in _ORIGIN_VALUES

    extracted = await extract_label_fields(
        front_image, back_image, None if auto_category else product_category
    )
    category = classify_category(extracted) if auto_category else product_category
    origin = classify_origin(extracted) if auto_origin else origin_type

    return {
        "product_category": category,
        "origin_type": origin,
        "detected_category": category,
        "detected_origin": origin,
        "extracted": extracted,
    }


_CATEGORY_VALUES = {c.value for c in ProductCategory}
_ORIGIN_VALUES = {o.value for o in OriginType}


@app.post("/verify", dependencies=COST_GUARDS)
async def verify(
    product_category: str = Form("auto"),
    origin_type: str = Form("auto"),
    front_image: UploadFile = File(...),
    back_image: UploadFile | None = File(default=None),
):
    """Extract a label and validate it in one call. Expected and reviewed are both
    seeded from the same extraction, so this is a completeness + statutory-warning +
    label-compliance check. Used by batch mode to give each row a real verdict in
    a single Gemini call, keeping the per-file request count (and rate-limit
    footprint) the same as a bare /extract.

    Auto-detect: when product_category / origin_type are "auto" (anything not a
    known value), the label is read with the all-fields schema and its category
    and origin are inferred from the result, so batch rows need no manual picks.
    """
    auto_category = product_category not in _CATEGORY_VALUES
    auto_origin = origin_type not in _ORIGIN_VALUES

    # A known category scopes the extraction to its fields; "auto" reads them all.
    extracted = await extract_label_fields(
        front_image, back_image, None if auto_category else product_category
    )
    category = classify_category(extracted) if auto_category else product_category
    origin = classify_origin(extracted) if auto_origin else origin_type

    response = build_verification_response(
        product_category=category,
        origin_type=origin,
        expected=extracted,
        reviewed=extracted,
    )
    response["detected_category"] = category
    response["detected_origin"] = origin
    return response


@app.post("/verify-reviewed", dependencies=COST_GUARDS)
async def verify_reviewed(request: VerifyReviewedRequest):
    expected = request.expected.model_dump()
    reviewed = request.reviewed.model_dump()

    return build_verification_response(
        product_category=request.product_category.value,
        origin_type=request.origin_type.value,
        expected=expected,
        reviewed=reviewed,
    )
