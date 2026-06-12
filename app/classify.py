"""Classify a label's product category and origin from already-extracted fields.

Used by the auto-detect flow: one unified extraction reads every field, then this
infers the product category (from the class/type designation) and the origin
(from the presence of an importer / country-of-origin vs a domestic bottler), so
a reviewer does not have to pick them by hand. Deterministic and rule-based — it
runs on the extracted text, makes no model call.
"""

import re

# Category keywords, matched on word boundaries (substring matching misfires:
# "Porter" contains "port", "Ginger" contains "gin", "Export" contains "port").
# Checked against the class/type first; the fanciful name is consulted only when
# the class/type yields no match.
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

# Priority order for breaking exact positional ties (most specific first).
_CATEGORY_ORDER = ("distilled_spirits", "wine", "malt_beverage")


def _classify_text(text: str):
    """Category of the right-most keyword match in `text`, or None.

    TTB class/type designations end with the class noun — "Bourbon Barrel
    Stout" is a stout, "Rye Ale" is an ale — so when keywords from several
    categories appear in one string, the right-most match decides. Word
    boundaries (\\b is Unicode-aware, so "rosé" matches whole) keep "Porter"
    from hitting "port" and "Ginger" from hitting "gin".
    """
    text = text.lower()
    # (end position, match length, category priority) — max() picks the
    # right-most match, preferring the longer keyword and then the more
    # specific category when positions coincide.
    matches = []
    for category, keywords in _CATEGORY_KEYWORDS.items():
        priority = -_CATEGORY_ORDER.index(category)
        for keyword in keywords:
            for found in re.finditer(r"\b" + re.escape(keyword) + r"\b", text):
                matches.append((found.end(), found.end() - found.start(), priority, category))
    if not matches:
        return None
    return max(matches)[3]


def classify_category(fields: dict) -> str:
    """Best-guess product category from the class/type (then fanciful name).
    Defaults to malt_beverage when nothing matches."""
    for source in ("class_type", "fanciful_name"):
        category = _classify_text(fields.get(source) or "")
        if category:
            return category
    return "malt_beverage"


def classify_origin(fields: dict) -> str:
    """Imported when the label names an importer or a country of origin; otherwise
    domestic. Mirrors how TTB distinguishes the two (importer statement / country
    of origin for imports vs a domestic bottler)."""
    importer = (fields.get("importer_name_address") or "").strip()
    country = (fields.get("country_of_origin") or "").strip()
    if importer or country:
        return "imported"
    return "domestic"
