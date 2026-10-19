import pytest
from shopping_list.core.units import canonical_unit, CANONICAL_UNITS

ALIASES = {
    "tsp": ["t", "tsp", "tsps", "teaspoon", "teaspoons", "TSP", "Tsp.", "teaspoons."],
    "tbsp": ["T", "tbsp", "tbsps", "tbs", "tbl", "tablespoon", "Tablespoons", "Tbsp."],
    "fl oz": ["fl oz", "fl. oz", "floz", "fluid ounce", "Fluid Ounces", "fl  oz"],
    "cup": ["c", "cup", "Cups"], "pint": ["pt", "pint", "pints"],
    "quart": ["qt", "quart", "quarts"], "gallon": ["gal", "gallon", "gallons"],
    "ml": ["ml", "mL", "milliliter", "millilitres"], "l": ["l", "L", "liter", "litres"],
    "oz": ["oz", "ounce", "Ounces"], "lb": ["lb", "lbs", "pound", "Pounds"],
    "g": ["g", "gram", "grams"], "kg": ["kg", "kilogram", "kilograms"],
}


@pytest.mark.parametrize("canon,alias", [(c, a) for c, al in ALIASES.items() for a in al])
def test_aliases(canon, alias):
    assert canonical_unit(alias) == (canon, True)


def test_t_vs_T_case_sensitive():
    assert canonical_unit("t") == ("tsp", True)
    assert canonical_unit("T") == ("tbsp", True)


def test_blank():
    assert canonical_unit("  ") == (None, True)


def test_unknown_passthrough_trimmed():
    assert canonical_unit("  Clove ") == ("Clove", False)


def test_canonical_set_complete():
    assert set(ALIASES) == set(CANONICAL_UNITS)
