"""Canonical definition of the regulated label fields.

This is the single source of truth for the field set, order, display labels,
control types, and which product categories each field applies to. The Pydantic
model (schemas.LabelFields), the validation field order (validation.FIELD_ORDER),
the extraction response schema, and the browser UI (served via GET /fields) all
derive from FIELD_SPECS so the field set can never drift across the stack. Add or
rename a regulated field here only.
"""

from dataclasses import dataclass

ALL_CATEGORIES = ("malt_beverage", "distilled_spirits", "wine")


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    control: str  # "text" or "textarea"
    categories: tuple = ALL_CATEGORIES  # product categories this field applies to


# Ordered to track the TTB COLA application form (Form 5100.31) a reviewer reads
# from: the fields that appear as boxes on the form come first, in box order,
# then the label-only checks the form doesn't carry (government warning, additive
# disclosures, category-specific statements). This is the single source of order
# for the UI form, the results table, and the model — see module docstring.
FIELD_SPECS = (
    # --- On the COLA application form (Form 5100.31), in box order ---
    FieldSpec("brand_name", "Brand name", "text"),                            # box 6
    FieldSpec("fanciful_name", "Fanciful name", "text"),                      # box 7
    FieldSpec("class_type", "Class/type designation", "text"),                # class/type description
    FieldSpec("domestic_name_address", "Domestic name/address", "textarea"),  # box 8 (domestic source)
    FieldSpec("importer_name_address", "Importer name/address", "textarea"),  # box 8 (imported source)
    FieldSpec("country_of_origin", "Country of origin", "text"),              # imported product
    FieldSpec("grape_varietal", "Grape varietal", "text", ("wine",)),         # box 10 (wine only)
    FieldSpec("appellation_of_origin", "Appellation of origin", "text", ("wine",)),  # box 11 (wine only)
    FieldSpec("net_contents", "Net contents", "text"),                        # box 15
    FieldSpec("alcohol_content", "Alcohol content", "text"),
    # --- Label-only checks (not boxes on Form 5100.31) ---
    FieldSpec("government_warning", "Government warning", "textarea"),
    FieldSpec("sulfite_declaration", "Sulfite declaration", "text"),
    FieldSpec("vintage_date", "Vintage date", "text", ("wine",)),
    FieldSpec("percentage_of_foreign_wine", "Percentage of foreign wine", "text", ("wine",)),
    # Conditional additive / ingredient disclosures
    FieldSpec("fdc_yellow_5_declaration", "FD&C Yellow #5 declaration", "text"),
    FieldSpec("cochineal_carmine_declaration", "Cochineal/Carmine declaration", "text"),
    FieldSpec("aspartame_declaration", "Aspartame declaration", "text", ("malt_beverage",)),
    # Distilled-spirits-specific statements
    FieldSpec("statement_of_age", "Statement of age", "text", ("distilled_spirits",)),
    FieldSpec("commodity_statement", "Commodity statement", "text", ("distilled_spirits",)),
    FieldSpec("coloring_materials", "Coloring materials", "text", ("distilled_spirits",)),
    FieldSpec("wood_treatment", "Wood treatment", "text", ("distilled_spirits",)),
    FieldSpec("state_of_distillation", "State of distillation", "text", ("distilled_spirits",)),
)

FIELD_KEYS = tuple(spec.key for spec in FIELD_SPECS)

FIELD_CATEGORIES = {spec.key: spec.categories for spec in FIELD_SPECS}


def fields_for_category(product_category: str) -> list[str]:
    """Field keys applicable to a product category, in canonical order."""
    return [spec.key for spec in FIELD_SPECS if product_category in spec.categories]


def field_specs_payload() -> list[dict]:
    """Serializable field specs for the browser UI (GET /fields)."""
    return [
        {"key": s.key, "label": s.label, "control": s.control, "categories": list(s.categories)}
        for s in FIELD_SPECS
    ]
