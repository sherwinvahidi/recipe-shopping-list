import re
from dataclasses import dataclass
from typing import Literal

from shopping_list.core.models import Ingredient
from shopping_list.core.quantity import QUANTITY_ERROR_MESSAGE, QuantityError, parse_quantity
from shopping_list.core.units import canonical_unit

INGREDIENT_REQUIRED = "Ingredient name is required"
RECIPE_NAME_REQUIRED = "Recipe name is required"
SERVINGS_INVALID = "Servings must be a whole number of 1 or more"
NO_INGREDIENTS = "Recipe has no ingredients"
UNKNOWN_UNIT = "Unknown unit '{unit}' — it will only combine with the same unit"
UNIT_WITHOUT_QUANTITY = "Unit has no quantity; treated as 'to taste'"


@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning"]
    message: str
    field: str | None


def _collapse(text: str) -> str:
    return " ".join(text.split())


def normalize_recipe_name(name: str) -> str:
    return _collapse(name).lower()


def validate_row(ingredient: str, quantity: str, unit: str) -> tuple[Ingredient | None, list[Issue]]:
    issues: list[Issue] = []
    name = _collapse(ingredient)
    if not name:
        issues.append(Issue("error", INGREDIENT_REQUIRED, "ingredient"))

    qty = None
    try:
        qty = parse_quantity(quantity)
    except QuantityError:
        issues.append(Issue("error", QUANTITY_ERROR_MESSAGE, "quantity"))
        quantity_invalid = True
    else:
        quantity_invalid = False

    canon, known = canonical_unit(unit)
    if not known:
        issues.append(Issue("warning", UNKNOWN_UNIT.format(unit=canon), "unit"))
    if canon is not None and qty is None and not quantity_invalid:
        issues.append(Issue("warning", UNIT_WITHOUT_QUANTITY, "unit"))

    if any(i.level == "error" for i in issues):
        return None, issues
    return Ingredient(name, qty, canon), issues


def validate_recipe(name: str, servings: str, active_row_count: int) -> tuple[int | None, list[Issue]]:
    issues: list[Issue] = []
    if not name.strip():
        issues.append(Issue("error", RECIPE_NAME_REQUIRED, "recipe"))
    text = servings.strip()
    count: int | None = None
    if re.fullmatch(r"\d+", text) and int(text) > 0:
        count = int(text)
    else:
        issues.append(Issue("error", SERVINGS_INVALID, "servings"))
    if active_row_count <= 0:
        issues.append(Issue("error", NO_INGREDIENTS, None))
    return count, issues
