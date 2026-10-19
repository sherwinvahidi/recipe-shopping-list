"""Aggregate selected recipes into a merged shopping list."""

from dataclasses import dataclass
from fractions import Fraction

from shopping_list.core.models import Recipe
from shopping_list.core.names import name_key
from shopping_list.core.quantity import format_quantity
from shopping_list.core.units import canonical_unit

PLURAL_UNITS = frozenset({"cup", "pint", "quart", "gallon"})


@dataclass(frozen=True)
class ShoppingLine:
    key: tuple[str, str | None]
    display_name: str
    quantity: Fraction | None
    unit: str | None
    sources: tuple[str, ...]


# An entry is (recipe index, position, ingredient name, recipe name).
_Entry = tuple[int, int, str, str]


def _unit_parts(raw: str | None) -> tuple[str | None, str | None]:
    """Return (unit key, displayed unit); both None for a missing/blank unit."""
    if raw is None:
        return None, None
    canon, known = canonical_unit(raw)
    if canon is None:
        return None, None
    if known:
        return canon, canon
    return " ".join(raw.split()).lower(), canon


def _sort_key(display_name: str, unit: str | None) -> tuple[str, str]:
    return display_name.casefold(), "" if unit is None else unit.casefold()


def build_shopping_list(recipes: list[Recipe]) -> list[ShoppingLine]:
    # group key -> [quantity sum, displayed unit, entries]
    groups: dict[tuple[str, str | None], list] = {}
    to_taste: dict[str, list[_Entry]] = {}
    for r, recipe in enumerate(recipes):
        for p, ing in enumerate(recipe.ingredients):
            nk = name_key(ing.name)
            entry: _Entry = (r, p, ing.name, recipe.name)
            if ing.quantity is None:
                to_taste.setdefault(nk, []).append(entry)
                continue
            unit_key, shown = _unit_parts(ing.unit)
            group = groups.setdefault((nk, unit_key), [Fraction(0), shown, []])
            group[0] += ing.quantity
            group[2].append(entry)

    def group_sort_key(key: tuple[str, str | None]) -> tuple[str, str]:
        group = groups[key]
        first = min(group[2], key=lambda e: (e[0], e[1]))
        return _sort_key(first[2], group[1])

    # Sort keys are computed before any absorption.
    sort_keys = {key: group_sort_key(key) for key in groups}
    by_name: dict[str, list[tuple[str, str | None]]] = {}
    for key in groups:
        by_name.setdefault(key[0], []).append(key)

    lines_input: list[tuple[tuple[str, str | None], Fraction | None, str | None, list[_Entry]]] = []
    for nk, entries in to_taste.items():
        if nk in by_name:
            target = min(by_name[nk], key=lambda k: sort_keys[k])
            groups[target][2].extend(entries)
        else:
            lines_input.append(((nk, None), None, None, list(entries)))
    for key, (total, shown, entries) in groups.items():
        lines_input.append((key, total, shown, entries))

    lines: list[ShoppingLine] = []
    for key, total, shown, entries in lines_input:
        entries = sorted(entries, key=lambda e: (e[0], e[1]))
        sources = tuple(dict.fromkeys(e[3] for e in entries))
        lines.append(ShoppingLine(key, entries[0][2], total, shown, sources))
    lines.sort(key=lambda l: _sort_key(l.display_name, l.unit))
    return lines


def format_line(line: ShoppingLine) -> str:
    if line.quantity is None:
        return line.display_name
    text = f"{line.display_name} — {format_quantity(line.quantity)}"
    if line.unit:
        plural = "s" if line.unit in PLURAL_UNITS and line.quantity > 1 else ""
        text += f" {line.unit}{plural}"
    return text
