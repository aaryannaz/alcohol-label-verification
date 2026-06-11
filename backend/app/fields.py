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


FIELD_SPECS = (
    # --- Core fields (all categories) ---
    FieldSpec("brand_name", "Brand name", "text"),
    FieldSpec("class_type", "Class/type designation", "text"),
    FieldSpec("alcohol_content", "Alcohol content", "text"),
    FieldSpec("net_contents", "Net contents", "text"),
    FieldSpec("government_warning", "Government warning", "textarea"),
    FieldSpec("domestic_name_address", "Domestic name/address", "textarea"),
    FieldSpec("importer_name_address", "Importer name/address", "textarea"),
    FieldSpec("country_of_origin", "Country of origin", "text"),
    FieldSpec("sulfite_declaration", "Sulfite declaration", "text"),
    FieldSpec("fanciful_name", "Fanciful name", "text"),
    # --- Conditional additive / ingredient disclosures ---
    FieldSpec("fdc_yellow_5_declaration", "FD&C Yellow #5 declaration", "text"),
    FieldSpec("cochineal_carmine_declaration", "Cochineal/Carmine declaration", "text"),
    FieldSpec("aspartame_declaration", "Aspartame declaration", "text", ("malt_beverage",)),
    # --- Distilled-spirits-specific ---
    FieldSpec("statement_of_age", "Statement of age", "text", ("distilled_spirits",)),
    FieldSpec("commodity_statement", "Commodity statement", "text", ("distilled_spirits",)),
    FieldSpec("coloring_materials", "Coloring materials", "text", ("distilled_spirits",)),
    FieldSpec("wood_treatment", "Wood treatment", "text", ("distilled_spirits",)),
    FieldSpec("state_of_distillation", "State of distillation", "text", ("distilled_spirits",)),
    # --- Wine-specific ---
    FieldSpec("appellation_of_origin", "Appellation of origin", "text", ("wine",)),
    FieldSpec("vintage_date", "Vintage date", "text", ("wine",)),
    FieldSpec("grape_varietal", "Grape varietal", "text", ("wine",)),
    FieldSpec("percentage_of_foreign_wine", "Percentage of foreign wine", "text", ("wine",)),
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
