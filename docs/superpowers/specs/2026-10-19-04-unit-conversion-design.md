# PRD 4 — Unit Conversion & Reduction

**Date:** 2026-10-19
**Depends on:** PRD 2 (shopping list); built after PRD 3 in the roadmap
**See also:** `2026-10-19-00-overview.md`

## Problem

After PRD 2, the same ingredient in different units shows as separate lines
(`milk — 1 cup`, `milk — 4 tbsp`), and totals land in awkward units
(`6 tsp` instead of `2 tbsp`). Recipes may also mix US and metric units.

## Goals

- Merge the same ingredient across units of the same dimension (volume or mass), across US and metric.
- Show every total as a **single, clean quantity in a single unit** that is easy to read in a store.
- Let the user choose US or metric output.

## Non-goals

- Volume ↔ mass conversion (needs per-ingredient density).
- Compound outputs such as "1 tbsp + 2 tsp" — explicitly rejected as hard to read.
- Converting unknown units (`clove`, `can`, `pinch`).

## User stories

1. As a user, `1 cup` milk from one recipe and `4 tbsp` from another shows as one line `milk — 1¼ cups`.
2. As a user, `6 tsp` shows as `2 tbsp`, but `5 tsp` stays `5 tsp` rather than an awkward fraction.
3. As a user, I set my preferred measurement system once and every list uses it.
4. As a user, I can tell when an amount was converted between systems and is therefore approximate.

## Functional requirements

### Unit table (`core/units.py`)

Each canonical unit from PRD 1 gets a dimension, system, and exact `Fraction`
factor to its dimension's base (volume base: `tsp`; mass base: `g`).

| Unit | Dimension | System | Factor to base |
|---|---|---|---|
| tsp | volume | US | 1 |
| tbsp | volume | US | 3 |
| fl oz | volume | US | 6 |
| cup | volume | US | 48 |
| pint | volume | US | 96 |
| quart | volume | US | 192 |
| gallon | volume | US | 768 |
| ml | volume | metric | 1 / 4.92892159375 (i.e. `Fraction(100000000000, 492892159375)`) |
| l | volume | metric | 1000 × ml factor |
| g | mass | metric | 1 |
| kg | mass | metric | 1000 |
| oz | mass | US | 28.349523125 (`Fraction(28349523125, 1000000000)`) |
| lb | mass | US | 16 × oz factor |

### Output ladders and clean steps

One table, `OUTPUT_LADDERS`, defines which units are used for display, from
largest to smallest, with the fractional steps that count as "clean" for
each. Tuning this table is the only change needed to adjust output behaviour.

| System / dimension | Ladder (largest → smallest) | Clean steps |
|---|---|---|
| US volume | gallon, quart, cup | ½, ⅓, ¼, ⅛ |
| | tbsp | ½ |
| | tsp | ½, ¼, ⅛ (floor unit) |
| US mass | lb | ½, ¼ |
| | oz | ½, ¼ (floor unit) |
| Metric volume | l, ml | see metric rule |
| Metric mass | kg, g | see metric rule |

A value is **clean in unit U** if `value_in_U × d` is a whole number for some
clean-step denominator `d` of U (whole numbers are always clean).

`fl oz` and `pint` are accepted as input but never chosen for output.

### Reduction rule (US)

In `core/reduce.py`, `reduce(total_in_base, ladder) -> (quantity, unit)`:

1. For each unit U in the ladder, largest first: if `value_in_U ≥ 1` and the
   value is clean in U, return it in U.
2. If no unit matched, return the value in the floor unit, rounded to the
   nearest step of the floor unit (⅛ tsp or ¼ oz). The result is never shown as 0:
   anything that rounds below the smallest step is shown as that step (⅛ tsp, ¼ oz).

| Total | Output | Why |
|---|---|---|
| 6 tsp | 2 tbsp | exact in tbsp |
| 20 tbsp (60 tsp) | 1¼ cups | exact in cups |
| 5 tsp | 5 tsp | ⁵⁄₃ tbsp not clean; 5 tsp clean |
| 18 tbsp (54 tsp) | 1⅛ cups | ⅛ is a clean cup step |
| 7 tbsp (21 tsp) | 7 tbsp | 7⁄16 cup < 1 |
| 16 cups | 1 gallon | exact |
| 4 cups | 1 quart | exact |
| 20 oz | 1¼ lb | clean lb step |
| 10 oz | 10 oz | ⅝ lb < 1 |
| 1/16 tsp | ⅛ tsp | floor minimum |

### Reduction rule (metric)

- Volume: if the total, rounded to whole ml, is ≥ 1000 ml, show in `l`; otherwise `ml`. Mass: same with g → `kg`.
- `ml` and `g` display rounded to the nearest whole number (minimum 1).
- `l` and `kg` display rounded to 2 decimal places, trailing zeros trimmed (`1.25 kg`, `2 l`).
- Metric quantities are shown as decimals, never as fractions.

### Merging

- Lines are grouped by `(name_key, dimension)` for known units, so all volume
  amounts of `milk` merge and all mass amounts of `flour` merge; volume and
  mass of the same ingredient remain two lines.
- Unknown units keep PRD 2 behaviour (group by exact lowercased unit text, no conversion, no reduction).
- Counted items (`unit=None`) keep PRD 3 behaviour (sum, round up).
- To-taste absorption (PRD 2) prefers the volume line, then mass, then counted, then unknown-unit, if several quantified lines share the name.
- `ShoppingLine.key` becomes `(name_key, dimension_or_unit_key)` so check
  states survive changes in the displayed unit.

### Output system and approximation

- New setting `units.system` ∈ {`us`, `metric`}, default `us`, stored in the
  `settings` table (migration 2) via `storage/settings.py`
  (`get(key, default) / set(key, value)`).
- **Preferences** dialog (menu: App → Preferences… on macOS, Edit → Preferences… elsewhere) with a single US / Metric radio choice. Changing it recomputes the open list.
- All known-unit totals are converted to the chosen system before reduction.
- `ShoppingLine` gains `approximate: bool`, true when any contributing amount
  was in the other system. Approximate values are rounded to the nearest
  clean step of the chosen unit (US) or per the metric rounding rule, and
  displayed with a leading `≈` (`milk — ≈ 1 cup`, `spaghetti — ≈ 7 oz`).
- Values whose contributions were all in the chosen system are exact (metric display rounding notwithstanding) and carry no `≈`.

For approximate US values, step 1 of the reduction rule tests each ladder
unit against the value rounded to that unit's nearest clean step (or whole
number) and picks the largest unit whose rounded value is ≥ 1 and within 5 %
of the true value; otherwise it falls through to step 2.

## Acceptance criteria

- `milk 1 cup` + `milk 4 tbsp` → `milk — 1¼ cups`.
- `baking powder 6 tsp` → `baking powder — 2 tbsp`; `5 tsp` → `baking powder — 5 tsp`.
- `flour 2 cups` + `flour 200 g` → two lines (volume and mass).
- `spaghetti 200 g` with system = US → `spaghetti — ≈ 7 oz` (7.05 oz rounded to the nearest ¼ oz gives 7; 7⁄16 lb is below 1).
- `olive oil 3 tbsp` with system = metric → `olive oil — ≈ 44 ml`.
- `sugar 500 g` + `sugar 750 g`, metric → `sugar — 1.25 kg`, no `≈`.
- `garlic 4 clove` remains `garlic — 4 clove`.
- Switching the preference keeps checked lines checked.

## Testing

- `tests/core/test_units.py` (extended) — every factor; round-trip US↔metric exactness on `Fraction`.
- `tests/core/test_reduce.py` — every row of the reduction examples table, the metric rules, floor minimum, approximate-value 5 % rule, and the acceptance criteria above.
- `tests/core/test_shopping.py` (extended) — dimension merging, volume/mass separation, unknown units untouched, to-taste preference order, `approximate` flag.
- `tests/storage/test_settings.py` — migration 2 on an existing PRD 1 database; get/set default.
- `tests/ui/test_preferences.py` — smoke: switch to metric, list text updates.
