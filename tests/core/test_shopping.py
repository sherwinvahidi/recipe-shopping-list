import pytest
from fractions import Fraction as F
from shopping_list.core.importer import parse_csv_text
from shopping_list.core.models import Ingredient as I, Recipe
from shopping_list.core.shopping import ShoppingLine, build_shopping_list, format_line
from shopping_list.core.template import TEMPLATE_CSV

def R(name, *ings): return Recipe(name, 2, list(ings))
def texts(recipes): return [format_line(l) for l in build_shopping_list(recipes)]
def L(name, q, unit): return ShoppingLine((name, unit), name, q, unit, ("A",))

def test_template_pancakes_alone():
    pancakes = parse_csv_text(TEMPLATE_CSV).to_recipes()[0]
    assert texts([pancakes]) == ["baking powder — 3½ tsp", "egg — 1", "flour — 1½ cups",
                                 "milk — 1¼ cups", "salt", "sugar — 1 tbsp"]

def test_same_name_and_unit_merge_across_case_and_alias():
    lines = build_shopping_list([R("A", I("olive oil", F(2), "tbsp")),
                                 R("B", I("Olive Oil", F(1), "tablespoon"))])
    assert [format_line(l) for l in lines] == ["olive oil — 3 tbsp"]
    assert lines[0].key == ("olive oil", "tbsp") and lines[0].sources == ("A", "B")

def test_plural_forms_merge_first_spelling_wins():
    assert texts([R("A", I("onions", F(2), None)), R("B", I("onion", F(1), None))]) == ["onions — 3"]

def test_more_specific_name_stays_separate():
    assert texts([R("A", I("yellow onion", F(1), None)), R("B", I("onion", F(1), None))]) == [
        "onion — 1", "yellow onion — 1"]

def test_different_units_stay_separate():
    assert texts([R("A", I("milk", F(1), "cup")), R("B", I("milk", F(4), "tbsp"))]) == [
        "milk — 1 cup", "milk — 4 tbsp"]

def test_counted_and_unit_never_merge():
    assert texts([R("A", I("garlic", F(2), None)), R("B", I("garlic", F(4), "clove"))]) == [
        "garlic — 2", "garlic — 4 clove"]

def test_to_taste_absorbed_into_quantified_line():
    lines = build_shopping_list([R("A", I("salt", None, None)), R("B", I("Salt", F(1), "tsp"))])
    assert [format_line(l) for l in lines] == ["salt — 1 tsp"]
    assert lines[0].key == ("salt", "tsp") and lines[0].sources == ("A", "B")

def test_to_taste_absorbed_into_first_in_sort_order():
    lines = build_shopping_list([R("A", I("milk", F(4), "tbsp"), I("milk", F(1), "cup")),
                                 R("B", I("milk", None, None))])
    assert [(l.unit, l.sources) for l in lines] == [("cup", ("A", "B")), ("tbsp", ("A",))]

def test_to_taste_only_entries_become_one_line():
    lines = build_shopping_list([R("A", I("pepper", None, None)), R("B", I("Pepper", None, "pinch"))])
    assert lines == [ShoppingLine(("pepper", None), "pepper", None, None, ("A", "B"))]

def test_unknown_unit_groups_case_insensitively():
    lines = build_shopping_list([R("A", I("garlic", F(2), "Clove")), R("B", I("garlic", F(1), "clove "))])
    assert [(l.key, l.quantity, l.unit) for l in lines] == [(("garlic", "clove"), F(3), "Clove")]

def test_sorted_case_insensitively():
    assert texts([R("A", I("Zucchini", F(1), None), I("apple", F(2), None), I("Banana", F(3), None))]) == [
        "apple — 2", "Banana — 3", "Zucchini — 1"]

def test_sources_follow_selection_order_and_dedupe():
    lines = build_shopping_list([R("B", I("egg", F(1), None)),
                                 R("A", I("egg", F(2), None), I("eggs", F(1), None))])
    assert len(lines) == 1 and lines[0].quantity == F(4) and lines[0].sources == ("B", "A")

def test_empty_selection():
    assert build_shopping_list([]) == []

@pytest.mark.parametrize("line,text", [
    (L("olive oil", F(5), "tbsp"), "olive oil — 5 tbsp"),
    (L("milk", F(3, 2), "cup"), "milk — 1½ cups"),
    (L("milk", F(1), "cup"), "milk — 1 cup"),
    (L("milk", F(1, 2), "cup"), "milk — ½ cup"),
    (L("egg", F(3), None), "egg — 3"),
    (L("salt", None, None), "salt"),
    (L("garlic", F(4), "clove"), "garlic — 4 clove"),
    (L("stock", F(2), "pint"), "stock — 2 pints"),
    (L("stock", F(3), "quart"), "stock — 3 quarts"),
    (L("water", F(2), "gallon"), "water — 2 gallons"),
    (L("cream", F(2), "fl oz"), "cream — 2 fl oz"),
    (L("beef", F(2), "lb"), "beef — 2 lb"),
    (L("flour", F(500), "g"), "flour — 500 g"),
    (L("sugar", F(2), "tsp"), "sugar — 2 tsp"),
    (L("milk", 1 + F(1, 250), "cup"), "milk — 1 cup"),
    (L("milk", F(199, 200), "cup"), "milk — 1 cup"),
    (L("milk", F(201, 200), "cup"), "milk — 1.01 cups"),
])
def test_format_line(line, text):
    assert format_line(line) == text


def test_unknown_unit_key_uses_unit_normalization():
    lines = build_shopping_list([R("A", I("tomatoes", F(1), "Can.")),
                                 R("B", I("tomatoes", F(2), "can"))])
    assert [format_line(l) for l in lines] == ["tomatoes — 3 Can"]

def test_unknown_unit_display_collapses_whitespace():
    assert texts([R("A", I("beans", F(1), "big  can"))]) == ["beans — 1 big can"]
