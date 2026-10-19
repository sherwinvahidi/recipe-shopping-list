import pytest
from fractions import Fraction as F
from shopping_list.core.quantity import parse_quantity, QuantityError, QUANTITY_ERROR_MESSAGE
from shopping_list.core.quantity import format_quantity

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


def test_huge_digit_string_is_quantity_error():
    import pytest
    from shopping_list.core.quantity import QuantityError, parse_quantity
    for text in ("9" * 5000, "1/" + "9" * 5000, "1." + "9" * 5000 + "1"):
        with pytest.raises(QuantityError):
            parse_quantity(text)


@pytest.mark.parametrize("q,text", [
    (F(3), "3"), (F(1000), "1000"), (F(3, 2), "1½"), (F(2, 3), "⅔"), (F(19, 8), "2⅜"),
    (F(1, 4), "¼"), (F(7, 4), "1¾"), (F(1, 8), "⅛"), (F(4, 3), "1⅓"),
    (F(5, 6), "0.83"), (F(7, 6), "1.17"), (F(3, 5), "0.6"), (F(1, 16), "0.06"),
    (F(1, 200), "0.01"), (F(1, 300), "<0.01"), (F(2999, 1000), "3"),
])
def test_format_quantity(q, text):
    assert format_quantity(q) == text


@pytest.mark.parametrize("q,text", [
    (F(3), "3"), (F(3, 2), "1½"), (F(2, 3), "⅔"), (F(1, 16), "1/16"),
    (F(17, 16), "1 1/16"), (F(5, 6), "5/6"), (F(1, 1000), "1/1000"),
])
def test_format_quantity_exact(q, text):
    assert format_quantity(q, exact=True) == text
