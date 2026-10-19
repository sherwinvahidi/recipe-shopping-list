# PRD 3 — Serving Scaling

**Date:** 2026-10-19
**Depends on:** PRD 2 (shopping list)
**See also:** `2026-10-19-00-overview.md`

## Problem

Recipes are written for a fixed number of servings, but the user may be
cooking for more or fewer people. Scaling each recipe by hand before shopping
is tedious and error-prone.

## Goals

- Let the user set target servings per selected recipe.
- Scale quantities exactly, then combine as in PRD 2.
- Show whole numbers for counted items on the shopping list, since you can't buy half an egg.

## Non-goals

- Changing a recipe's stored base servings (that's PRD 5's editor).
- Persisting target servings between sessions.
- Unit conversion of scaled results (PRD 4).

## User stories

1. As a user, each recipe I add to the shopping selection shows its servings, which I can change.
2. As a user, the shopping list updates immediately to reflect the new amounts.
3. As a user, counted items are rounded up to whole numbers so I know how many to buy, and I can see the exact amount if I want it.

## Functional requirements

### Selection model (`core/shopping.py`)

```python
@dataclass(frozen=True)
class Selection:
    recipe: Recipe
    target_servings: int          # 1..999

def build_shopping_list(selections: list[Selection]) -> list[ShoppingLine]
```

PRD 2's `build_shopping_list(recipes)` signature is replaced by this one; the
UI wraps each selected recipe as `Selection(recipe, recipe.servings)` by default.

`ShoppingLine` gains:

```python
    exact_quantity: Fraction | None   # summed scaled amount before rounding; None if no quantity
```

`quantity` holds the value to display (rounded for counted items, equal to
`exact_quantity` otherwise).

### Scaling

- Scale factor per recipe: `Fraction(target_servings, recipe.servings)` — exact.
- Each ingredient's quantity is multiplied by its recipe's factor **before**
  grouping. No-quantity ingredients stay no-quantity.
- Grouping and to-taste absorption are unchanged from PRD 2.

### Rounding counted items

- After grouping and summing, lines with `unit is None` and a quantity are
  rounded **up** to the next whole number: `quantity = ceil(exact_quantity)`.
- Rounding happens after summing, so 2½ onions from each of two recipes is 5,
  not 6.
- Lines with a unit (known or unknown) are never rounded here.

### UI changes (`ui/shopping_view.py`)

- Each selected recipe row gets a servings spin box (range 1–999), initialized
  to the recipe's base servings, with the base shown beside it ("serves 4 by default").
- Changing the value recomputes the list immediately; check states persist by key as in PRD 2.
- A rounded line (where `quantity != exact_quantity`) shows its exact amount
  in the tooltip: "Exact: 4½ · From: Pancakes".
- Copied text uses the rounded `quantity`.
- Target servings reset when a recipe is removed and re-added, and on app restart.

## Acceptance criteria

- Pancakes (base 4) at 4 servings produces the same list as PRD 2.
- Pancakes at 6 servings: flour `2¼ cups`, milk `1⅞ cups`, egg `2` (exact 1½, rounded up), sugar `1½ tbsp`, baking powder `5¼ tsp`, salt with no amount.
- Pancakes at 2 servings: egg `1` (exact ½).
- Two recipes each requiring 2½ (scaled) onions → `onion — 5`, no tooltip "Exact" (no rounding occurred).
- Two recipes requiring 1¼ and 1½ eggs → `egg — 3`, tooltip "Exact: 2¾".
- Changing servings keeps already-checked lines checked.

## Testing

- `tests/core/test_shopping.py` (extended) — scale factors up and down, factor 1 identity, exact fractional results (e.g. ⅓ cup × 3 = 1 cup), round-up after summing (not before), unit-ed lines untouched, no-quantity lines untouched.
- `tests/ui/test_shopping_view.py` (extended) — change servings spin box, assert list updates.
