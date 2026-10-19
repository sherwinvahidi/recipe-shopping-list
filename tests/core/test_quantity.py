import pytest
from fractions import Fraction as F
from shopping_list.core.quantity import parse_quantity, QuantityError, QUANTITY_ERROR_MESSAGE

@pytest.mark.parametrize("text,expected", [
    ("2", F(2)), ("0.5", F(1, 2)), (".5", F(1, 2)), ("1/2", F(1, 2)),
    ("1 1/2", F(3, 2)), ("½", F(1, 2)), ("1½", F(3, 2)), ("1 ½", F(3, 2)),
    ("⅓", F(1, 3)), ("⅔", F(2, 3)), ("¾", F(3, 4)), ("⅜", F(3, 8)), ("⅚", F(5, 6)),
    ("  2  ", F(2)), ("1  1/2", F(3, 2)), ("1 / 2", F(1, 2)), ("10", F(10)),
])
def test_parses(text, expected):
    assert parse_quantity(text) == expected

@pytest.mark.parametrize("text", ["", "   "])
def test_blank_is_none(text):
    assert parse_quantity(text) is None

@pytest.mark.parametrize("text", ["1-2", "a few", "0", "-1", "1/0", "0/3", "1.2.3", "½½", "2 cups"])
def test_rejects(text):
    with pytest.raises(QuantityError) as exc:
        parse_quantity(text)
    assert str(exc.value) == QUANTITY_ERROR_MESSAGE
