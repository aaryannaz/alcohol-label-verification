from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .errors import AppError, app_error_handler
from .extraction import extract_label_fields
from .schemas import LabelFields, OriginType, ProductCategory, VerifyReviewedRequest
from .validation import get_field_requirements, get_wine_path, validate_label_fields


STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Alcohol Label Verification API")
app.add_exception_handler(AppError, app_error_handler)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/how-to", include_in_schema=False)
async def how_to():
    return FileResponse(STATIC_DIR / "how-to.html")


def build_expected_fields(
    expected_brand_name: str,
    expected_alcohol_content: str,
    expected_net_contents: str,
    expected_class_type: str,
    expected_domestic_name_address: str,
    expected_importer_name_address: str,
    expected_country_of_origin: str,
    expected_sulfite_declaration: str,
    expected_appellation_of_origin: str,
    expected_fanciful_name: str,
) -> dict:
    return {
        "brand_name": expected_brand_name,
        "class_type": expected_class_type,
        "alcohol_content": expected_alcohol_content,
        "net_contents": expected_net_contents,
        "domestic_name_address": expected_domestic_name_address,
        "importer_name_address": expected_importer_name_address,
        "country_of_origin": expected_country_of_origin,
        "sulfite_declaration": expected_sulfite_declaration,
        "appellation_of_origin": expected_appellation_of_origin,
        "fanciful_name": expected_fanciful_name,
    }


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
        "extracted": reviewed,
        "validation": validation,
    }


@app.get("/field-requirements")
async def field_requirements(product_category: ProductCategory, origin_type: OriginType):
    return {
        "product_category": product_category.value,
        "origin_type": origin_type.value,
        "field_requirements": get_field_requirements(product_category.value, origin_type.value),
    }


@app.post("/extract")
async def extract(
    product_category: ProductCategory = Form(...),
    origin_type: OriginType = Form(...),
    front_image: UploadFile = File(...),
    back_image: UploadFile | None = File(default=None),
):
    extracted = await extract_label_fields(front_image, back_image)

    return {
        "product_category": product_category.value,
        "origin_type": origin_type.value,
        "extracted": extracted,
    }


@app.post("/verify-front")
async def verify_front(
    product_category: ProductCategory = Form(...),
    origin_type: OriginType = Form(...),
    front_image: UploadFile = File(...),
    expected_brand_name: str = Form(...),
    expected_alcohol_content: str = Form(""),
    expected_net_contents: str = Form(...),
    expected_class_type: str = Form(...),
    expected_domestic_name_address: str = Form(""),
    expected_importer_name_address: str = Form(""),
    expected_country_of_origin: str = Form(""),
    expected_sulfite_declaration: str = Form(""),
    expected_appellation_of_origin: str = Form(""),
    expected_fanciful_name: str = Form(""),
):
    return await verify(
        product_category=product_category,
        origin_type=origin_type,
        front_image=front_image,
        back_image=None,
        expected_brand_name=expected_brand_name,
        expected_alcohol_content=expected_alcohol_content,
        expected_net_contents=expected_net_contents,
        expected_class_type=expected_class_type,
        expected_domestic_name_address=expected_domestic_name_address,
        expected_importer_name_address=expected_importer_name_address,
        expected_country_of_origin=expected_country_of_origin,
        expected_sulfite_declaration=expected_sulfite_declaration,
        expected_appellation_of_origin=expected_appellation_of_origin,
        expected_fanciful_name=expected_fanciful_name,
    )


@app.post("/verify")
async def verify(
    product_category: ProductCategory = Form(...),
    origin_type: OriginType = Form(...),
    front_image: UploadFile = File(...),
    back_image: UploadFile | None = File(default=None),
    expected_brand_name: str = Form(...),
    expected_alcohol_content: str = Form(""),
    expected_net_contents: str = Form(...),
    expected_class_type: str = Form(...),
    expected_domestic_name_address: str = Form(""),
    expected_importer_name_address: str = Form(""),
    expected_country_of_origin: str = Form(""),
    expected_sulfite_declaration: str = Form(""),
    expected_appellation_of_origin: str = Form(""),
    expected_fanciful_name: str = Form(""),
):
    extracted = await extract_label_fields(front_image, back_image)

    expected = build_expected_fields(
        expected_brand_name=expected_brand_name,
        expected_alcohol_content=expected_alcohol_content,
        expected_net_contents=expected_net_contents,
        expected_class_type=expected_class_type,
        expected_domestic_name_address=expected_domestic_name_address,
        expected_importer_name_address=expected_importer_name_address,
        expected_country_of_origin=expected_country_of_origin,
        expected_sulfite_declaration=expected_sulfite_declaration,
        expected_appellation_of_origin=expected_appellation_of_origin,
        expected_fanciful_name=expected_fanciful_name,
    )

    return build_verification_response(
        product_category=product_category.value,
        origin_type=origin_type.value,
        expected=expected,
        reviewed=extracted,
    )


@app.post("/verify-reviewed")
async def verify_reviewed(request: VerifyReviewedRequest):
    expected = request.expected.model_dump()
    reviewed = request.reviewed.model_dump()

    response = build_verification_response(
        product_category=request.product_category.value,
        origin_type=request.origin_type.value,
        expected=expected,
        reviewed=reviewed,
    )
    response["expected"] = expected
    response["reviewed"] = reviewed
    return response
