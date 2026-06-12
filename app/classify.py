"""Classify a label's product category and origin from already-extracted fields.

Used by the auto-detect flow: one unified extraction reads every field, then this
infers the product category (from the class/type designation) and the origin
(from the presence of an importer / country-of-origin vs a domestic bottler), so
a reviewer does not have to pick them by hand. Deterministic and rule-based — it
runs on the extracted text, makes no model call.
"""

# Category keywords, checked against the class/type (and fanciful name as a
# fallback). Spirits and wine terms are more specific than the broad malt terms,
# so they are weighted ahead of malt on ties.
_CATEGORY_KEYWORDS = {
    "distilled_spirits": (
        "whiskey", "whisky", "bourbon", "scotch", "rye", "vodka", "gin", "rum",
        "tequila", "mezcal", "brandy", "cognac", "liqueur", "schnapps", "absinthe",
        "aquavit", "grappa", "spirit", "moonshine",
    ),
    "wine": (
        "wine", "chardonnay", "cabernet", "merlot", "pinot", "shiraz", "syrah",
        "riesling", "sauvignon", "chablis", "champagne", "prosecco", "moscato",
        "zinfandel", "sangiovese", "malbec", "chianti", "burgundy", "bordeaux",
        "rosé", "rose", "port", "sherry", "sangria", "vermouth", "sparkling",
    ),
    "malt_beverage": (
        "beer", "ale", "lager", "stout", "porter", "pilsner", "pilsener", "ipa",
        "malt", "hefeweizen", "hefe", "weiss", "weissbier", "saison", "bock",
        "dunkel", "kolsch", "marzen", "gose", "lambic", "witbier", "wheat",
    ),
}

# Priority order for tie-breaking (most specific first).
_CATEGORY_ORDER = ("distilled_spirits", "wine", "malt_beverage")


def classify_category(fields: dict) -> str:
    """Best-guess product category from the class/type (then fanciful name).
    Defaults to malt_beverage when nothing matches."""
    blob = " ".join(
        filter(None, [fields.get("class_type"), fields.get("fanciful_name")])
    ).lower()
    counts = {
        category: sum(1 for kw in keywords if kw in blob)
        for category, keywords in _CATEGORY_KEYWORDS.items()
    }
    best = max(_CATEGORY_ORDER, key=lambda c: (counts[c], -_CATEGORY_ORDER.index(c)))
    return best if counts[best] else "malt_beverage"


def classify_origin(fields: dict) -> str:
    """Imported when the label names an importer or a country of origin; otherwise
    domestic. Mirrors how TTB distinguishes the two (importer statement / country
    of origin for imports vs a domestic bottler)."""
    importer = (fields.get("importer_name_address") or "").strip()
    country = (fields.get("country_of_origin") or "").strip()
    if importer or country:
        return "imported"
    return "domestic"
