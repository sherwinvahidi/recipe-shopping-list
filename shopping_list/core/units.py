"""Unit alias canonicalization."""
import re

CANONICAL_UNITS: tuple[str, ...] = (
    "tsp", "tbsp", "fl oz", "cup", "pint", "quart", "gallon",
    "ml", "l", "oz", "lb", "g", "kg",
)

_ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    "tsp": ("tsp", "tsps", "teaspoon", "teaspoons"),
    "tbsp": ("tbsp", "tbsps", "tbs", "tbl", "tablespoon", "tablespoons"),
    "fl oz": ("fl oz", "floz", "fluid ounce", "fluid ounces"),
    "cup": ("c", "cup", "cups"),
    "pint": ("pt", "pint", "pints"),
    "quart": ("qt", "quart", "quarts"),
    "gallon": ("gal", "gallon", "gallons"),
    "ml": ("ml", "milliliter", "milliliters", "millilitre", "millilitres"),
    "l": ("l", "liter", "liters", "litre", "litres"),
    "oz": ("oz", "ounce", "ounces"),
    "lb": ("lb", "lbs", "pound", "pounds"),
    "g": ("g", "gram", "grams"),
    "kg": ("kg", "kilogram", "kilograms"),
}

_ALIASES: dict[str, str] = {
    alias: canon for canon, aliases in _ALIAS_GROUPS.items() for alias in aliases
}
# "t" and "T" differ only by case, so they are matched on the exact text first.
_CASE_SENSITIVE = {"t": "tsp", "T": "tbsp"}


def normalize_unit_text(text: str) -> str:
    """Trim, drop a trailing period, collapse whitespace and read "fl." as "fl"."""
    key = text.strip()
    if key.endswith("."):
        key = key[:-1]
    key = re.sub(r"\s+", " ", key)
    return re.sub(r"(?i)\bfl\.", "fl", key)


def canonical_unit(text: str) -> tuple[str | None, bool]:
    """Return (canonical, True) for a known alias, (trimmed, False) for an
    unknown unit, and (None, True) for blank input."""
    trimmed = text.strip()
    if not trimmed:
        return None, True
    key = normalize_unit_text(trimmed)
    if key in _CASE_SENSITIVE:
        return _CASE_SENSITIVE[key], True
    canon = _ALIASES.get(key.lower())
    if canon is not None:
        return canon, True
    return trimmed, False
