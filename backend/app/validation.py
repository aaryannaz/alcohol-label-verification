import re


EXPECTED_WARNING = """
GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects.

(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.
"""
EXPECTED_WARNING_HEADING = "GOVERNMENT WARNING:"

FIELD_ORDER = (
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "government_warning",
    "domestic_name_address",
    "importer_name_address",
    "country_of_origin",
    "sulfite_declaration",
    "appellation_of_origin",
    "fanciful_name",
)

COMMON_REQUIRED_FIELDS = (
    "brand_name",
    "class_type",
    "net_contents",
    "government_warning",
)

PRODUCT_REQUIRED_FIELDS = {
    "malt_beverage": (),
    "distilled_spirits": ("alcohol_content",),
    "wine": ("alcohol_content",),
}

PRODUCT_CONDITIONAL_FIELDS = {
    "malt_beverage": ("alcohol_content", "sulfite_declaration", "fanciful_name"),
    "distilled_spirits": ("sulfite_declaration", "fanciful_name"),
    "wine": ("sulfite_declaration", "appellation_of_origin", "fanciful_name"),
}

ORIGIN_REQUIRED_FIELDS = {
    "domestic": ("domestic_name_address",),
    "imported": ("importer_name_address", "country_of_origin"),
}


def normalize(value):
    if value is None:
        return ""

    value = value.lower()
    value = value.replace("company", "co")
    value = value.replace("illinois", "il")
    value = value.replace("virginia", "va")
    value = value.replace("sulphites", "sulfites")
    value = value.replace("fluid ounces", "fl oz")
    value = value.replace("fluid ounce", "fl oz")
    value = value.replace("alc/vol", "")
    value = value.replace("abv", "")
    value = value.replace("alcohol by volume", "")
    value = value.replace("alcoholbyvolume", "")
    value = value.replace("produced in", "")
    value = value.replace("product of", "")
    value = value.replace("made in", "")
    value = value.replace("imported from", "")
    value = value.replace("country of origin", "")
    value = value.replace("\n", "")
    value = value.replace(",", "")
    value = value.replace(".", "")
    value = value.replace(":", "")
    value = value.replace("(", "")
    value = value.replace(")", "")
    value = value.replace(" ", "")

    return value.strip()


def check_match(expected, actual):
    if normalize(expected) == normalize(actual):
        return "PASS"
    return "FAIL"


def check_optional(expected, reviewed):
    if expected and expected.strip():
        return check_match(expected, reviewed)
    return "NOT REQUIRED"


def normalize_warning_spacing(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def check_government_warning(actual):
    actual_warning = normalize_warning_spacing(actual)
    if not actual_warning:
        return "MISSING"

    expected_warning = normalize_warning_spacing(EXPECTED_WARNING)

    if actual_warning == expected_warning:
        return "PASS"

    if EXPECTED_WARNING_HEADING not in actual_warning:
        if "government warning" in actual_warning.lower():
            return "FAIL_HEADING_FORMAT"
        return "FAIL_MISSING_HEADING"

    return "FAIL_TEXT_MISMATCH"


def parse_abv(value):
    if not value:
        return None

    value = value.replace("%", "").strip()

    try:
        return float(value)
    except ValueError:
        return None


def get_wine_path(origin_type: str, alcohol_content: str):
    abv = parse_abv(alcohol_content)

    if abv is None:
        return "wine_abv_unknown"

    if origin_type == "domestic" and abv < 7:
        return "domestic_wine_under_7"

    if origin_type == "imported" and abv < 7:
        return "imported_wine_under_7"

    if origin_type == "domestic" and abv >= 7:
        return "domestic_wine_7_or_more"

    if origin_type == "imported" and abv >= 7:
        return "imported_wine_7_or_more"

    return "wine_path_unknown"


def check_required(expected, reviewed):
    if not expected or not expected.strip():
        return "EXPECTED VALUE MISSING"

    if not reviewed or not reviewed.strip():
        return "MISSING"

    return check_match(expected, reviewed)


def _ordered_unique(fields):
    return [field for field in FIELD_ORDER if field in set(fields)]


def get_field_requirements(product_category: str, origin_type: str) -> dict:
    required = _ordered_unique(
        COMMON_REQUIRED_FIELDS
        + PRODUCT_REQUIRED_FIELDS[product_category]
        + ORIGIN_REQUIRED_FIELDS[origin_type]
    )
    conditional = _ordered_unique(PRODUCT_CONDITIONAL_FIELDS[product_category])
    optional = [
        field
        for field in FIELD_ORDER
        if field not in set(required) and field not in set(conditional)
    ]

    return {
        "required": required,
        "conditional": conditional,
        "optional": optional,
    }


def _validate_by_requirements(product_category: str, origin_type: str, expected: dict, reviewed: dict) -> dict:
    requirements = get_field_requirements(product_category, origin_type)
    required_fields = set(requirements["required"])
    validation = {}

    for field in FIELD_ORDER:
        if field == "government_warning":
            validation[field] = check_government_warning(reviewed.get(field))
        elif field in required_fields:
            validation[field] = check_required(expected.get(field), reviewed.get(field))
        else:
            validation[field] = check_optional(expected.get(field), reviewed.get(field))

    return validation


def validate_malt_beverage(expected: dict, reviewed: dict, origin_type: str) -> dict:
    return _validate_by_requirements("malt_beverage", origin_type, expected, reviewed)


def validate_distilled_spirits(expected: dict, reviewed: dict, origin_type: str) -> dict:
    return _validate_by_requirements("distilled_spirits", origin_type, expected, reviewed)


def validate_wine(expected: dict, reviewed: dict, origin_type: str) -> dict:
    return _validate_by_requirements("wine", origin_type, expected, reviewed)


def validate_fields(expected: dict, reviewed: dict) -> dict:
    return validate_malt_beverage(expected, reviewed, "domestic")


def validate_label_fields(product_category: str, origin_type: str, expected: dict, reviewed: dict) -> dict:
    if product_category == "malt_beverage":
        return validate_malt_beverage(expected, reviewed, origin_type)
    if product_category == "distilled_spirits":
        return validate_distilled_spirits(expected, reviewed, origin_type)
    if product_category == "wine":
        return validate_wine(expected, reviewed, origin_type)
    raise ValueError(f"Unsupported product category: {product_category}")
