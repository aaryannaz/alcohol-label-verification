from enum import Enum

from pydantic import BaseModel


class ProductCategory(str, Enum):
    malt_beverage = "malt_beverage"
    distilled_spirits = "distilled_spirits"
    wine = "wine"


class OriginType(str, Enum):
    domestic = "domestic"
    imported = "imported"


class LabelFields(BaseModel):
    brand_name: str = ""
    class_type: str = ""
    alcohol_content: str = ""
    net_contents: str = ""
    government_warning: str = ""
    domestic_name_address: str = ""
    importer_name_address: str = ""
    country_of_origin: str = ""
    sulfite_declaration: str = ""
    appellation_of_origin: str = ""
    fanciful_name: str = ""


class VerifyReviewedRequest(BaseModel):
    product_category: ProductCategory
    origin_type: OriginType
    expected: LabelFields
    reviewed: LabelFields
