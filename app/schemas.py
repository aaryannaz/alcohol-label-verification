"""Pydantic request/response models and the product-category / origin enums.
LabelFields is generated from the canonical field list in fields.py."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, create_model

from .fields import FIELD_KEYS


class ProductCategory(str, Enum):
    malt_beverage = "malt_beverage"
    distilled_spirits = "distilled_spirits"
    wine = "wine"


class OriginType(str, Enum):
    domestic = "domestic"
    imported = "imported"


# Generated from the canonical field list in fields.py so the model can never
# drift from FIELD_KEYS. Every field is an optional string defaulting to "".
# Extra keys are forbidden: a misspelled field key must be a 422, not silently
# validate against the defaults and produce a green verdict.
LabelFields = create_model(
    "LabelFields",
    __config__=ConfigDict(extra="forbid"),
    **{key: (str, "") for key in FIELD_KEYS},
)


class VerifyReviewedRequest(BaseModel):
    product_category: ProductCategory
    origin_type: OriginType
    expected: LabelFields
    reviewed: LabelFields


# --- Response models ---------------------------------------------------------
# These document the endpoint contracts in OpenAPI. Each mirrors the runtime
# shape exactly — changing one is an API contract change, not a docs tweak.


class FieldSpecOut(BaseModel):
    """One entry of GET /fields: a UI-facing field spec from fields.FIELD_SPECS."""

    key: str
    label: str
    control: str
    categories: list[str]


class FieldsResponse(BaseModel):
    fields: list[FieldSpecOut]


class FieldRequirements(BaseModel):
    """The required / conditional / optional buckets computed by
    validation.get_field_requirements for one category + origin."""

    required: list[str]
    conditional: list[str]
    optional: list[str]


class FieldRequirementsResponse(BaseModel):
    product_category: ProductCategory
    origin_type: OriginType
    field_requirements: FieldRequirements


class ExtractResponse(BaseModel):
    """POST /extract: the resolved category and origin (detected from the label
    when "auto" was requested, echoed when chosen) plus the extracted fields."""

    product_category: ProductCategory
    origin_type: OriginType
    extracted: LabelFields


class GovernmentWarningStatus(BaseModel):
    """The health warning is checked against the statutory text on the COLA and
    the label independently, so its validation entry is a per-side pair of
    status codes rather than the single string every other field gets."""

    expected: str
    label: str


class ComplianceCheck(BaseModel):
    """One advisory label-only check from validation.compute_label_checks."""

    name: str
    label: str
    status: str
    detail: str


class VerificationResponse(BaseModel):
    """POST /verify and /verify-reviewed: the full verification shape built by
    main.build_verification_response."""

    product_category: ProductCategory
    origin_type: OriginType
    wine_path: str | None
    field_requirements: FieldRequirements
    validation: dict[str, str | GovernmentWarningStatus]
    compliance_checks: list[ComplianceCheck]
    expected: LabelFields
    reviewed: LabelFields


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = {}
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    """The one envelope every failure is rendered into (see errors.py). Declared
    here only so endpoint `responses=` documentation can reference it — the
    runtime envelope is built by the exception handlers, not this model."""

    error: ErrorDetail
