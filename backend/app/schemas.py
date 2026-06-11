"""Pydantic request models and the product-category / origin enums. LabelFields
is generated from the canonical field list in fields.py."""

from enum import Enum

from pydantic import BaseModel, create_model

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
LabelFields = create_model(
    "LabelFields",
    __base__=BaseModel,
    **{key: (str, "") for key in FIELD_KEYS},
)


class VerifyReviewedRequest(BaseModel):
    product_category: ProductCategory
    origin_type: OriginType
    expected: LabelFields
    reviewed: LabelFields
