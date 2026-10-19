from fractions import Fraction as F
from shopping_list.core.models import Ingredient
from shopping_list.core.validation import (validate_row, validate_recipe, normalize_recipe_name,
    Issue, INGREDIENT_REQUIRED, RECIPE_NAME_REQUIRED, SERVINGS_INVALID, NO_INGREDIENTS,
    UNKNOWN_UNIT, UNIT_WITHOUT_QUANTITY)
from shopping_list.core.quantity import QUANTITY_ERROR_MESSAGE

def test_valid_row():
    assert validate_row(" flour ", "1 1/2", "cups") == (Ingredient("flour", F(3, 2), "cup"), [])

def test_counted_and_to_taste():
    assert validate_row("egg", "1", "") == (Ingredient("egg", F(1), None), [])
    assert validate_row("salt", "", "") == (Ingredient("salt", None, None), [])

def test_blank_ingredient_error():
    ing, issues = validate_row("  ", "1", "cup")
    assert ing is None and issues == [Issue("error", INGREDIENT_REQUIRED, "ingredient")]

def test_bad_quantity_error():
    ing, issues = validate_row("milk", "1-2", "cup")
    assert ing is None and issues == [Issue("error", QUANTITY_ERROR_MESSAGE, "quantity")]

def test_unknown_unit_warning():
    ing, issues = validate_row("garlic", "4", "clove")
    assert ing == Ingredient("garlic", F(4), "clove")
    assert issues == [Issue("warning", UNKNOWN_UNIT.format(unit="clove"), "unit")]

def test_unit_without_quantity_warning():
    ing, issues = validate_row("salt", "", "tsp")
    assert ing == Ingredient("salt", None, "tsp")
    assert issues == [Issue("warning", UNIT_WITHOUT_QUANTITY, "unit")]

def test_multiple_errors_reported_together():
    _, issues = validate_row("", "x", "cup")
    assert {i.field for i in issues} == {"ingredient", "quantity"}
    assert [i.field for i in issues] == ["ingredient", "quantity"]

def test_unknown_unit_and_blank_quantity_both_warn():
    ing, issues = validate_row("salt", "", " pinch ")
    assert ing == Ingredient("salt", None, "pinch")
    assert issues == [Issue("warning", UNKNOWN_UNIT.format(unit="pinch"), "unit"),
                      Issue("warning", UNIT_WITHOUT_QUANTITY, "unit")]

def test_invalid_quantity_with_unit_has_no_unit_without_quantity_warning():
    _, issues = validate_row("milk", "x", "cup")
    assert issues == [Issue("error", QUANTITY_ERROR_MESSAGE, "quantity")]

def test_ingredient_name_whitespace_collapsed_case_kept():
    ing, _ = validate_row("  Olive   Oil ", "1", "tbsp")
    assert ing.name == "Olive Oil"

def test_recipe_valid():
    assert validate_recipe("Pancakes", " 4 ", 6) == (4, [])

def test_recipe_errors():
    assert validate_recipe("", "4", 1) == (4, [Issue("error", RECIPE_NAME_REQUIRED, "recipe")])
    for bad in ["", "0", "-2", "2.5", "four"]:
        assert validate_recipe("X", bad, 1) == (None, [Issue("error", SERVINGS_INVALID, "servings")])
    assert validate_recipe("X", "2", 0) == (2, [Issue("error", NO_INGREDIENTS, None)])

def test_normalize_recipe_name():
    assert normalize_recipe_name("  Garlic   Pasta ") == "garlic pasta"
