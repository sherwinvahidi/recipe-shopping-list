import re
from fractions import Fraction
from math import floor

QUANTITY_ERROR_MESSAGE = "Quantity must be a single positive number, e.g. 2, 1/2, 1 1/2"

VULGAR = {
    "½": Fraction(1, 2), "⅓": Fraction(1, 3), "⅔": Fraction(2, 3),
    "¼": Fraction(1, 4), "¾": Fraction(3, 4),
    "⅕": Fraction(1, 5), "⅖": Fraction(2, 5), "⅗": Fraction(3, 5), "⅘": Fraction(4, 5),
    "⅙": Fraction(1, 6), "⅚": Fraction(5, 6),
    "⅛": Fraction(1, 8), "⅜": Fraction(3, 8), "⅝": Fraction(5, 8), "⅞": Fraction(7, 8),
}

_GLYPH_FOR = {v: k for k, v in VULGAR.items()}

_FRAC = rf"(?:\d+/\d+|[{''.join(VULGAR)}])"
_PATTERN = re.compile(
    rf"^(?:(?P<whole>\d+)\s*(?P<mixed>{_FRAC})"
    rf"|(?P<frac>{_FRAC})"
    rf"|(?P<decimal>\d*\.\d+|\d+))$"
)


class QuantityError(ValueError):
    def __init__(self) -> None:
        super().__init__(QUANTITY_ERROR_MESSAGE)


def _frac_value(token: str) -> Fraction:
    if token in VULGAR:
        return VULGAR[token]
    num, den = token.split("/")
    if int(den) == 0:
        raise QuantityError()
    return Fraction(int(num), int(den))


def parse_quantity(text: str) -> Fraction | None:
    try:
        return _parse_quantity(text)
    except ValueError as err:  # includes int-string digit limit; QuantityError is a ValueError
        if isinstance(err, QuantityError):
            raise
        raise QuantityError() from err


def _parse_quantity(text: str) -> Fraction | None:
    text = text.strip()
    if not text:
        return None
    text = re.sub(r"\s*/\s*", "/", text)
    m = _PATTERN.match(text)
    if not m:
        raise QuantityError()
    if m["mixed"]:
        value = Fraction(int(m["whole"])) + _frac_value(m["mixed"])
    elif m["frac"]:
        value = _frac_value(m["frac"])
    else:
        value = Fraction(m["decimal"])
    if value <= 0:
        raise QuantityError()
    return value


def format_quantity(q: Fraction, exact: bool = False) -> str:
    """Format a positive quantity for display, using exact Fraction arithmetic.

    Denominators other than 2, 3, 4 and 8 are rounded to 2 decimals, or shown
    as a plain (mixed) fraction such as "1 1/16" when `exact` is set.
    """
    if q.denominator == 1:
        return str(q.numerator)
    whole, rem = divmod(q.numerator, q.denominator)
    if q.denominator in (2, 3, 4, 8):
        glyph = _GLYPH_FOR[Fraction(rem, q.denominator)]
        return f"{whole}{glyph}" if whole else glyph
    if exact:
        frac = f"{rem}/{q.denominator}"
        return f"{whole} {frac}" if whole else frac
    h = floor(q * 100 + Fraction(1, 2))
    if h == 0:
        return "<0.01"
    text = f"{h // 100}.{h % 100:02d}".rstrip("0").rstrip(".")
    return text
