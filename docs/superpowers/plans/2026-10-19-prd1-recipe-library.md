# PRD 1 — Recipe Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A PySide6 desktop app that imports recipes from CSV files or pasted spreadsheet rows through a validated, editable preview, stores them in local SQLite, and lets the user browse, view and delete them.

**Architecture:** Pure-Python `shopping_list/core/` (models, quantity parsing, unit aliases, validation, CSV import) with no Qt imports; `shopping_list/storage/` owns SQLite; `shopping_list/import_commit.py` applies a preview to storage with duplicate resolution in one transaction; `shopping_list/ui/` widgets hold no business logic.

**Tech Stack:** Python 3.11+, PySide6 ≥ 6.6, stdlib `sqlite3` / `csv` / `fractions`, pytest ≥ 8, pytest-qt ≥ 4.4.

**Spec:** `docs/superpowers/specs/2026-10-19-01-recipe-library-design.md` (with `docs/superpowers/specs/2026-10-19-00-overview.md` for architecture and schema).

## Global Constraints

- Quantities are `fractions.Fraction`, never `float`; stored in SQLite as `str(Fraction)` (`"3/2"`, `"2"`).
- `shopping_list/core/` must not import PySide6 or `sqlite3`.
- Required CSV columns, in this canonical order for messages: `recipe, servings, ingredient, quantity, unit`.
- Schema per overview: `recipes(id, name, servings CHECK > 0, created_at)`, `ingredients(id, recipe_id ON DELETE CASCADE, position, name, quantity NULL, unit NULL)`; migrations keyed on `PRAGMA user_version`; `PRAGMA foreign_keys = ON` on every connection.
- `recipes.name` is not unique.
- An import writes in exactly one transaction; any failure leaves the library unchanged.
- Database path: `QStandardPaths.AppDataLocation / "recipes.db"`; application name `Recipe Shopping List`.
- Run with `python -m shopping_list`.

## Review Focus

1. **Quoted cells containing commas** (`"salt, kosher"`) — must parse as one cell (Task 4 test `test_quoted_comma_cell`).
2. **Blank lines and all-blank rows** (trailing empty rows Excel exports, `,,,,`) — ignored, not reported as errors (Task 4 test `test_blank_rows_ignored`).
3. **Windows line endings** (`\r\n`) in files and pastes — parse identically (Task 4 test `test_crlf_line_endings`).
4. **Non-UTF-8 file** (old Excel "CSV" saved as cp1252, e.g. byte `0xBD` for ½) — file-level error with the save-as hint, never a crash (Task 4 test `test_non_utf8_file`).
5. **Pasted data without a header row** — file-level missing-columns error naming the required columns, not a preview of garbage (Task 4 test `test_paste_without_header`).

---

## File Structure

```
pyproject.toml
shopping_list/
  __init__.py
  __main__.py               # Task 10: app entry, DB path, open-failure dialog
  core/
    __init__.py
    models.py               # Task 1: Ingredient, Recipe, RecipeSummary
    quantity.py             # Task 1: parse_quantity, QuantityError
    units.py                # Task 2: canonical_unit
    validation.py           # Task 3: Issue, validate_row, validate_recipe, normalize_recipe_name
    importer.py             # Task 4: ImportPreview & friends, parse_csv_text/file, revalidate
    template.py             # Task 4: TEMPLATE_CSV
  storage/
    __init__.py
    db.py                   # Task 5: connect, migrations
    recipes.py              # Task 5: RecipeRepository
  import_commit.py          # Task 6: commit_import, DuplicateChoice, ImportResult
  ui/
    __init__.py
    recipe_table_editor.py  # Task 7
    import_dialog.py        # Task 8 (+ ask_duplicate)
    library_view.py         # Task 9
    main_window.py          # Task 10
tests/
  conftest.py
  core/test_quantity.py  core/test_units.py  core/test_validation.py  core/test_importer.py
  storage/test_recipes.py
  test_import_commit.py
  ui/test_recipe_table_editor.py  ui/test_import_dialog.py  ui/test_library_view.py  ui/test_main.py
```

---

### Task 1: Project scaffold, models, quantity parsing

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `shopping_list/__init__.py`, `shopping_list/core/__init__.py`, `shopping_list/core/models.py`, `shopping_list/core/quantity.py`, `tests/conftest.py`
- Test: `tests/core/test_quantity.py`

**Interfaces:**
- Produces:
  - `models.Ingredient(name: str, quantity: Fraction | None, unit: str | None)` — frozen dataclass
  - `models.Recipe(name: str, servings: int, ingredients: list[Ingredient], id: int | None = None)` — dataclass
  - `models.RecipeSummary(id: int, name: str, servings: int, ingredient_count: int)` — frozen dataclass
  - `quantity.parse_quantity(text: str) -> Fraction | None` — `None` for blank; raises `QuantityError`
  - `quantity.QuantityError(ValueError)`; `quantity.QUANTITY_ERROR_MESSAGE = "Quantity must be a single positive number, e.g. 2, 1/2, 1 1/2"`

- [ ] **Step 1: Scaffold.** `pyproject.toml`: project `shopping-list`, `requires-python = ">=3.11"`, dependency `PySide6>=6.6`, optional `dev = ["pytest>=8", "pytest-qt>=4.4"]`, setuptools package discovery for `shopping_list*`, and `[tool.pytest.ini_options] qt_api = "pyside6"`, `testpaths = ["tests"]`. `.gitignore`: `.venv/`, `__pycache__/`, `*.egg-info/`. Then:

Run: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
Expected: installs without error.

- [ ] **Step 2: Write the failing tests** in `tests/core/test_quantity.py`:

```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/pytest tests/core/test_quantity.py -v`
Expected: FAIL — `ModuleNotFoundError: shopping_list.core.quantity`

- [ ] **Step 4: Implement** `models.py` (the three dataclasses above) and `parse_quantity` in `quantity.py`. Approach: strip; collapse whitespace around `/`; one regex for `whole`, `whole frac`, `frac`, `decimal`, where `frac` is `n/d` or a single Unicode vulgar fraction from a `VULGAR` dict (½ ⅓ ⅔ ¼ ¾ ⅕ ⅖ ⅗ ⅘ ⅙ ⅚ ⅛ ⅜ ⅝ ⅞); decimals via `Fraction(str)`; reject zero denominator and values ≤ 0.

- [ ] **Step 5: Run tests** — `.venv/bin/pytest tests/core/test_quantity.py -v` → all PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore shopping_list tests
git commit -m "feat: project scaffold, recipe models and quantity parsing"
```

---

### Task 2: Unit canonicalization

**Files:**
- Create: `shopping_list/core/units.py`
- Test: `tests/core/test_units.py`

**Interfaces:**
- Produces: `canonical_unit(text: str) -> tuple[str | None, bool]` — returns `(canonical, True)` for a known alias, `(trimmed_original, False)` for unknown, `(None, True)` for blank. `CANONICAL_UNITS: tuple[str, ...]` = `("tsp","tbsp","fl oz","cup","pint","quart","gallon","ml","l","oz","lb","g","kg")`.

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/core/test_units.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement** with an `_ALIASES: dict[str, str]` keyed by lowercased alias, plus `_CASE_SENSITIVE = {"t": "tsp", "T": "tbsp"}` checked first on the exact text. Normalize lookup key by trimming, stripping one trailing `.`, collapsing internal whitespace, and removing `.` after `fl`.
- [ ] **Step 4: Run** → all PASS.
- [ ] **Step 5: Commit** — `git add shopping_list/core/units.py tests/core/test_units.py && git commit -m "feat: unit alias canonicalization"`

---

### Task 3: Shared row and recipe validation

**Files:**
- Create: `shopping_list/core/validation.py`
- Test: `tests/core/test_validation.py`

**Interfaces:**
- Consumes: `parse_quantity`, `QuantityError`, `QUANTITY_ERROR_MESSAGE` (Task 1); `canonical_unit` (Task 2); `Ingredient` (Task 1).
- Produces:
  - `Issue(level: Literal["error", "warning"], message: str, field: str | None)` — frozen dataclass; `field` ∈ `"recipe" | "servings" | "ingredient" | "quantity" | "unit" | None`
  - `validate_row(ingredient: str, quantity: str, unit: str) -> tuple[Ingredient | None, list[Issue]]` — `Ingredient` is `None` iff an error exists
  - `validate_recipe(name: str, servings: str, active_row_count: int) -> tuple[int | None, list[Issue]]`
  - `normalize_recipe_name(name: str) -> str` — trim, collapse whitespace, lowercase
  - Message constants (exact copy):
    - `INGREDIENT_REQUIRED = "Ingredient name is required"`
    - `RECIPE_NAME_REQUIRED = "Recipe name is required"`
    - `SERVINGS_INVALID = "Servings must be a whole number of 1 or more"`
    - `NO_INGREDIENTS = "Recipe has no ingredients"`
    - `UNKNOWN_UNIT = "Unknown unit '{unit}' — it will only combine with the same unit"`
    - `UNIT_WITHOUT_QUANTITY = "Unit has no quantity; treated as 'to taste'"`

- [ ] **Step 1: Write failing tests**

```python
from fractions import Fraction as F
from shopping_list.core.models import Ingredient
from shopping_list.core.validation import (validate_row, validate_recipe, normalize_recipe_name,
    Issue, INGREDIENT_REQUIRED, RECIPE_NAME_REQUIRED, SERVINGS_INVALID, NO_INGREDIENTS,
    UNKNOWN_UNIT, UNIT_WITHOUT_QUANTITY)
from shopping_list.core.quantity import QUANTITY_ERROR_MESSAGE

def test_valid_row():
    assert validate_row(" flour ", "1 1/2", "cups") == (Ingredient("flour", F(3, 2), "cup"), [])

def test_counted_and_to_taste():
    assert validate_row("egg", "1", "") == (Ingredient("egg", F(1), None), [])
    assert validate_row("salt", "", "") == (Ingredient("salt", None, None), [])

def test_blank_ingredient_error():
    ing, issues = validate_row("  ", "1", "cup")
    assert ing is None and issues == [Issue("error", INGREDIENT_REQUIRED, "ingredient")]

def test_bad_quantity_error():
    ing, issues = validate_row("milk", "1-2", "cup")
    assert ing is None and issues == [Issue("error", QUANTITY_ERROR_MESSAGE, "quantity")]

def test_unknown_unit_warning():
    ing, issues = validate_row("garlic", "4", "clove")
    assert ing == Ingredient("garlic", F(4), "clove")
    assert issues == [Issue("warning", UNKNOWN_UNIT.format(unit="clove"), "unit")]

def test_unit_without_quantity_warning():
    ing, issues = validate_row("salt", "", "tsp")
    assert ing == Ingredient("salt", None, "tsp")
    assert issues == [Issue("warning", UNIT_WITHOUT_QUANTITY, "unit")]

def test_multiple_errors_reported_together():
    _, issues = validate_row("", "x", "cup")
    assert {i.field for i in issues} == {"ingredient", "quantity"}

def test_recipe_valid():
    assert validate_recipe("Pancakes", " 4 ", 6) == (4, [])

def test_recipe_errors():
    assert validate_recipe("", "4", 1) == (4, [Issue("error", RECIPE_NAME_REQUIRED, "recipe")])
    for bad in ["", "0", "-2", "2.5", "four"]:
        assert validate_recipe("X", bad, 1) == (None, [Issue("error", SERVINGS_INVALID, "servings")])
    assert validate_recipe("X", "2", 0) == (2, [Issue("error", NO_INGREDIENTS, None)])

def test_normalize_recipe_name():
    assert normalize_recipe_name("  Garlic   Pasta ") == "garlic pasta"
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/core/test_validation.py -v` → FAIL.
- [ ] **Step 3: Implement** the functions above. Ingredient name is stored trimmed with internal whitespace collapsed; original case kept. Servings accepts only `str.strip()` matching `^\d+$` and > 0.
- [ ] **Step 4: Run** → all PASS.
- [ ] **Step 5: Commit** — `git add shopping_list/core/validation.py tests/core/test_validation.py && git commit -m "feat: shared row and recipe validation"`

---

### Task 4: CSV / paste importer and template

**Files:**
- Create: `shopping_list/core/importer.py`, `shopping_list/core/template.py`
- Test: `tests/core/test_importer.py`

**Interfaces:**
- Consumes: `validate_row`, `validate_recipe`, `normalize_recipe_name`, `Issue` (Task 3); `Recipe` (Task 1).
- Produces:
  - `PreviewRow(line_no: int, ingredient: str, quantity: str, unit: str, issues: list[Issue], parsed: Ingredient | None, skipped: bool = False)` — mutable dataclass; cell fields are raw strings the UI edits
  - `PreviewRecipe(name: str, servings: str, rows: list[PreviewRow], issues: list[Issue], parse_issues: list[Issue], parsed_servings: int | None, skipped: bool = False)` — `parse_issues` holds the servings-mismatch warning, preserved across `revalidate`; `issues` = `parse_issues` + `validate_recipe` result
  - `ImportPreview(file_issues: list[Issue], notices: list[str], recipes: list[PreviewRecipe])` with properties `active_recipes -> list[PreviewRecipe]` (non-skipped), `is_importable -> bool`, and method `to_recipes() -> list[Recipe]` (non-skipped recipes, non-skipped rows, in file order; raises `ValueError` if not importable)
  - `parse_csv_text(text: str) -> ImportPreview`, `parse_csv_file(path: Path) -> ImportPreview`, `revalidate(preview: ImportPreview) -> ImportPreview` (in place, returns same object)
  - Constants: `REQUIRED_COLUMNS = ("recipe", "servings", "ingredient", "quantity", "unit")`, `MISSING_COLUMNS = "Missing required column(s): {missing}. Required columns: recipe, servings, ingredient, quantity, unit"`, `NO_ROWS = "No recipe rows found. Required columns: recipe, servings, ingredient, quantity, unit"`, `NOT_UTF8 = "File is not valid UTF-8 text. Save it as 'CSV UTF-8' and try again."`, `IGNORED_COLUMNS = "Ignored columns: {columns}"`, `SERVINGS_MISMATCH = "Rows disagree on servings; using {servings}"`
  - `template.TEMPLATE_CSV: str` — exact contents of the spec's template block, ending in a newline

Behavioural decisions the tests pin:
- `is_importable` = no file-level errors **and** ≥ 1 active recipe **and** no error in any active recipe's `issues` or any non-skipped row's `issues`.
- Order of file-level checks: no non-blank line at all → `NO_ROWS`; else missing header columns → `MISSING_COLUMNS` (the first non-blank line is the header); else no non-blank data rows → `NO_ROWS`.
- Rows whose cells are all blank (after trimming) are dropped before grouping.
- Rows with a blank `recipe` cell group into one `PreviewRecipe` with `name=""`, which carries `RECIPE_NAME_REQUIRED` (the user fixes the name in the header or skips it) — this is how the spec's "blank recipe" row error surfaces.
- Recipe `servings` = first row value that is a valid positive integer, else the first row's raw value; if the recipe's rows hold differing non-blank servings values (computed once at parse time), add `SERVINGS_MISMATCH` warning (field `"servings"`) to `parse_issues`.
- Recipes appear in order of first occurrence; `name` is the first occurrence's trimmed spelling.
- `line_no` is the 1-based line in the source (header = line 1), taken from `csv.reader.line_num`.
- Delimiter: tab if the first line contains `\t`, else comma. Files are decoded with `utf-8-sig`.

- [ ] **Step 1: Write failing tests** (excerpt — every listed test must exist):

```python
from fractions import Fraction as F
from shopping_list.core.importer import (parse_csv_text, parse_csv_file, revalidate,
    MISSING_COLUMNS, NO_ROWS, NOT_UTF8, IGNORED_COLUMNS, SERVINGS_MISMATCH)
from shopping_list.core.template import TEMPLATE_CSV
from shopping_list.core.validation import UNKNOWN_UNIT, RECIPE_NAME_REQUIRED

H = "recipe,servings,ingredient,quantity,unit\n"

def test_template_imports_cleanly():
    p = parse_csv_text(TEMPLATE_CSV)
    assert [r.name for r in p.recipes] == ["Pancakes", "Garlic Pasta"]
    warnings = [i for r in p.recipes for row in r.rows for i in row.issues]
    assert [w.message for w in warnings] == [UNKNOWN_UNIT.format(unit="clove")]
    assert p.is_importable
    recipes = p.to_recipes()
    assert recipes[0].servings == 4 and len(recipes[0].ingredients) == 6
    assert recipes[0].ingredients[0].quantity == F(3, 2)

def test_tab_separated_paste_matches_csv():
    tsv = TEMPLATE_CSV.replace(",", "\t")
    assert parse_csv_text(tsv).to_recipes() == parse_csv_text(TEMPLATE_CSV).to_recipes()

def test_headers_case_insensitive_any_order_extra_ignored():
    p = parse_csv_text("Unit, Ingredient ,QUANTITY,notes,Servings,Recipe\ncup,milk,1,x,2,Soup\n")
    assert p.notices == [IGNORED_COLUMNS.format(columns="notes")]
    assert p.to_recipes()[0].ingredients[0].unit == "cup"

def test_missing_column_rejected():
    p = parse_csv_text("recipe,ingredient,quantity,unit\nA,b,1,\n")
    assert [i.message for i in p.file_issues] == [MISSING_COLUMNS.format(missing="servings")]
    assert not p.is_importable and p.recipes == []

def test_empty_file():
    assert [i.message for i in parse_csv_text("").file_issues] == [NO_ROWS]
    assert [i.message for i in parse_csv_text(H).file_issues] == [NO_ROWS]

def test_bom_file(tmp_path):
    f = tmp_path / "r.csv"; f.write_bytes(("﻿" + H + "A,1,egg,1,\n").encode())
    assert parse_csv_file(f).is_importable

def test_non_utf8_file(tmp_path):
    f = tmp_path / "r.csv"; f.write_bytes((H + "A,1,milk,").encode() + b"\xbd,cup\n")
    p = parse_csv_file(f)
    assert [i.message for i in p.file_issues] == [NOT_UTF8]

def test_non_contiguous_grouping_case_insensitive():
    p = parse_csv_text(H + "Soup,2,a,1,\nTea,1,b,1,\n soup ,2,c,1,\n")
    assert [(r.name, [x.ingredient for x in r.rows]) for r in p.recipes] == [("Soup", ["a", "c"]), ("Tea", ["b"])]

def test_servings_mismatch_warning_uses_first():
    p = parse_csv_text(H + "A,4,x,1,\nA,6,y,1,\n")
    assert p.recipes[0].parsed_servings == 4
    assert [i.message for i in p.recipes[0].issues] == [SERVINGS_MISMATCH.format(servings=4)]
    assert p.is_importable

def test_blank_recipe_name_groups_and_blocks():
    p = parse_csv_text(H + ",2,x,1,\nA,1,y,1,\n")
    assert p.recipes[0].name == "" and p.recipes[0].issues[0].message == RECIPE_NAME_REQUIRED
    assert not p.is_importable
    p.recipes[0].skipped = True
    assert revalidate(p).is_importable

def test_row_error_fix_and_skip():
    p = parse_csv_text(H + "A,1,milk,1-2,cup\nA,1,egg,1,\n")
    assert not p.is_importable
    p.recipes[0].rows[0].quantity = "2"
    assert revalidate(p).is_importable
    p.recipes[0].rows[0].quantity = "bad"; p.recipes[0].rows[0].skipped = True
    assert revalidate(p).is_importable and len(p.to_recipes()[0].ingredients) == 1

def test_all_recipes_skipped_not_importable():
    p = parse_csv_text(H + "A,1,egg,1,\n"); p.recipes[0].skipped = True
    assert not revalidate(p).is_importable

def test_line_numbers():
    p = parse_csv_text(H + "A,1,egg,1,\n\nA,1,milk,1,cup\n")
    assert [r.line_no for r in p.recipes[0].rows] == [2, 4]

# Review Focus tests
def test_quoted_comma_cell():
    p = parse_csv_text(H + 'A,1,"salt, kosher",1,tsp\n')
    assert p.to_recipes()[0].ingredients[0].name == "salt, kosher"

def test_blank_rows_ignored():
    p = parse_csv_text(H + "A,1,egg,1,\n,,,,\n\n   ,  ,,,\n")
    assert p.is_importable and len(p.recipes) == 1 and len(p.recipes[0].rows) == 1

def test_crlf_line_endings():
    assert parse_csv_text(TEMPLATE_CSV.replace("\n", "\r\n")).to_recipes() == parse_csv_text(TEMPLATE_CSV).to_recipes()

def test_paste_without_header():
    p = parse_csv_text("Pancakes\t4\tflour\t1 1/2\tcup\n")
    assert p.file_issues and p.file_issues[0].message.startswith("Missing required column(s): recipe, servings, ingredient, quantity, unit")
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/core/test_importer.py -v` → FAIL.
- [ ] **Step 3: Implement** `template.py` (copy the template block from the spec verbatim) and `importer.py` using `csv.reader` over `io.StringIO(text, newline="")` with the chosen delimiter. `MISSING_COLUMNS` lists missing names comma-separated in `REQUIRED_COLUMNS` order; ignored columns in header order. `revalidate` re-runs `validate_row` on every row and `validate_recipe(name, servings, active_row_count)` per recipe, setting `parsed`, `parsed_servings` and `issues`; `parse_csv_text` builds rows then calls `revalidate`.
- [ ] **Step 4: Run** → all PASS; then run the whole suite `.venv/bin/pytest -v` → all PASS.
- [ ] **Step 5: Commit** — `git add shopping_list/core/importer.py shopping_list/core/template.py tests/core/test_importer.py && git commit -m "feat: CSV and paste importer with validated preview"`

---

### Task 5: SQLite storage and recipe repository

**Files:**
- Create: `shopping_list/storage/__init__.py`, `shopping_list/storage/db.py`, `shopping_list/storage/recipes.py`
- Test: `tests/storage/test_recipes.py`

**Interfaces:**
- Consumes: `Recipe`, `Ingredient`, `RecipeSummary` (Task 1); `normalize_recipe_name` (Task 3).
- Produces:
  - `db.connect(path: str | Path) -> sqlite3.Connection` — accepts `":memory:"`; enables foreign keys; applies migrations
  - `db.MIGRATIONS: list[str]` — index *i* upgrades `user_version` *i* → *i+1*; PRD 1 ships one entry (both tables + index on `ingredients(recipe_id)`)
  - `RecipeRepository(conn: sqlite3.Connection)` with:
    - `transaction() -> ContextManager[None]` — commits on success, rolls back on exception
    - `add(recipe: Recipe) -> int`, `replace(existing_id: int, recipe: Recipe) -> int` (deletes existing, inserts new, returns new id), `delete(recipe_id: int) -> None`
    - `get(recipe_id: int) -> Recipe` (raises `KeyError` if missing; ingredients ordered by `position`; `id` set), `list_summaries() -> list[RecipeSummary]` (sorted by name, case-insensitive), `find_by_name(name: str) -> list[RecipeSummary]` (match on `normalize_recipe_name`)
  - Write methods do **not** commit; callers wrap them in `transaction()`.

- [ ] **Step 1: Write failing tests**

```python
import sqlite3, pytest
from fractions import Fraction as F
from shopping_list.core.models import Recipe, Ingredient, RecipeSummary
from shopping_list.storage.db import connect, MIGRATIONS
from shopping_list.storage.recipes import RecipeRepository

@pytest.fixture
def repo():
    return RecipeRepository(connect(":memory:"))

PANCAKES = Recipe("Pancakes", 4, [Ingredient("flour", F(3, 2), "cup"), Ingredient("egg", F(1), None), Ingredient("salt", None, None)])

def test_schema_version():
    conn = connect(":memory:")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

def test_migrations_idempotent_on_reopen(tmp_path):
    p = tmp_path / "r.db"; connect(p).close()
    assert connect(p).execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)

def test_add_get_roundtrip_exact(repo):
    with repo.transaction():
        rid = repo.add(PANCAKES)
    got = repo.get(rid)
    assert got.ingredients == PANCAKES.ingredients and got.servings == 4 and got.id == rid

def test_list_summaries_sorted(repo):
    with repo.transaction():
        repo.add(Recipe("tea", 1, [Ingredient("tea", F(1), None)])); repo.add(PANCAKES)
    assert [(s.name, s.ingredient_count) for s in repo.list_summaries()] == [("Pancakes", 3), ("tea", 1)]

def test_find_by_name_normalized_and_duplicates_allowed(repo):
    with repo.transaction():
        repo.add(PANCAKES); repo.add(PANCAKES)
    assert len(repo.find_by_name("  pancakes ")) == 2

def test_replace(repo):
    with repo.transaction():
        old = repo.add(PANCAKES)
        new = repo.replace(old, Recipe("Pancakes", 2, [Ingredient("milk", F(1), "cup")]))
    assert [s.id for s in repo.list_summaries()] == [new]
    with pytest.raises(KeyError):
        repo.get(old)

def test_delete_cascades(repo):
    with repo.transaction():
        rid = repo.add(PANCAKES)
    with repo.transaction():
        repo.delete(rid)
    assert repo.conn.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0] == 0

def test_transaction_rollback(repo):
    with pytest.raises(RuntimeError):
        with repo.transaction():
            repo.add(PANCAKES); raise RuntimeError
    assert repo.list_summaries() == []

def test_servings_check_constraint(repo):
    with pytest.raises(sqlite3.IntegrityError):
        with repo.transaction():
            repo.add(Recipe("Bad", 0, []))
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/storage -v` → FAIL.
- [ ] **Step 3: Implement.** Open connections with `isolation_level=None` (autocommit) and implement `transaction()` with explicit `BEGIN` / `COMMIT` / `ROLLBACK` so nesting mistakes are visible. `created_at` = `datetime.now(timezone.utc).isoformat()`. Quantity stored as `str(q)` or `NULL`; read back with `Fraction(text)`. `find_by_name` loads summaries and filters in Python with `normalize_recipe_name` (no SQL `lower()`, so Unicode case-folding matches core).
- [ ] **Step 4: Run** → all PASS.
- [ ] **Step 5: Commit** — `git add shopping_list/storage tests/storage && git commit -m "feat: SQLite storage and recipe repository"`

---

### Task 6: Commit an import with duplicate resolution

**Files:**
- Create: `shopping_list/import_commit.py`
- Test: `tests/test_import_commit.py`

**Interfaces:**
- Consumes: `ImportPreview.to_recipes()` (Task 4); `RecipeRepository` (Task 5); `RecipeSummary` (Task 1).
- Produces:
  - `DuplicateChoice(action: Literal["replace", "skip", "keep_both"], apply_to_all: bool = False)` — frozen dataclass
  - `Resolver = Callable[[Recipe, list[RecipeSummary]], DuplicateChoice | None]` — `None` means cancel
  - `ImportResult(added: int, replaced: int, skipped: int)` — frozen dataclass
  - `commit_import(preview: ImportPreview, repo: RecipeRepository, resolve: Resolver) -> ImportResult | None` — `None` if the user cancelled; nothing written in that case

Decisions: all duplicate questions are asked **before** any write; once a choice has `apply_to_all=True` it is reused for every later duplicate without calling `resolve`. **Replace** deletes every existing recipe matching the normalized name, then adds the new one (counted once in `replaced`). All writes happen inside one `repo.transaction()`; exceptions propagate after rollback.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from shopping_list.core.importer import parse_csv_text
from shopping_list.core.template import TEMPLATE_CSV
from shopping_list.storage.db import connect
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.import_commit import commit_import, DuplicateChoice, ImportResult

def fresh():
    return RecipeRepository(connect(":memory:"))

def never(*_):
    raise AssertionError("resolver should not be called")

def test_clean_import():
    repo = fresh()
    assert commit_import(parse_csv_text(TEMPLATE_CSV), repo, never) == ImportResult(2, 0, 0)
    assert len(repo.list_summaries()) == 2

def test_replace_all_on_reimport():
    repo = fresh(); commit_import(parse_csv_text(TEMPLATE_CSV), repo, never)
    calls = []
    def resolve(recipe, existing):
        calls.append(recipe.name); return DuplicateChoice("replace", apply_to_all=True)
    assert commit_import(parse_csv_text(TEMPLATE_CSV), repo, resolve) == ImportResult(0, 2, 0)
    assert calls == ["Pancakes"] and len(repo.list_summaries()) == 2

def test_skip_and_keep_both():
    repo = fresh(); commit_import(parse_csv_text(TEMPLATE_CSV), repo, never)
    choices = iter([DuplicateChoice("skip"), DuplicateChoice("keep_both")])
    assert commit_import(parse_csv_text(TEMPLATE_CSV), repo, lambda r, e: next(choices)) == ImportResult(1, 0, 1)
    assert len(repo.list_summaries()) == 3

def test_cancel_writes_nothing():
    repo = fresh(); commit_import(parse_csv_text(TEMPLATE_CSV), repo, never)
    choices = iter([DuplicateChoice("replace"), None])
    assert commit_import(parse_csv_text(TEMPLATE_CSV), repo, lambda r, e: next(choices)) is None
    assert len(repo.list_summaries()) == 2

def test_failure_mid_import_rolls_back(monkeypatch):
    repo = fresh(); real_add = repo.add; n = {"i": 0}
    def flaky(recipe):
        n["i"] += 1
        if n["i"] == 2: raise RuntimeError("disk full")
        return real_add(recipe)
    monkeypatch.setattr(repo, "add", flaky)
    with pytest.raises(RuntimeError):
        commit_import(parse_csv_text(TEMPLATE_CSV), repo, never)
    assert repo.list_summaries() == []

def test_not_importable_raises():
    with pytest.raises(ValueError):
        commit_import(parse_csv_text("recipe\n"), fresh(), never)
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_import_commit.py -v` → FAIL.
- [ ] **Step 3: Implement** `commit_import` as specified.
- [ ] **Step 4: Run** → all PASS.
- [ ] **Step 5: Commit** — `git add shopping_list/import_commit.py tests/test_import_commit.py && git commit -m "feat: transactional import commit with duplicate resolution"`

---

### Task 7: Reusable `RecipeTableEditor` widget

**Files:**
- Create: `shopping_list/ui/__init__.py`, `shopping_list/ui/recipe_table_editor.py`
- Test: `tests/ui/test_recipe_table_editor.py`

**Interfaces:**
- Consumes: `PreviewRow`, `Issue` (Tasks 3–4).
- Produces: `RecipeTableEditor(QWidget)`:
  - `__init__(self, show_skip: bool = True, parent: QWidget | None = None)`
  - `set_rows(rows: list[PreviewRow]) -> None` — displays rows; edits write back into the same `PreviewRow` objects
  - `refresh_issues() -> None` — repaints issue styling from the rows' current `issues` without rebuilding cells (keeps the edit cursor)
  - `rows_edited = Signal()` — emitted after any cell edit or skip toggle has been written back
  - Columns: `COL_INGREDIENT = 0`, `COL_QUANTITY = 1`, `COL_UNIT = 2`, `COL_SKIP = 3` (hidden when `show_skip=False`); headers `Ingredient`, `Quantity`, `Unit`, `Skip`
  - Styling: a cell whose field has an error gets background `ERROR_COLOR = QColor("#f8d7da")`; warning `WARNING_COLOR = QColor("#fff3cd")`; tooltip = that field's messages joined by newline. Issues with `field=None` style the ingredient cell. Skipped rows render in grey text.
  - Must not import anything from `import_dialog`.

- [ ] **Step 1: Write failing tests** (use the `qtbot` fixture):

```python
from shopping_list.core.importer import parse_csv_text, revalidate
from shopping_list.ui.recipe_table_editor import (RecipeTableEditor, COL_QUANTITY, COL_UNIT, COL_SKIP,
    ERROR_COLOR, WARNING_COLOR)

H = "recipe,servings,ingredient,quantity,unit\n"

def make(qtbot, text, **kw):
    p = parse_csv_text(text); w = RecipeTableEditor(**kw); qtbot.addWidget(w)
    w.set_rows(p.recipes[0].rows); return p, w

def test_error_and_warning_styling(qtbot):
    p, w = make(qtbot, H + "A,1,milk,1-2,cup\nA,1,garlic,4,clove\n")
    t = w.table
    assert t.item(0, COL_QUANTITY).background().color() == ERROR_COLOR
    assert "single positive number" in t.item(0, COL_QUANTITY).toolTip()
    assert t.item(1, COL_UNIT).background().color() == WARNING_COLOR

def test_edit_writes_back_and_signals(qtbot):
    p, w = make(qtbot, H + "A,1,milk,1-2,cup\n")
    with qtbot.waitSignal(w.rows_edited):
        w.table.item(0, COL_QUANTITY).setText("2")
    assert p.recipes[0].rows[0].quantity == "2"
    revalidate(p); w.refresh_issues()
    assert w.table.item(0, COL_QUANTITY).background().color() != ERROR_COLOR

def test_skip_toggle(qtbot):
    p, w = make(qtbot, H + "A,1,milk,1,cup\n")
    with qtbot.waitSignal(w.rows_edited):
        w.table.item(0, COL_SKIP).setCheckState(Qt.Checked)
    assert p.recipes[0].rows[0].skipped

def test_skip_column_hidden(qtbot):
    _, w = make(qtbot, H + "A,1,milk,1,cup\n", show_skip=False)
    assert w.table.isColumnHidden(COL_SKIP)
```
(Import `Qt` from `PySide6.QtCore`.)

- [ ] **Step 2: Run** `.venv/bin/pytest tests/ui/test_recipe_table_editor.py -v` → FAIL.
- [ ] **Step 3: Implement** with a `QTableWidget` exposed as `self.table`; block signals while populating and while `refresh_issues` restyles, so programmatic changes don't emit `rows_edited`.
- [ ] **Step 4: Run** → all PASS.
- [ ] **Step 5: Commit** — `git add shopping_list/ui tests/ui/test_recipe_table_editor.py && git commit -m "feat: reusable recipe table editor widget"`

---

### Task 8: Import dialog (file, paste, preview, duplicates)

**Files:**
- Create: `shopping_list/ui/import_dialog.py`
- Test: `tests/ui/test_import_dialog.py`

**Interfaces:**
- Consumes: `parse_csv_text`, `parse_csv_file`, `revalidate`, `ImportPreview` (Task 4); `commit_import`, `DuplicateChoice`, `Resolver`, `ImportResult` (Task 6); `RecipeRepository` (Task 5); `RecipeTableEditor` (Task 7).
- Produces:
  - `ImportDialog(QDialog)`: `__init__(self, repo: RecipeRepository, resolve: Resolver | None = None, parent=None)` — `resolve` defaults to `ask_duplicate` bound to the dialog
  - `load_text(text: str) -> None`, `load_file(path: Path) -> None` — parse and show the preview
  - Attributes for tests: `import_button: QPushButton`, `file_issue_label: QLabel`, `recipe_editors: list[RecipeTableEditor]`, `recipe_name_edits: list[QLineEdit]`, `recipe_servings_edits: list[QLineEdit]`, `recipe_skip_boxes: list[QCheckBox]`, `result: ImportResult | None`
  - `ask_duplicate(parent: QWidget, recipe: Recipe, existing: list[RecipeSummary]) -> DuplicateChoice | None` — modal box: text `"A recipe named '{name}' already exists."` (or `"{n} recipes named '{name}' already exist."` when more than one), buttons **Replace**, **Skip**, **Keep both**, **Cancel import**, checkbox **Apply to all remaining**

Layout: `QTabWidget` with **File** (drop zone label "Drop a .csv file here" + **Browse…** using `QFileDialog.getOpenFileName(filter="CSV files (*.csv)")`; the dialog accepts drops of a single local `.csv` URL) and **Paste** (`QPlainTextEdit` + **Preview** button). Below: `file_issue_label` (red, hidden when empty; notices shown in grey beneath it), a scroll area with one `QGroupBox` per recipe (name edit, servings edit, "Skip recipe" checkbox, `RecipeTableEditor`), a hint label with exact copy `"Tip: use fl oz for liquids — oz always means weight."`, and `import_button`. Button text: `"Import 1 recipe"` / `"Import {n} recipes"`; disabled unless `preview.is_importable`. Any edit (rows, name, servings, skip) → write into the preview, `revalidate`, `refresh_issues` on every editor, update the button and each group box's recipe-level issue line. Clicking Import → `commit_import`; on result store `self.result` and `accept()`; on `None` stay open; on `sqlite3.Error` show `QMessageBox.critical(self, "Import failed", f"Nothing was imported.\n\n{err}")` and stay open.

- [ ] **Step 1: Write failing tests**

```python
from shopping_list.core.template import TEMPLATE_CSV
from shopping_list.storage.db import connect
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.import_commit import DuplicateChoice, ImportResult
from shopping_list.ui.import_dialog import ImportDialog
from shopping_list.ui.recipe_table_editor import COL_QUANTITY

H = "recipe,servings,ingredient,quantity,unit\n"

def dialog(qtbot, resolve=None):
    repo = RecipeRepository(connect(":memory:")); d = ImportDialog(repo, resolve=resolve); qtbot.addWidget(d)
    return repo, d

def test_template_import(qtbot):
    repo, d = dialog(qtbot); d.load_text(TEMPLATE_CSV)
    assert d.import_button.isEnabled() and d.import_button.text() == "Import 2 recipes"
    d.import_button.click()
    assert d.result == ImportResult(2, 0, 0) and len(repo.list_summaries()) == 2

def test_file_error_shown(qtbot):
    _, d = dialog(qtbot); d.load_text("recipe,ingredient\nA,b\n")
    assert "Missing required column(s): servings, quantity, unit" in d.file_issue_label.text()
    assert not d.import_button.isEnabled()

def test_fix_cell_enables_import(qtbot):
    _, d = dialog(qtbot); d.load_text(H + "A,1,milk,1-2,cup\n")
    assert not d.import_button.isEnabled()
    d.recipe_editors[0].table.item(0, COL_QUANTITY).setText("2")
    assert d.import_button.isEnabled() and d.import_button.text() == "Import 1 recipe"

def test_fix_servings_and_skip_recipe(qtbot):
    _, d = dialog(qtbot); d.load_text(H + "A,x,egg,1,\nB,1,egg,1,\n")
    assert not d.import_button.isEnabled()
    d.recipe_servings_edits[0].setText("2")
    assert d.import_button.text() == "Import 2 recipes" and d.import_button.isEnabled()
    d.recipe_skip_boxes[0].setChecked(True)
    assert d.import_button.text() == "Import 1 recipe"

def test_duplicates_routed_to_resolver(qtbot):
    seen = []
    repo, d = dialog(qtbot, resolve=lambda r, e: seen.append(r.name) or DuplicateChoice("replace", True))
    d.load_text(TEMPLATE_CSV); d.import_button.click()
    d2 = ImportDialog(repo, resolve=d._resolve); qtbot.addWidget(d2)
    d2.load_text(TEMPLATE_CSV); d2.import_button.click()
    assert seen == ["Pancakes"] and d2.result == ImportResult(0, 2, 0)

def test_cancel_keeps_dialog_open(qtbot):
    repo, d = dialog(qtbot, resolve=lambda r, e: None)
    d.load_text(TEMPLATE_CSV); d.import_button.click()
    d2 = ImportDialog(repo, resolve=lambda r, e: None); qtbot.addWidget(d2)
    d2.load_text(TEMPLATE_CSV); d2.import_button.click()
    assert d2.result is None and len(repo.list_summaries()) == 2
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/ui/test_import_dialog.py -v` → FAIL.
- [ ] **Step 3: Implement** as described; store the resolver as `self._resolve`.
- [ ] **Step 4: Run** → all PASS.
- [ ] **Step 5: Manual check** — `python -c "from PySide6.QtWidgets import QApplication; from shopping_list.storage.db import connect; from shopping_list.storage.recipes import RecipeRepository; from shopping_list.ui.import_dialog import ImportDialog; a=QApplication([]); d=ImportDialog(RecipeRepository(connect(':memory:'))); d.show(); a.exec()"`; drag a `.csv` onto the File tab and confirm the preview appears; paste rows copied from a spreadsheet and press Preview.
- [ ] **Step 6: Commit** — `git add shopping_list/ui/import_dialog.py tests/ui/test_import_dialog.py && git commit -m "feat: import dialog with editable preview and duplicate prompt"`

---

### Task 9: Library view

**Files:**
- Create: `shopping_list/ui/library_view.py`
- Test: `tests/ui/test_library_view.py`

**Interfaces:**
- Consumes: `RecipeRepository` (Task 5); `ImportDialog` (Task 8); `TEMPLATE_CSV` (Task 4). Quantities display as `str(Fraction)` for now; PRD 2 adds `format_quantity`.
- Produces: `LibraryView(QWidget)`:
  - `__init__(self, repo: RecipeRepository, confirm: Callable[[str], bool] | None = None, parent=None)` — `confirm(message)` defaults to a Yes/No `QMessageBox.question`
  - `refresh() -> None`; `recipes_changed = Signal()` (emitted after import or delete; PRD 2 listens)
  - Test attributes: `filter_edit: QLineEdit`, `recipe_list: QListWidget` (item text `"{name} — serves {servings} · {n} ingredient"` with `s` appended when n ≠ 1, item data `Qt.UserRole` = recipe id), `detail_table: QTableWidget` (columns `Quantity`, `Unit`, `Ingredient`), `delete_button`, `import_button`, `template_button`, `empty_label: QLabel`
  - Exact copy: empty hint `"No recipes yet — Import a CSV or save the template to get started."`; delete prompt `"Delete '{name}'? This can't be undone."`
  - **Import…** opens `ImportDialog(repo, parent=self)`; on accept → `refresh()` + `recipes_changed`. **Save template…** → `QFileDialog.getSaveFileName(self, "Save template", "recipe-template.csv", "CSV files (*.csv)")` then writes `TEMPLATE_CSV` as UTF-8. Delete is disabled with no selection.

- [ ] **Step 1: Write failing tests**

```python
from fractions import Fraction as F
from shopping_list.core.models import Recipe, Ingredient
from shopping_list.storage.db import connect
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui.library_view import LibraryView

def seeded(qtbot, confirm=lambda m: True):
    repo = RecipeRepository(connect(":memory:"))
    with repo.transaction():
        repo.add(Recipe("Pancakes", 4, [Ingredient("flour", F(3, 2), "cup"), Ingredient("salt", None, None)]))
        repo.add(Recipe("Garlic Pasta", 2, [Ingredient("spaghetti", F(200), "g")]))
    v = LibraryView(repo, confirm=confirm); qtbot.addWidget(v); return repo, v

def test_empty_hint(qtbot):
    v = LibraryView(RecipeRepository(connect(":memory:"))); qtbot.addWidget(v); v.show()
    assert v.empty_label.isVisible() and v.recipe_list.count() == 0

def test_list_sorted_and_filter(qtbot):
    _, v = seeded(qtbot)
    assert [v.recipe_list.item(i).text() for i in range(2)] == [
        "Garlic Pasta — serves 2 · 1 ingredient", "Pancakes — serves 4 · 2 ingredients"]
    v.filter_edit.setText("PAN")
    visible = [v.recipe_list.item(i).text() for i in range(v.recipe_list.count()) if not v.recipe_list.item(i).isHidden()]
    assert visible == ["Pancakes — serves 4 · 2 ingredients"]

def test_detail_shows_ingredients(qtbot):
    _, v = seeded(qtbot); v.recipe_list.setCurrentRow(1)
    t = v.detail_table
    assert [t.item(0, c).text() for c in range(3)] == ["3/2", "cup", "flour"]
    assert [t.item(1, c).text() for c in range(3)] == ["", "", "salt"]

def test_delete_confirmed(qtbot):
    msgs = []
    repo, v = seeded(qtbot, confirm=lambda m: msgs.append(m) or True)
    v.recipe_list.setCurrentRow(1)
    with qtbot.waitSignal(v.recipes_changed):
        v.delete_button.click()
    assert msgs == ["Delete 'Pancakes'? This can't be undone."]
    assert [s.name for s in repo.list_summaries()] == ["Garlic Pasta"]

def test_delete_declined(qtbot):
    repo, v = seeded(qtbot, confirm=lambda m: False)
    v.recipe_list.setCurrentRow(0); v.delete_button.click()
    assert len(repo.list_summaries()) == 2

def test_delete_disabled_without_selection(qtbot):
    _, v = seeded(qtbot)
    assert not v.delete_button.isEnabled()
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/ui/test_library_view.py -v` → FAIL.
- [ ] **Step 3: Implement.** Delete runs inside `repo.transaction()`; on `sqlite3.Error` show `QMessageBox.critical(self, "Delete failed", str(err))`.
- [ ] **Step 4: Run** → all PASS.
- [ ] **Step 5: Commit** — `git add shopping_list/ui/library_view.py tests/ui/test_library_view.py && git commit -m "feat: recipe library view"`

---

### Task 10: Main window and app entry point

**Files:**
- Create: `shopping_list/ui/main_window.py`, `shopping_list/__main__.py`
- Test: `tests/ui/test_main.py`

**Interfaces:**
- Consumes: `connect` (Task 5), `RecipeRepository` (Task 5), `LibraryView` (Task 9).
- Produces:
  - `MainWindow(QMainWindow)`: `__init__(self, repo: RecipeRepository)`; window title `"Recipe Shopping List"`; central `QTabWidget` exposed as `self.tabs` with one tab **Library** (`self.library: LibraryView`). PRD 2 adds a Shopping tab.
  - `__main__.open_database(path: Path) -> sqlite3.Connection` — creates parent dirs, calls `connect`
  - `__main__.default_db_path() -> Path` — `Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "recipes.db"`
  - `__main__.main(argv: list[str] | None = None, db_path: Path | None = None) -> int` — sets `QApplication.setApplicationName("Recipe Shopping List")` before computing the default path; on `sqlite3.Error`/`OSError` from `open_database` shows `QMessageBox.critical(None, "Can't open recipes", f"Could not open the recipe database at:\n{path}\n\n{err}")` and returns `1`; otherwise shows the window and returns `app.exec()`

- [ ] **Step 1: Write failing tests**

```python
from shopping_list.storage.db import connect
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui.main_window import MainWindow
from shopping_list import __main__ as entry

def test_main_window(qtbot):
    w = MainWindow(RecipeRepository(connect(":memory:"))); qtbot.addWidget(w)
    assert w.windowTitle() == "Recipe Shopping List" and w.tabs.tabText(0) == "Library"

def test_open_database_creates_dirs(tmp_path):
    conn = entry.open_database(tmp_path / "a" / "b" / "recipes.db")
    assert (tmp_path / "a" / "b" / "recipes.db").exists(); conn.close()

def test_db_open_failure_shows_dialog_and_exits_1(qtbot, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(entry.QMessageBox, "critical", lambda *a: shown.append(a[2]))
    bad = tmp_path / "dir_not_file"; bad.mkdir()
    assert entry.main([], db_path=bad) == 1
    assert str(bad) in shown[0]
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/ui/test_main.py -v` → FAIL.
- [ ] **Step 3: Implement.** `main` reuses an existing `QApplication.instance()` if present (pytest-qt creates one). Guard the module with `if __name__ == "__main__": sys.exit(main())` so tests can import it.
- [ ] **Step 4: Run the full suite** — `.venv/bin/pytest -v` → all PASS.
- [ ] **Step 5: Manual acceptance run** — `.venv/bin/python -m shopping_list`; walk through the spec's acceptance criteria: Save template → Import it (2 recipes, one `clove` warning) → re-import and Replace all (still 2) → paste the template's rows copied from a spreadsheet → delete a recipe.
- [ ] **Step 6: Commit** — `git add shopping_list/ui/main_window.py shopping_list/__main__.py tests/ui/test_main.py && git commit -m "feat: main window and app entry point"`
