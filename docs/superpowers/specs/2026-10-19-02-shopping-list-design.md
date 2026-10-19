# PRD 2 — Shopping List

**Date:** 2026-10-19
**Depends on:** PRD 1 (recipe library)
**See also:** `2026-10-19-00-overview.md`

## Problem

With recipes in the library, the user still has to read each one and tally
ingredients by hand. The app should combine the chosen recipes into a single
list and let the user strike out what they already have.

## Goals

- Select recipes and see one combined, alphabetical shopping list that updates live.
- Merge the same ingredient in the same unit across recipes.
- Check off items in the app; copy the remaining items as plain text.

## Non-goals

- Changing servings (PRD 3) — every recipe is used at its own serving count.
- Converting between units (PRD 4) — `1 cup` and `4 tbsp` of milk stay as two lines here.
- Aliases or fuzzy matching (product decision: a more specific name is a different item).
- Saving lists, printing, `.txt` export, aisle grouping.

## User stories

1. As a user, I add recipes from my library to a selection and see the shopping list immediately.
2. As a user, the same ingredient appearing in several recipes shows as one line with the total.
3. As a user, I can see which recipes a line came from.
4. As a user, I tick items I already have, then copy the rest to paste into my phone's notes.

## Functional requirements

### Screen (`ui/shopping_view.py`)

Main window gains a **Shopping** tab next to **Library**.

- **Left:** recipe library list (same filter box as PRD 1) with an **Add** button per row; recipes already selected show "Added" and are disabled.
- **Right, top:** selected recipes, each with a **Remove** button. A recipe can be selected at most once.
- **Right, bottom:** the shopping list, recomputed on every add/remove. Each line has a checkbox. Toolbar: **Copy list**, **Clear checks**, **Clear selection**.
- Empty selection shows: "Add recipes to build your shopping list."

### Name normalization (`core/names.py`)

`name_key(name: str) -> str`:

1. Lowercase, trim, collapse internal whitespace to single spaces.
2. Singularize the **last word only**, applying the first matching rule:
   1. Word is in `IRREGULAR` → mapped value
      (`leaves→leaf`, `halves→half`, `loaves→loaf`, `cookies→cookie`,
      `brownies→brownie`, `veggies→veggie`).
   2. Word is in `UNCHANGED` (`molasses`, `swiss`, `grits`, `series`) or has ≤ 3 letters → unchanged.
   3. Ends in `ies` → replace with `y` (`berries→berry`, `anchovies→anchovy`).
   4. Ends in `oes` → drop `es` (`tomatoes→tomato`, `potatoes→potato`).
   5. Ends in `ches`, `shes`, `sses`, `xes`, `zes` → drop `es` (`peaches→peach`, `radishes→radish`).
   6. Ends in `ss`, `us`, `is` → unchanged (`asparagus`, `hummus`, `couscous`).
   7. Ends in `s` → drop `s` (`onions→onion`, `eggs→egg`, `peas→pea`).
3. Return the words rejoined with single spaces.

`IRREGULAR` and `UNCHANGED` are module-level dicts/sets so mis-normalizations
are fixed by adding one entry. Normalization is best-effort; its failure mode
is two lines that should have merged, never a wrong merge of distinct items
(only singular/plural forms of the same word collapse).

### Aggregation (`core/shopping.py`)

```python
@dataclass(frozen=True)
class ShoppingLine:
    key: tuple[str, str | None]   # (name_key, unit_key)
    display_name: str             # spelling from the first selected recipe that used it
    quantity: Fraction | None     # None = no amount ("to taste")
    unit: str | None              # canonical unit, raw unknown unit, or None (counted)
    sources: tuple[str, ...]      # recipe names, in selection order, deduplicated

def build_shopping_list(recipes: list[Recipe]) -> list[ShoppingLine]
```

- Group ingredients by `(name_key(name), unit_key)` where `unit_key` is the
  canonical unit, the unknown unit normalized like unit aliases (trimmed,
  trailing period dropped, whitespace collapsed) and lowercased, or `None`.
- Sum quantities within a group as `Fraction`.
- **"To taste" absorption:** an ingredient with no quantity is merged into a
  quantified group with the same `name_key` (any unit; if several, the first in sort order) if one exists —
  it adds its recipe to that line's `sources` and nothing to the quantity. If
  no quantified group exists, all no-quantity entries for that name become one
  line with `quantity=None`.
- Counted items (`unit=None`) and unit-ed items never merge with each other:
  `2 garlic` and `4 clove garlic` are two lines.
- Result sorted by `display_name` (case-insensitive), then unit.

### Display formatting

`core/quantity.py` gains `format_quantity(q: Fraction) -> str`:

| Value | Output |
|---|---|
| 3 | `3` |
| 3/2 | `1½` |
| 2/3 | `⅔` |
| 19/8 | `2⅜` |
| 5/6 | `0.83` (denominators other than 2, 3, 4, 8 → decimal, ≤ 2 places, trailing zeros trimmed) |

`format_quantity(q, exact=True)` shows other denominators as a plain fraction
instead (`1/16`, `1 1/16`). The library's recipe detail uses this exact form,
since it shows stored amounts; the shopping list uses the rounded form.

Line text (`format_line(line) -> str`), ingredient first so the alphabetical list scans easily:

| Line | Text |
|---|---|
| olive oil, 5, tbsp | `olive oil — 5 tbsp` |
| milk, 3/2, cup | `milk — 1½ cups` |
| egg, 3, None | `egg — 3` |
| salt, None, None | `salt` |
| garlic, 4, clove | `garlic — 4 clove` |

Plural unit display: `cup`, `pint`, `quart`, `gallon` add `s` when quantity > 1
and the displayed number is not `1` (so 1.004 cups shows `1 cup`).
Abbreviated units (`tsp`, `tbsp`, `fl oz`, `oz`, `lb`, `g`, `kg`, `ml`, `l`) and
unknown units are never pluralized.

Hovering a line shows "From: Pancakes, Garlic Pasta".

### Checking off and copying

- Check state lives in the view, keyed by `ShoppingLine.key` together with the
  line's quantity when it was checked. It survives list recomputation while the
  line still exists with the same quantity; if the amount changes (another
  recipe adds to it, or a "to taste" line becomes a counted one) the line is
  unchecked so the extra amount is not left off the copied list. It is lost
  when the app closes.
- When the library changes, selected recipes that were deleted drop out of the
  selection with one status message ("'A' was removed from the shopping list",
  or "N recipes were removed from the shopping list: 'A', 'B'"). A recipe
  replaced by an import is followed to its replacement by id (the import
  reports old id → new id); recipes are never re-matched by name.
- Checked lines are shown struck through and greyed.
- **Copy list** puts unchecked lines on the clipboard, one per line, each
  prefixed with `- ` (e.g. `- milk — 1½ cups`). Status bar confirms
  "Copied N items". If every line is checked: "Nothing left to copy".
- **Clear checks** unchecks all; **Clear selection** empties the selection.

## Acceptance criteria

- Selecting the template's Pancakes alone lists 6 lines in alphabetical order, with `salt` having no amount.
- Recipe A `olive oil, 2, tbsp` and recipe B `Olive Oil, 1, tablespoon` produce one line `olive oil — 3 tbsp`.
- `onions, 2,` and `onion, 1,` merge to `onions — 3` (display spelling from the first recipe).
- `yellow onion` and `onion` remain separate lines.
- `milk, 1, cup` and `milk, 4, tbsp` remain separate lines (until PRD 4).
- `salt` (no quantity) in recipe A plus `salt, 1, tsp` in recipe B yields one line `salt — 1 tsp` with both recipes in its sources.
- Checking a line, then adding another recipe, keeps it checked.
- Copy with 2 of 8 lines checked places exactly 6 `- ` lines on the clipboard.

## Testing

- `tests/core/test_names.py` — table-driven over every rule and every `IRREGULAR`/`UNCHANGED` entry; multi-word names only change the last word.
- `tests/core/test_shopping.py` — grouping, summing, to-taste absorption (with and without a quantified group), counted vs unit-ed separation, unknown-unit case-insensitive grouping, sorting, sources ordering.
- `tests/core/test_quantity.py` — `format_quantity` table; `format_line` table including pluralization.
- `tests/ui/test_shopping_view.py` — smoke: add two recipes, list appears, check one, copy, assert clipboard text.
