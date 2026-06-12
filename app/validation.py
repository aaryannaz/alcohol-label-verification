"""Compliance comparison of reviewed label fields against expected COLA values.

Comparison is per-field rather than one global normalizer: text fields use
word-boundary normalization (so a phrase rule meant for one field cannot corrupt
another), alcohol content is compared numerically within a TTB tolerance band,
and net contents is compared by converting to a common unit. Each rule cites the
TTB checklist requirement it supports where applicable.
"""

import re

from .fields import FIELD_KEYS, fields_for_category

EXPECTED_WARNING = """
GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects.

(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.
"""
EXPECTED_WARNING_HEADING = "GOVERNMENT WARNING:"

# Derived from the canonical field list (fields.py) — never hand-maintained.
FIELD_ORDER = FIELD_KEYS

COMMON_REQUIRED_FIELDS = (
    "brand_name",
    "class_type",
    "net_contents",
    "government_warning",
)

PRODUCT_REQUIRED_FIELDS = {
    "malt_beverage": (),
    "distilled_spirits": ("alcohol_content",),
    # Wine ABV is conditional, not required: a 7-14% "table wine"/"light wine"
    # may omit a numeric alcohol statement (27 CFR 4.36(a)).
    "wine": (),
}

# Additive disclosures mandatory only if the additive is used (a formulation
# fact on the COLA, not the label image), so all are conditional.
_ADDITIVE_ALL = ("fdc_yellow_5_declaration", "cochineal_carmine_declaration")

PRODUCT_CONDITIONAL_FIELDS = {
    "malt_beverage": ("alcohol_content", "sulfite_declaration", "fanciful_name")
    + _ADDITIVE_ALL + ("aspartame_declaration",),
    "distilled_spirits": ("sulfite_declaration", "fanciful_name")
    + _ADDITIVE_ALL
    + ("statement_of_age", "commodity_statement", "coloring_materials",
       "wood_treatment", "state_of_distillation"),
    "wine": ("alcohol_content", "sulfite_declaration", "appellation_of_origin", "fanciful_name")
    + _ADDITIVE_ALL
    + ("grape_varietal", "percentage_of_foreign_wine"),
}

ORIGIN_REQUIRED_FIELDS = {
    "domestic": ("domestic_name_address",),
    "imported": ("importer_name_address", "country_of_origin"),
}

# These address / country fields are origin-specific, not merely origin-required:
# a field that isn't required for the selected origin isn't applicable to it at
# all (a domestic product has no importer or country-of-origin; an imported
# product has no domestic bottler). Derived from ORIGIN_REQUIRED_FIELDS so the
# two can't drift. Cross-origin values that DO appear on the label are still
# surfaced by the origin-consistency check in compute_label_checks().
ORIGIN_SCOPED_FIELDS = {
    field: tuple(origin for origin, fields in ORIGIN_REQUIRED_FIELDS.items() if field in fields)
    for field in set().union(*ORIGIN_REQUIRED_FIELDS.values())
}

ADDRESS_FIELDS = {"domestic_name_address", "importer_name_address"}

# Fail fast if a requirement matrix references a field that is not in the
# canonical list (e.g. a typo or a renamed field).
_KNOWN_FIELDS = set(FIELD_KEYS)
for _group in (
    COMMON_REQUIRED_FIELDS,
    *PRODUCT_REQUIRED_FIELDS.values(),
    *PRODUCT_CONDITIONAL_FIELDS.values(),
    *ORIGIN_REQUIRED_FIELDS.values(),
    ADDRESS_FIELDS,
):
    _unknown = set(_group) - _KNOWN_FIELDS
    assert not _unknown, f"validation references unknown fields: {_unknown}"

# USPS state / territory name -> abbreviation. Folded so a label that abbreviates
# and a COLA that spells out (or vice versa) compare equal on name/address fields.
STATE_ABBREVIATIONS = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
    "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv",
    "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm", "new york": "ny",
    "north carolina": "nc", "north dakota": "nd", "ohio": "oh", "oklahoma": "ok",
    "oregon": "or", "pennsylvania": "pa", "rhode island": "ri",
    "south carolina": "sc", "south dakota": "sd", "tennessee": "tn", "texas": "tx",
    "utah": "ut", "vermont": "vt", "virginia": "va", "washington": "wa",
    "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
    "district of columbia": "dc", "puerto rico": "pr",
}

# Country name synonyms -> a single canonical token for country_of_origin.
COUNTRY_SYNONYMS = {
    "united states of america": "us", "united states": "us", "usa": "us",
    "u s a": "us", "u s": "us", "us": "us", "america": "us",
    "united kingdom": "uk", "uk": "uk", "u k": "uk", "great britain": "uk",
    "britain": "uk", "england": "uk",
}

# Lead phrases that introduce a responsible party but are not part of the
# name/address itself (the bottler name + city/state are what matter).
ADDRESS_LEAD_PHRASES = (
    "brewed and bottled by", "produced and bottled by", "vinted and bottled by",
    "bottled and packed by", "brewed by", "bottled by", "produced by",
    "distilled by", "packed by", "imported by", "made by", "vinted by",
)

# Lead phrases for country of origin (e.g. "Product of Australia" -> "Australia").
ORIGIN_LEAD_PHRASES = (
    "country of origin", "product of", "produce of", "produced in",
    "made in", "imported from", "brewed in", "distilled in",
)

# Wine designation tokens (lowercase) used as conditional triggers.
# Table/light wine (27 CFR 4.36(a)) may omit a numeric ABV statement.
TABLE_WINE_DESIGNATION_TOKENS = ("table wine", "light wine")
# A semi-generic type, varietal, vintage, or "estate bottled" makes the
# appellation of origin mandatory (27 CFR 4.25/4.34).
SEMI_GENERIC_WINE_TYPES = (
    "burgundy", "claret", "chablis", "champagne", "chianti", "malaga", "marsala",
    "madeira", "moselle", "port", "rhine wine", "hock", "sauterne", "haut sauterne",
    "sherry", "tokay",
)
ESTATE_BOTTLED_TOKENS = ("estate bottled",)

# Volume unit -> millilitres, for net-contents comparison.
UNIT_TO_ML = {
    "ml": 1.0, "milliliter": 1.0, "millilitre": 1.0,
    "cl": 10.0, "centiliter": 10.0, "centilitre": 10.0,
    "l": 1000.0, "liter": 1000.0, "litre": 1000.0,
    "fl oz": 29.5735, "fluid ounce": 29.5735,
    "pt": 473.176, "pint": 473.176,
    "qt": 946.353, "quart": 946.353,
    "gal": 3785.41, "gallon": 3785.41,
}

_METRIC_UNIT_ROOTS = {"ml", "milliliter", "millilitre", "cl", "centiliter", "centilitre", "l", "liter", "litre"}
_CUSTOMARY_UNIT_ROOTS = {"fl oz", "fluid ounce", "pt", "pint", "qt", "quart", "gal", "gallon"}

# Approved metric standards of fill (millilitres). These tables change by
# regulation; the check is advisory and tells the reviewer to confirm against
# the current CFR. Wine: 27 CFR 4.72 (plus even-litre sizes >= 4 L). Distilled
# spirits: 27 CFR 5.203.
WINE_STANDARDS_OF_FILL_ML = {
    50, 100, 180, 187, 200, 250, 300, 330, 355, 360, 375, 473, 500, 550, 568,
    600, 620, 700, 720, 750, 1000, 1500, 1800, 2250, 3000,
}
DS_STANDARDS_OF_FILL_ML = {
    50, 100, 187, 200, 250, 331, 350, 355, 375, 475, 500, 570, 700, 710, 720,
    750, 900, 945, 1000, 1500, 1750, 1800, 2000, 3000, 3750,
}

# Per-category labeling tolerance on stated alcohol content (percentage points).
# Wine: 27 CFR 4.36 (1.5% at/above 14% ABV, 0.75% for table wine below 14%).
# Distilled spirits: 27 CFR 5.65 (0.3%). Malt beverage: 27 CFR 7.71 (0.3%).
ABV_TOLERANCE_DISTILLED_SPIRITS = 0.3
ABV_TOLERANCE_MALT_BEVERAGE = 0.3
ABV_TOLERANCE_WINE_TABLE = 0.75
ABV_TOLERANCE_WINE = 1.5

# Relative tolerance on net contents to absorb rounding between unit systems.
NET_CONTENTS_REL_TOLERANCE = 0.01


def _normalize_basic(value):
    """Lowercase, fold '&', drop apostrophes, turn separating punctuation into
    spaces, and collapse whitespace — preserving token order and boundaries."""
    if not value:
        return ""

    value = value.lower()
    value = value.replace("&", " and ")
    value = value.replace("'", "").replace("’", "")
    # Replace anything that is not a word char, percent, slash, or hyphen with a
    # space. Periods (abbreviation dots) become spaces too; numeric fields are
    # handled separately so decimal points are never destroyed here.
    value = re.sub(r"[^\w%/-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _fold_company(value):
    value = re.sub(r"\bcompany\b", "co", value)
    value = re.sub(r"\bincorporated\b", "inc", value)
    value = re.sub(r"\bcorporation\b", "corp", value)
    return value


def _strip_lead_phrases(value, phrases):
    for phrase in phrases:
        value = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _apply_map(value, mapping):
    for source, target in mapping.items():
        value = re.sub(r"\b" + re.escape(source) + r"\b", target, value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_field(field, value):
    """Per-field text normalization. Phrase/abbreviation rules apply only to the
    fields they belong to so they cannot corrupt unrelated fields."""
    normalized = _normalize_basic(value)

    if field in ADDRESS_FIELDS:
        normalized = _strip_lead_phrases(normalized, ADDRESS_LEAD_PHRASES)
        normalized = _apply_map(normalized, STATE_ABBREVIATIONS)
        normalized = _fold_company(normalized)
    elif field == "country_of_origin":
        normalized = _strip_lead_phrases(normalized, ORIGIN_LEAD_PHRASES)
        normalized = _apply_map(normalized, COUNTRY_SYNONYMS)
    elif field == "sulfite_declaration":
        normalized = normalized.replace("sulphite", "sulfite")
    elif field in ADDRESS_FIELDS or field in ("brand_name", "class_type", "fanciful_name"):
        normalized = _fold_company(normalized)

    return normalized


def parse_abv(value):
    """Extract an alcohol-by-volume percentage from a free-text statement.

    Prefers an explicit '...%' figure; falls back to a proof figure (proof / 2);
    otherwise the first number. Returns None if nothing plausible is found.
    """
    if not value:
        return None

    text = value.lower()

    percent = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if percent:
        number = float(percent.group(1))
    else:
        proof = re.search(r"(\d+(?:\.\d+)?)\s*proof", text)
        if proof:
            number = float(proof.group(1)) / 2.0
        else:
            first = re.search(r"\d+(?:\.\d+)?", text)
            if not first:
                return None
            number = float(first.group(0))

    if 0 <= number <= 100:
        return number
    return None


def _match_volume(value):
    """Return (quantity, unit_token) parsed from a net-contents statement, or None."""
    if not value:
        return None

    text = value.lower()
    text = re.sub(r"fl\.?\s*oz\.?", "fl oz", text)
    text = re.sub(r"fluid\s+ounces?", "fl oz", text)

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*"
        r"(fl oz|milliliters?|millilitres?|centiliters?|centilitres?|"
        r"liters?|litres?|gallons?|quarts?|pints?|ml|cl|l|gal|qt|pt)\b",
        text,
    )
    if not match:
        return None
    return float(match.group(1)), match.group(2)


def parse_volume(value):
    """Parse a net-contents statement into millilitres, or None if unparseable."""
    matched = _match_volume(value)
    if matched is None:
        return None
    quantity, unit = matched
    factor = UNIT_TO_ML.get(unit) or UNIT_TO_ML.get(unit.rstrip("s"))
    if factor is None:
        return None
    return quantity * factor


def net_contents_unit_system(value):
    """Return 'metric', 'customary', or None for a net-contents statement."""
    matched = _match_volume(value)
    if matched is None:
        return None
    unit = matched[1]
    root = unit.rstrip("s")
    if unit in _METRIC_UNIT_ROOTS or root in _METRIC_UNIT_ROOTS:
        return "metric"
    if unit in _CUSTOMARY_UNIT_ROOTS or root in _CUSTOMARY_UNIT_ROOTS:
        return "customary"
    return None


def is_approved_standard_of_fill(product_category, milliliters):
    """True/False if the volume is an approved standard of fill, or None when the
    category has no enumerated standard (malt beverage)."""
    if milliliters is None:
        return None
    ml = round(milliliters)
    if product_category == "wine":
        if ml in WINE_STANDARDS_OF_FILL_ML:
            return True
        return ml >= 4000 and ml % 1000 == 0  # 4 L or larger in even litres
    if product_category == "distilled_spirits":
        return ml in DS_STANDARDS_OF_FILL_ML
    return None


def _abv_tolerance(product_category, expected_abv):
    if product_category == "wine":
        return ABV_TOLERANCE_WINE if expected_abv >= 14 else ABV_TOLERANCE_WINE_TABLE
    if product_category == "distilled_spirits":
        return ABV_TOLERANCE_DISTILLED_SPIRITS
    if product_category == "malt_beverage":
        return ABV_TOLERANCE_MALT_BEVERAGE
    return 0.0


def match_alcohol_content(product_category, expected, reviewed):
    expected_abv = parse_abv(expected)
    reviewed_abv = parse_abv(reviewed)

    if expected_abv is None or reviewed_abv is None:
        # Fall back to a plain text comparison if either side is unparseable.
        return "PASS" if _normalize_basic(expected) == _normalize_basic(reviewed) else "FAIL"

    tolerance = _abv_tolerance(product_category, expected_abv)
    return "PASS" if abs(expected_abv - reviewed_abv) <= tolerance else "FAIL"


def match_net_contents(expected, reviewed):
    expected_ml = parse_volume(expected)
    reviewed_ml = parse_volume(reviewed)

    if expected_ml is None or reviewed_ml is None:
        return "PASS" if _normalize_basic(expected) == _normalize_basic(reviewed) else "FAIL"

    if expected_ml == 0 and reviewed_ml == 0:
        return "PASS"

    tolerance = max(expected_ml, reviewed_ml) * NET_CONTENTS_REL_TOLERANCE
    return "PASS" if abs(expected_ml - reviewed_ml) <= tolerance else "FAIL"


def match_field(field, product_category, expected, reviewed):
    if field == "alcohol_content":
        return match_alcohol_content(product_category, expected, reviewed)
    if field == "net_contents":
        return match_net_contents(expected, reviewed)
    return "PASS" if normalize_field(field, expected) == normalize_field(field, reviewed) else "FAIL"


def check_required(field, product_category, expected, reviewed):
    if not expected or not expected.strip():
        return "EXPECTED VALUE MISSING"
    if not reviewed or not reviewed.strip():
        return "MISSING"
    return match_field(field, product_category, expected, reviewed)


def _deemed_brand_source(origin_type, fields):
    """The bottler/producer (domestic) or importer (imported) name that TTB deems
    to be the brand name when a label bears no brand name (27 CFR 4.33 for wine;
    7.23 malt beverage; 5.x spirits). Returns that name if present, else ""."""
    key = "importer_name_address" if origin_type == "imported" else "domestic_name_address"
    return (fields.get(key) or "").strip()


def check_brand_name(product_category, origin_type, expected, reviewed):
    """Brand name, with TTB's deemed-brand rule (27 CFR 4.33 etc.): when a label
    bears no brand name, the bottler/producer/importer name is deemed the brand,
    so a brandless label that still names its bottler is compliant — surface that
    as DEEMED_FROM_BOTTLER (confirm) rather than a missing-brand failure.
    """
    exp = (expected.get("brand_name") or "").strip()
    rev = (reviewed.get("brand_name") or "").strip()

    if rev:  # label carries a brand name → ordinary required-field handling
        if not exp:
            return "EXPECTED VALUE MISSING"
        return match_field("brand_name", product_category, exp, rev)

    # Label bears no brand name: fall back to the deemed brand if a bottler/
    # producer/importer name is present; otherwise the brand is truly missing.
    if _deemed_brand_source(origin_type, reviewed):
        return "DEEMED_FROM_BOTTLER"
    return "MISSING"


def check_optional(field, product_category, expected, reviewed):
    if expected and expected.strip():
        return match_field(field, product_category, expected, reviewed)
    if reviewed and reviewed.strip():
        # Present on the label but not entered in the COLA — surface it so the
        # reviewer confirms applicability instead of silently passing.
        return "PRESENT_ON_LABEL_CONFIRM_APPLICABILITY"
    return "NOT REQUIRED"


def _contains_token(text, tokens):
    if not text:
        return False
    lowered = text.lower()
    return any(re.search(r"\b" + re.escape(token) + r"\b", lowered) for token in tokens)


def is_table_wine(reviewed: dict) -> bool:
    blob = " ".join(filter(None, [reviewed.get("class_type"), reviewed.get("fanciful_name")]))
    return _contains_token(blob, TABLE_WINE_DESIGNATION_TOKENS)


def check_wine_alcohol_content(expected, reviewed: dict):
    """Wine ABV is conditional: a table/light wine may omit a numeric statement
    (27 CFR 4.36(a)). Otherwise an ABV is expected."""
    reviewed_value = reviewed.get("alcohol_content")
    if reviewed_value and reviewed_value.strip():
        if expected and expected.strip():
            return match_alcohol_content("wine", expected, reviewed_value)
        return "PRESENT_ON_LABEL_CONFIRM_APPLICABILITY"
    if is_table_wine(reviewed):
        return "EXEMPT_TABLE_WINE"
    if expected and expected.strip():
        return "MISSING"
    return "NOT REQUIRED"


def _appellation_trigger_present(reviewed: dict) -> bool:
    if (reviewed.get("grape_varietal") or "").strip():
        return True
    if re.search(r"\b(19|20)\d{2}\b", reviewed.get("vintage_date") or ""):
        return True
    blob = " ".join(filter(None, [reviewed.get("class_type"), reviewed.get("fanciful_name")]))
    return _contains_token(blob, SEMI_GENERIC_WINE_TYPES) or _contains_token(blob, ESTATE_BOTTLED_TOKENS)


def check_wine_appellation(expected, reviewed: dict):
    """Appellation of origin becomes mandatory when the label bears a varietal,
    vintage, semi-generic type, or "estate bottled" (27 CFR 4.25/4.34)."""
    reviewed_value = reviewed.get("appellation_of_origin")
    if expected and expected.strip():
        if not reviewed_value or not reviewed_value.strip():
            return "MISSING"
        return match_field("appellation_of_origin", "wine", expected, reviewed_value)
    if reviewed_value and reviewed_value.strip():
        return "PRESENT_ON_LABEL_CONFIRM_APPLICABILITY"
    if _appellation_trigger_present(reviewed):
        return "FAIL_APPELLATION_REQUIRED_BY_TRIGGER"
    return "NOT REQUIRED"


def check_aspartame(product_category, expected, reviewed):
    """Conditional comparison plus the all-caps format rule (27 CFR 7.63(b)(4))."""
    if reviewed and reviewed.strip():
        letters = [c for c in reviewed if c.isalpha()]
        if letters and "".join(letters) != "".join(letters).upper():
            return "FAIL_NOT_ALLCAPS"
    return check_optional("aspartame_declaration", product_category, expected, reviewed)


def normalize_warning_spacing(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _warning_key(value):
    """Whitespace-free comparison key. Spacing is not regulated wording — only the
    words and punctuation are — so comparing on a space-free key keeps OCR/extraction
    artifacts like "WARNING:(1)" vs "WARNING: (1)" from registering as a mismatch,
    while every letter, comma, period, and (1)/(2) marker is still required.
    """
    return re.sub(r"\s+", "", value or "")


def check_government_warning(actual):
    """Validate the health warning against the exact statutory text (27 CFR 16.21).

    The heading "GOVERNMENT WARNING" must appear in capital letters (27 CFR
    16.22). The wording and punctuation must match, but the *case* of the body is
    not regulated — an all-caps warning is compliant and common on real labels —
    so the body is compared case-insensitively. Spacing is not regulated either
    (and OCR routinely drops the space around "(1)"/"(2)"), so the comparison
    ignores whitespace entirely; the words and punctuation marks are still
    required. Returns granular codes — FAIL_MISSING_HEADING, FAIL_HEADING_FORMAT
    (e.g. title-case heading), FAIL_TEXT_MISMATCH, MISSING — rather than PASS/FAIL.
    Typography (bold, type size) is not text-verifiable.
    """
    if not normalize_warning_spacing(actual):
        return "MISSING"

    actual_key = _warning_key(actual)
    heading_key = _warning_key(EXPECTED_WARNING_HEADING)  # "GOVERNMENTWARNING:"
    heading_words = heading_key.rstrip(":")               # "GOVERNMENTWARNING"
    expected_key = _warning_key(EXPECTED_WARNING)

    # The heading must be present in capital letters, including the colon
    # (spacing within it ignored, case enforced). If the words are there but the
    # caps or colon are wrong, that's a format failure rather than a missing one.
    if heading_key not in actual_key:
        if heading_words.lower() in actual_key.lower():
            return "FAIL_HEADING_FORMAT"
        return "FAIL_MISSING_HEADING"

    # Wording + punctuation must match; letter case and spacing are not regulated.
    if actual_key.lower() == expected_key.lower():
        return "PASS"

    return "FAIL_TEXT_MISMATCH"


def get_wine_path(origin_type: str, alcohol_content: str):
    """Classify a wine by origin and the 7% ABV threshold (27 CFR 4.36): wine
    under 7% ABV is regulated differently from wine at or above 7%. Returns an
    advisory path label; 'wine_abv_unknown' when the ABV can't be parsed."""
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


def _ordered_unique(fields):
    return [field for field in FIELD_ORDER if field in set(fields)]


def get_field_requirements(product_category: str, origin_type: str) -> dict:
    applicable = set(fields_for_category(product_category))
    # Drop origin-specific fields that don't belong to the selected origin, so an
    # imported product never shows the domestic-bottler field and a domestic one
    # never shows importer / country-of-origin.
    applicable -= {
        field for field, origins in ORIGIN_SCOPED_FIELDS.items()
        if origin_type not in origins
    }
    required = _ordered_unique(
        COMMON_REQUIRED_FIELDS
        + PRODUCT_REQUIRED_FIELDS[product_category]
        + ORIGIN_REQUIRED_FIELDS[origin_type]
    )
    conditional = _ordered_unique(PRODUCT_CONDITIONAL_FIELDS[product_category])
    optional = [
        field
        for field in FIELD_ORDER
        if field in applicable and field not in set(required) and field not in set(conditional)
    ]

    return {
        "required": required,
        "conditional": conditional,
        "optional": optional,
    }


def _validate_by_requirements(product_category: str, origin_type: str, expected: dict, reviewed: dict) -> dict:
    requirements = get_field_requirements(product_category, origin_type)
    required_fields = set(requirements["required"])
    applicable = set(requirements["required"] + requirements["conditional"] + requirements["optional"])
    validation = {}

    for field in FIELD_ORDER:
        if field not in applicable:
            continue  # field not relevant to this product category
        if field == "government_warning":
            # The health warning must match the exact statutory text (27 CFR 16.21)
            # on BOTH the COLA application and the label, so each side is checked
            # against the statute independently and surfaced as its own status.
            validation[field] = {
                "expected": check_government_warning(expected.get(field)),
                "label": check_government_warning(reviewed.get(field)),
            }
        elif field == "alcohol_content" and product_category == "wine":
            validation[field] = check_wine_alcohol_content(expected.get(field), reviewed)
        elif field == "appellation_of_origin" and product_category == "wine":
            validation[field] = check_wine_appellation(expected.get(field), reviewed)
        elif field == "aspartame_declaration":
            validation[field] = check_aspartame(product_category, expected.get(field), reviewed.get(field))
        elif field == "brand_name":
            # Applies TTB's deemed-brand rule (27 CFR 4.33) — a brandless label
            # that names its bottler is not missing a brand.
            validation[field] = check_brand_name(product_category, origin_type, expected, reviewed)
        elif field in required_fields:
            validation[field] = check_required(field, product_category, expected.get(field), reviewed.get(field))
        else:
            validation[field] = check_optional(field, product_category, expected.get(field), reviewed.get(field))

    return validation


def validate_malt_beverage(expected: dict, reviewed: dict, origin_type: str) -> dict:
    return _validate_by_requirements("malt_beverage", origin_type, expected, reviewed)


def validate_distilled_spirits(expected: dict, reviewed: dict, origin_type: str) -> dict:
    return _validate_by_requirements("distilled_spirits", origin_type, expected, reviewed)


def validate_wine(expected: dict, reviewed: dict, origin_type: str) -> dict:
    return _validate_by_requirements("wine", origin_type, expected, reviewed)


def validate_label_fields(product_category: str, origin_type: str, expected: dict, reviewed: dict) -> dict:
    if product_category == "malt_beverage":
        return validate_malt_beverage(expected, reviewed, origin_type)
    if product_category == "distilled_spirits":
        return validate_distilled_spirits(expected, reviewed, origin_type)
    if product_category == "wine":
        return validate_wine(expected, reviewed, origin_type)
    raise ValueError(f"Unsupported product category: {product_category}")


def _check(name, label, status, detail):
    return {"name": name, "label": label, "status": status, "detail": detail}


def compute_label_checks(product_category: str, origin_type: str, reviewed: dict) -> list:
    """Label-only compliance checks that don't compare to the COLA: net-contents
    unit system and standard of fill, origin coherence, and (spirits) state of
    distillation vs name/address. Advisory — surfaced alongside the field
    comparison for the reviewer."""
    checks = []
    net_contents = (reviewed.get("net_contents") or "").strip()

    # Net-contents unit system (wine/spirits metric; malt U.S. customary).
    if net_contents:
        system = net_contents_unit_system(net_contents)
        expected_system = "customary" if product_category == "malt_beverage" else "metric"
        readable = product_category.replace("_", " ")
        if system is None:
            checks.append(_check("net_contents_unit_system", "Net contents unit system",
                                 "INFO", "Could not recognize the net-contents unit."))
        elif system != expected_system:
            checks.append(_check("net_contents_unit_system", "Net contents unit system",
                                 "FAIL", f"{readable} must use {expected_system} units; the label uses {system} units."))
        else:
            checks.append(_check("net_contents_unit_system", "Net contents unit system",
                                 "PASS", f"Uses {expected_system} units."))

    # Standard of fill (wine and distilled spirits only).
    if net_contents and product_category in ("wine", "distilled_spirits"):
        milliliters = parse_volume(net_contents)
        approved = is_approved_standard_of_fill(product_category, milliliters)
        cite = "27 CFR 4.72" if product_category == "wine" else "27 CFR 5.203"
        if milliliters is None:
            checks.append(_check("standard_of_fill", "Standard of fill",
                                 "INFO", "Could not parse the net-contents volume."))
        elif approved:
            checks.append(_check("standard_of_fill", "Standard of fill",
                                 "PASS", f"{milliliters:g} mL is an approved standard of fill."))
        else:
            checks.append(_check("standard_of_fill", "Standard of fill",
                                 "FAIL", f"{milliliters:g} mL is not a recognized approved standard of fill ({cite}); verify against the current regulation."))

    # Origin coherence: populated fields should match the selected origin.
    if origin_type == "domestic":
        if (reviewed.get("importer_name_address") or "").strip() or (reviewed.get("country_of_origin") or "").strip():
            checks.append(_check("origin_consistency", "Origin consistency",
                                 "INFO", "Origin is domestic but importer / country-of-origin fields are filled — confirm the origin selection."))
    else:
        if (reviewed.get("domestic_name_address") or "").strip():
            checks.append(_check("origin_consistency", "Origin consistency",
                                 "INFO", "Origin is imported but a domestic name/address is filled — confirm the origin selection."))

    # Distilled spirits: state of distillation vs the name/address state.
    if product_category == "distilled_spirits":
        state = (reviewed.get("state_of_distillation") or "").strip()
        address = (reviewed.get("domestic_name_address") or "").strip()
        if state and address:
            state_token = _apply_map(_normalize_basic(state), STATE_ABBREVIATIONS)
            address_norm = _apply_map(_normalize_basic(address), STATE_ABBREVIATIONS)
            matches = bool(state_token) and re.search(r"\b" + re.escape(state_token) + r"\b", address_norm)
            checks.append(_check("state_of_distillation_consistency", "State of distillation vs address",
                                 "INFO",
                                 "Matches the name/address state." if matches
                                 else "Differs from the name/address state — verify which is the true state of distillation."))

    return checks
