# PRD 1 — Recipe Library (CSV Import & Local Storage)

**Date:** 2026-10-19
**Depends on:** — (foundation)
**See also:** `2026-10-19-00-overview.md` for architecture and data model

## Problem

Before the app can build a shopping list it needs recipes. Users keep recipes
in spreadsheets; typing CSVs by hand is error-prone, and a silently bad import
(wrong quantity, typo'd unit, inconsistent servings) corrupts every list built
from it.

## Goals

- Get recipes from a spreadsheet into the app with minimal friction.
- Catch every data problem before anything is saved, and let the user fix it in place.
- Never leave the library half-imported.
- Provide a library screen to browse, view and delete recipes.

## Non-goals

- Editing a recipe after import (PRD 5).
- Shopping list generation (PRD 2).
- URL / free-text import, import history.

## User stories

1. As a user, I can save a template CSV so I know the expected format.
2. As a user, I can import a `.csv` file, or paste rows copied from Excel/Google Sheets.
3. As a user, I see a preview of what will be imported, with problems flagged per row, and can fix cells or skip rows before confirming.
4. As a user, if an imported recipe has the same name as one in my library, I choose to replace it, skip it, or keep both.
5. As a user, I can browse my recipes, filter by name, view a recipe's ingredients, and delete a recipe.

## Functional requirements

### CSV format

- Required columns: `recipe`, `servings`, `ingredient`, `quantity`, `unit`.
  Header names match case-insensitively after trimming, in any order.
- Unknown extra columns are ignored; the preview shows one notice listing them.
- One row per ingredient. Rows group into a recipe by the `recipe` cell
  (trimmed, case-insensitive); rows of a recipe need not be contiguous.
  Ingredient order within a recipe is the row order in the file.
- Encoding: UTF-8, with or without BOM (`utf-8-sig`).
- Pasted text: if the first line contains a tab, parse as tab-separated;
  otherwise comma-separated. Pasted text must include the header row.

### Quantity parsing (`core/quantity.py`)

Accepted forms, all producing an exact `Fraction`:

| Input | Value |
|---|---|
| `2` | 2 |
| `0.5`, `.5` | 1/2 |
| `1/2` | 1/2 |
| `1 1/2` | 3/2 |
| `½`, `1½`, `1 ½` | 1/2, 3/2, 3/2 (Unicode vulgar fractions ½ ⅓ ⅔ ¼ ¾ ⅕–⅘ ⅙ ⅚ ⅛ ⅜ ⅝ ⅞) |
| (blank) | `None` — "to taste" |

Anything else (ranges like `1-2`, words like `a few`, zero or negative values,
zero denominators) is an error with the message
"Quantity must be a single positive number, e.g. 2, 1/2, 1 1/2".

### Unit canonicalization (`core/units.py`)

Unit text is trimmed, a trailing `.` removed, and matched against an alias
table. Matching is case-insensitive **except** `t` (tsp) and `T` (tbsp).

| Canonical | Aliases |
|---|---|
| `tsp` | t, tsp, tsps, teaspoon, teaspoons |
| `tbsp` | T, tbsp, tbsps, tbs, tbl, tablespoon, tablespoons |
| `fl oz` | fl oz, fl. oz, floz, fluid ounce, fluid ounces |
| `cup` | c, cup, cups |
| `pint` | pt, pint, pints |
| `quart` | qt, quart, quarts |
| `gallon` | gal, gallon, gallons |
| `ml` | ml, milliliter, milliliters, millilitre, millilitres |
| `l` | l, liter, liters, litre, litres |
| `oz` | oz, ounce, ounces (always weight) |
| `lb` | lb, lbs, pound, pounds |
| `g` | g, gram, grams |
| `kg` | kg, kilogram, kilograms |

- Blank unit → `None` (counted item, e.g. "2 eggs").
- Unrecognized unit (e.g. `pinch`, `can`, `clove`) → stored exactly as
  written (trimmed) and flagged as a warning.

### Validation

| Level | Condition | Effect |
|---|---|---|
| File | Missing required column; empty file / no data rows; undecodable bytes | Import rejected before preview; message lists the required columns |
| Recipe | No row in the recipe has a valid positive whole-number `servings` | Recipe blocked until fixed or skipped |
| Row (error) | Blank `recipe`; blank `ingredient`; invalid quantity | Row blocked until fixed or skipped |
| Warning | Unknown unit; rows of one recipe disagree on `servings` (first valid value used); unit given but quantity blank | Shown, non-blocking |

Row- and recipe-level rules live in `core/validation.py` (`validate_row`,
`validate_recipe`) so PRD 5's editor reuses them unchanged; `core/importer.py`
handles file-level checks, parsing and grouping, and calls into it.

`core/importer.py` exposes:

```python
def parse_csv_text(text: str) -> ImportPreview: ...
def parse_csv_file(path: Path) -> ImportPreview: ...
def revalidate(preview: ImportPreview) -> ImportPreview: ...   # after edits
```

`ImportPreview` holds file-level issues, a list of `PreviewRecipe`
(name, servings, rows, recipe-level issues, skipped flag) and each
`PreviewRow` (raw cell strings, parsed values, issues, skipped flag).
`ImportPreview.is_importable` is true when there are no file-level errors and
no error on any non-skipped recipe or row.

### Preview screen (`ui/import_dialog.py`)

- Entry: **Import…** in the library opens a dialog with two tabs: *File*
  (drag-and-drop zone + Browse button) and *Paste* (multi-line text box +
  Preview button).
- The preview shows each recipe as a header (name, servings, skip-recipe
  checkbox) followed by its ingredient rows in a `RecipeTableEditor`.
- `RecipeTableEditor` (`ui/recipe_table_editor.py`) is a standalone,
  reusable widget: editable columns `ingredient`, `quantity`, `unit`, a
  per-row skip checkbox, and inline issue display (error = red cell +
  tooltip, warning = amber). It must not depend on the import dialog, as PRD 5 reuses it; the skip column is optional (`show_skip: bool = True`).
- Recipe name and servings are editable in the recipe header.
- Any edit re-runs validation for the affected recipe immediately.
- **Import N recipes** is disabled while `is_importable` is false; N counts
  non-skipped recipes.

### Duplicate handling

On confirm, each incoming recipe whose normalized name (trimmed, lowercase)
matches an existing recipe prompts: **Replace** (delete existing, insert
new), **Skip**, or **Keep both**, with an "Apply to all remaining" checkbox.
Cancelling the prompt cancels the whole import.

### Persistence

All inserts/replacements for one import run in a single SQLite transaction.
Any failure rolls back everything and shows the error; the preview stays open
so the user can retry.

`storage/recipes.py` — `RecipeRepository`:

```python
def add(recipe: Recipe) -> int
def replace(existing_id: int, recipe: Recipe) -> int
def list_summaries() -> list[RecipeSummary]       # id, name, servings, ingredient_count
def get(recipe_id: int) -> Recipe
def delete(recipe_id: int) -> None
def find_by_name(name: str) -> list[RecipeSummary] # normalized match
```

Writes take an optional connection/transaction so the importer can batch them.

### Library screen (`ui/library_view.py`)

- List of recipes: name, servings, ingredient count, sorted by name; a
  filter box narrows by substring of name (case-insensitive).
- Selecting a recipe shows its ingredients (quantity, unit, name) read-only.
- **Delete** asks "Delete '<name>'? This can't be undone." then deletes.
- Toolbar: **Import…**, **Save template…**.
- Empty library shows a hint: "No recipes yet — Import a CSV or save the template to get started."

### Template (`Save template…`)

Writes this file to a user-chosen path:

```csv
recipe,servings,ingredient,quantity,unit
Pancakes,4,flour,1 1/2,cup
Pancakes,4,milk,1 1/4,cup
Pancakes,4,egg,1,
Pancakes,4,sugar,1,tbsp
Pancakes,4,baking powder,3 1/2,tsp
Pancakes,4,salt,,
Garlic Pasta,2,spaghetti,200,g
Garlic Pasta,2,garlic,4,clove
Garlic Pasta,2,olive oil,3,tbsp
Garlic Pasta,2,parmesan,1/2,cup
```

(Shows: fractions, counted item with blank unit, "to taste" with blank
quantity, metric unit, and an unknown unit `clove`. Note for users in the app's help text: use `fl oz` for liquids — `oz` always means weight.)

## Acceptance criteria

- Importing the template produces a preview with 2 recipes, no errors, and one warning (unknown unit `clove`); confirming adds both to the library.
- Pasting the same content copied from a spreadsheet (tab-separated) yields an identical preview.
- A file missing the `servings` column is rejected with a message naming the required columns.
- A row with quantity `1-2` is flagged as an error; Import stays disabled until it is fixed or skipped.
- Fixing the cell to `2` clears the error without reopening the file.
- Re-importing the template prompts for both duplicates; choosing Replace for all leaves exactly 2 recipes.
- Simulated DB failure mid-import leaves the library unchanged.
- Deleting a recipe removes it and its ingredients.

## Testing

- `tests/core/test_quantity.py` — every row of the quantity table, plus each error case.
- `tests/core/test_units.py` — every alias, `t`/`T` case sensitivity, trailing period, unknown unit passthrough.
- `tests/core/test_validation.py` — every row and recipe rule.
- `tests/core/test_importer.py` — header matching, extra columns, BOM, tab vs comma detection, grouping non-contiguous rows, every validation rule, `revalidate` after edits.
- `tests/storage/test_recipes.py` — repository CRUD on in-memory SQLite, cascade delete, transaction rollback.
- `tests/ui/test_import_dialog.py` — smoke: load template, Import enabled, confirm adds to library.
