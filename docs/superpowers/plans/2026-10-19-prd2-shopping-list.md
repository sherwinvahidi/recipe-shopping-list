# PRD 2 — Shopping List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A **Shopping** tab where the user picks recipes from the library and sees one combined, alphabetical shopping list that updates live. Lines can be checked off, and the unchecked lines can be copied as plain text.

**Architecture:** Three pure-Python additions to `shopping_list/core/`: `format_quantity` in `quantity.py`, ingredient-name normalization in `names.py`, and aggregation plus line formatting in `shopping.py`. A thin `ui/shopping_view.py` widget holds the selection and the check state and calls into `core`. `MainWindow` adds the tab and connects `LibraryView.recipes_changed` to it.

**Tech Stack:** Python 3.11+, PySide6 ≥ 6.6, stdlib `fractions`, pytest ≥ 8, pytest-qt ≥ 4.4.

**Spec:** `docs/superpowers/specs/2026-10-19-02-shopping-list-design.md` (with `docs/superpowers/specs/2026-10-19-00-overview.md` for architecture). Builds on the PRD 1 code (`feat/prd1-recipe-library`).

**Setup:** if the worktree has no `.venv`, run `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"` first. Baseline: `.venv/bin/pytest -q` → 185 passed.

## Global Constraints

- Quantities are `fractions.Fraction`, never `float`. That includes rounding for display.
- `shopping_list/core/` must not import PySide6 or `sqlite3`.
- Ingredient matching normalizes case, whitespace and plurals only. There are no aliases and no fuzzy matching: `yellow onion` ≠ `onion`.
- No servings scaling (PRD 3) and no unit conversion (PRD 4). `1 cup` and `4 tbsp` of milk stay as two lines.
- Line separator in display text: ` — ` (space, em dash, space). Copy prefix: `- `.
- Exact copy: empty selection `"Add recipes to build your shopping list."`; tooltip `"From: {a}, {b}"`; buttons `Add` / `Added` / `Remove` / `Copy list` / `Clear checks` / `Clear selection`; status `"Copied {n} items"` / `"Nothing left to copy"`.
- Check state lives only in memory (in the view). Nothing new is persisted, and there is no schema change.

**Deviations from the spec (decided here):**
- `format_line` lives in `core/shopping.py` and is tested in `tests/core/test_shopping.py`, not in `quantity.py`/`test_quantity.py`. It takes a `ShoppingLine`, and putting it in `quantity.py` would make the low-level module import `shopping.py`.
- Status text is singular for one item: `"Copied 1 item"`.
- A no-quantity entry that has a unit (`salt,,pinch`, which PRD 1 imports with a warning) is treated exactly like a blank-unit one. Its unit is ignored.
- `format_quantity` shows `<0.01` for a positive value that would otherwise round to `0`.

## Review Focus

1. **A recipe is deleted, or replaced by re-import, in the Library tab while it is selected in Shopping.** Its id is gone, and the Shopping tab must drop it and recompute without raising `KeyError`. Tests: Task 4 `test_refresh_library_drops_deleted_recipe`, Task 5 `test_library_change_refreshes_shopping`.
2. **Quantities with odd or tiny denominators** (`1/16 tsp`, `1/300 cup`, `2999/1000`). They must display as a readable non-zero decimal and never as `0` or `3.00`. Test: Task 1 `test_format_quantity` rows.
3. **The same ingredient listed twice in one recipe.** It shows as one summed line, and that recipe is named once in the sources. Test: Task 3 `test_sources_follow_selection_order_and_dedupe`.
4. **Two library recipes with the same name** (PRD 1's "keep both"). Each one is selected independently by id. Test: Task 4 `test_duplicate_named_recipes_selectable_separately`.
5. **Copy with nothing selected, or with every line checked.** Shows `"Nothing left to copy"` and leaves the clipboard untouched. Tests: Task 4 `test_copy_when_all_checked` and `test_copy_with_empty_selection`.

---

## File Structure

```
shopping_list/
  core/
    quantity.py        # Task 1: + format_quantity
    names.py           # Task 2: name_key, IRREGULAR, UNCHANGED
    shopping.py        # Task 3: ShoppingLine, build_shopping_list, format_line
  ui/
    library_view.py    # Task 1: detail table uses format_quantity
    shopping_view.py   # Task 4: ShoppingView
    main_window.py     # Task 5: Shopping tab + wiring + status bar
tests/
  core/test_quantity.py     # Task 1 (extend)
  core/test_names.py        # Task 2
  core/test_shopping.py     # Task 3
  ui/test_library_view.py   # Task 1 (one assertion changes)
  ui/test_shopping_view.py  # Task 4
  ui/test_main.py           # Task 5 (extend)
```

---

### Task 1: `format_quantity` and the library detail view

**Files:**
- Modify: `shopping_list/core/quantity.py`, `shopping_list/ui/library_view.py` (`_sync_detail`)
- Test: `tests/core/test_quantity.py`, `tests/ui/test_library_view.py`

**Interfaces:**
- Consumes: `quantity.VULGAR` (existing glyph → `Fraction` dict).
- Produces: `quantity.format_quantity(q: Fraction) -> str` for `q > 0`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/core/test_quantity.py`:

```python
from shopping_list.core.quantity import format_quantity

@pytest.mark.parametrize("q,text", [
    (F(3), "3"), (F(1000), "1000"), (F(3, 2), "1½"), (F(2, 3), "⅔"), (F(19, 8), "2⅜"),
    (F(1, 4), "¼"), (F(7, 4), "1¾"), (F(1, 8), "⅛"), (F(4, 3), "1⅓"),
    (F(5, 6), "0.83"), (F(7, 6), "1.17"), (F(3, 5), "0.6"), (F(1, 16), "0.06"),
    (F(1, 200), "0.01"), (F(1, 300), "<0.01"), (F(2999, 1000), "3"),
])
def test_format_quantity(q, text):
    assert format_quantity(q) == text
```

In `tests/ui/test_library_view.py::test_detail_shows_ingredients`, change the expected first row to `["1½", "cup", "flour"]`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/core/test_quantity.py tests/ui/test_library_view.py -v`
Expected: FAIL. `ImportError: cannot import name 'format_quantity'`, and the detail row still shows `3/2`.

- [ ] **Step 3: Implement `format_quantity(q: Fraction) -> str`** in `quantity.py`, using these rules:
  - denominator 1 → `str(numerator)`.
  - denominator in {2, 3, 4, 8} → whole part, then the glyph for the remainder, taken from a module-level inverse of `VULGAR`. Leave out the whole part when it is 0.
  - otherwise → `h = floor(q * 100 + Fraction(1, 2))` (exact, half-up). If `h == 0`, return `"<0.01"`. Otherwise format `f"{h // 100}.{h % 100:02d}"` and strip trailing `0`s, then a trailing `.`.

  In `LibraryView._sync_detail`, the quantity cell becomes `"" if ing.quantity is None else format_quantity(ing.quantity)`.

- [ ] **Step 4: Run tests.** `.venv/bin/pytest tests/core/test_quantity.py tests/ui/test_library_view.py -v` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add shopping_list/core/quantity.py shopping_list/ui/library_view.py tests/core/test_quantity.py tests/ui/test_library_view.py
git commit -m "feat: format_quantity with vulgar fractions; use it in library detail"
```

---

### Task 2: Ingredient name normalization

**Files:**
- Create: `shopping_list/core/names.py`
- Test: `tests/core/test_names.py`

**Interfaces:**
- Produces:
  - `names.name_key(name: str) -> str`
  - `names.IRREGULAR: dict[str, str]` = `{"leaves": "leaf", "halves": "half", "loaves": "loaf", "cookies": "cookie", "brownies": "brownie", "veggies": "veggie"}`
  - `names.UNCHANGED: set[str]` = `{"molasses", "swiss", "grits", "series"}`

- [ ] **Step 1: Write the failing tests** in `tests/core/test_names.py`:

```python
import pytest
from shopping_list.core.names import IRREGULAR, UNCHANGED, name_key

@pytest.mark.parametrize("name,key", [
    ("  Olive   Oil ", "olive oil"), ("EGG", "egg"), ("", ""),          # step 1
    ("gas", "gas"), ("abs", "abs"),                                       # ≤ 3 letters
    ("berries", "berry"), ("anchovies", "anchovy"),                       # ies → y
    ("tomatoes", "tomato"), ("potatoes", "potato"),                       # oes
    ("peaches", "peach"), ("radishes", "radish"), ("glasses", "glass"),
    ("boxes", "box"), ("topazes", "topaz"),                               # ches/shes/sses/xes/zes
    ("asparagus", "asparagus"), ("hummus", "hummus"), ("couscous", "couscous"),
    ("watercress", "watercress"), ("pastis", "pastis"),                   # ss/us/is
    ("onions", "onion"), ("eggs", "egg"), ("peas", "pea"), ("cloves", "clove"),  # s
    ("onion", "onion"), ("leaf", "leaf"),                                 # already singular
    ("green onions", "green onion"), ("Bay Leaves", "bay leaf"),
    ("peas and carrots", "peas and carrot"), ("cherry  tomatoes", "cherry tomato"),  # last word only
])
def test_name_key(name, key):
    assert name_key(name) == key

@pytest.mark.parametrize("plural,singular", sorted(IRREGULAR.items()))
def test_every_irregular_entry(plural, singular):
    assert name_key(plural) == singular and name_key(singular) == singular
    assert name_key(f"fresh {plural}") == f"fresh {singular}"

@pytest.mark.parametrize("word", sorted(UNCHANGED))
def test_every_unchanged_entry(word):
    assert name_key(word) == word and name_key(word.title()) == word
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/core/test_names.py -v`
Expected: FAIL with `ModuleNotFoundError: shopping_list.core.names`

- [ ] **Step 3: Implement `name_key`** following the spec's steps 1–3 in the spec's rule order: IRREGULAR, then UNCHANGED or ≤ 3 letters, then `ies`, `oes`, `ches|shes|sses|xes|zes`, `ss|us|is`, `s`. Use `str.lower()` and `str.split()`, and apply the rules to the last word only.

- [ ] **Step 4: Run tests.** `.venv/bin/pytest tests/core/test_names.py -v` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add shopping_list/core/names.py tests/core/test_names.py
git commit -m "feat: ingredient name normalization (case, whitespace, plurals)"
```

---

### Task 3: Aggregation and line formatting

**Files:**
- Create: `shopping_list/core/shopping.py`
- Test: `tests/core/test_shopping.py`

**Interfaces:**
- Consumes: `name_key` (Task 2); `format_quantity` (Task 1); `units.canonical_unit(text) -> (str | None, bool)` and `models.Recipe` / `models.Ingredient` (PRD 1).
- Produces:
  - `ShoppingLine`: a frozen dataclass with exactly the spec's fields, in this order: `key: tuple[str, str | None]`, `display_name: str`, `quantity: Fraction | None`, `unit: str | None`, `sources: tuple[str, ...]`
  - `build_shopping_list(recipes: list[Recipe]) -> list[ShoppingLine]`
  - `format_line(line: ShoppingLine) -> str`
  - `PLURAL_UNITS = frozenset({"cup", "pint", "quart", "gallon"})`

- [ ] **Step 1: Write the failing tests** in `tests/core/test_shopping.py`:

```python
import pytest
from fractions import Fraction as F
from shopping_list.core.importer import parse_csv_text
from shopping_list.core.models import Ingredient as I, Recipe
from shopping_list.core.shopping import ShoppingLine, build_shopping_list, format_line
from shopping_list.core.template import TEMPLATE_CSV

def R(name, *ings): return Recipe(name, 2, list(ings))
def texts(recipes): return [format_line(l) for l in build_shopping_list(recipes)]
def L(name, q, unit): return ShoppingLine((name, unit), name, q, unit, ("A",))

def test_template_pancakes_alone():
    pancakes = parse_csv_text(TEMPLATE_CSV).to_recipes()[0]
    assert texts([pancakes]) == ["baking powder — 3½ tsp", "egg — 1", "flour — 1½ cups",
                                 "milk — 1¼ cups", "salt", "sugar — 1 tbsp"]

def test_same_name_and_unit_merge_across_case_and_alias():
    lines = build_shopping_list([R("A", I("olive oil", F(2), "tbsp")),
                                 R("B", I("Olive Oil", F(1), "tablespoon"))])
    assert [format_line(l) for l in lines] == ["olive oil — 3 tbsp"]
    assert lines[0].key == ("olive oil", "tbsp") and lines[0].sources == ("A", "B")

def test_plural_forms_merge_first_spelling_wins():
    assert texts([R("A", I("onions", F(2), None)), R("B", I("onion", F(1), None))]) == ["onions — 3"]

def test_more_specific_name_stays_separate():
    assert texts([R("A", I("yellow onion", F(1), None)), R("B", I("onion", F(1), None))]) == [
        "onion — 1", "yellow onion — 1"]

def test_different_units_stay_separate():
    assert texts([R("A", I("milk", F(1), "cup")), R("B", I("milk", F(4), "tbsp"))]) == [
        "milk — 1 cup", "milk — 4 tbsp"]

def test_counted_and_unit_never_merge():
    assert texts([R("A", I("garlic", F(2), None)), R("B", I("garlic", F(4), "clove"))]) == [
        "garlic — 2", "garlic — 4 clove"]

def test_to_taste_absorbed_into_quantified_line():
    lines = build_shopping_list([R("A", I("salt", None, None)), R("B", I("Salt", F(1), "tsp"))])
    assert [format_line(l) for l in lines] == ["salt — 1 tsp"]
    assert lines[0].key == ("salt", "tsp") and lines[0].sources == ("A", "B")

def test_to_taste_absorbed_into_first_in_sort_order():
    lines = build_shopping_list([R("A", I("milk", F(4), "tbsp"), I("milk", F(1), "cup")),
                                 R("B", I("milk", None, None))])
    assert [(l.unit, l.sources) for l in lines] == [("cup", ("A", "B")), ("tbsp", ("A",))]

def test_to_taste_only_entries_become_one_line():
    lines = build_shopping_list([R("A", I("pepper", None, None)), R("B", I("Pepper", None, "pinch"))])
    assert lines == [ShoppingLine(("pepper", None), "pepper", None, None, ("A", "B"))]

def test_unknown_unit_groups_case_insensitively():
    lines = build_shopping_list([R("A", I("garlic", F(2), "Clove")), R("B", I("garlic", F(1), "clove "))])
    assert [(l.key, l.quantity, l.unit) for l in lines] == [(("garlic", "clove"), F(3), "Clove")]

def test_sorted_case_insensitively():
    assert texts([R("A", I("Zucchini", F(1), None), I("apple", F(2), None), I("Banana", F(3), None))]) == [
        "apple — 2", "Banana — 3", "Zucchini — 1"]

def test_sources_follow_selection_order_and_dedupe():
    lines = build_shopping_list([R("B", I("egg", F(1), None)),
                                 R("A", I("egg", F(2), None), I("eggs", F(1), None))])
    assert len(lines) == 1 and lines[0].quantity == F(4) and lines[0].sources == ("B", "A")

def test_empty_selection():
    assert build_shopping_list([]) == []

@pytest.mark.parametrize("line,text", [
    (L("olive oil", F(5), "tbsp"), "olive oil — 5 tbsp"),
    (L("milk", F(3, 2), "cup"), "milk — 1½ cups"),
    (L("milk", F(1), "cup"), "milk — 1 cup"),
    (L("milk", F(1, 2), "cup"), "milk — ½ cup"),
    (L("egg", F(3), None), "egg — 3"),
    (L("salt", None, None), "salt"),
    (L("garlic", F(4), "clove"), "garlic — 4 clove"),
    (L("stock", F(2), "pint"), "stock — 2 pints"),
    (L("stock", F(3), "quart"), "stock — 3 quarts"),
    (L("water", F(2), "gallon"), "water — 2 gallons"),
    (L("cream", F(2), "fl oz"), "cream — 2 fl oz"),
    (L("beef", F(2), "lb"), "beef — 2 lb"),
    (L("flour", F(500), "g"), "flour — 500 g"),
    (L("sugar", F(2), "tsp"), "sugar — 2 tsp"),
])
def test_format_line(line, text):
    assert format_line(line) == text
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/core/test_shopping.py -v`
Expected: FAIL with `ModuleNotFoundError: shopping_list.core.shopping`

- [ ] **Step 3: Implement `build_shopping_list`** with this algorithm. The signature alone doesn't determine it:
  1. Unit key: `None` for a `None` or blank unit. Otherwise call `canonical_unit(unit)`: a known unit gives the canonical name; an unknown one gives `" ".join(raw.split()).lower()`. The **displayed** unit is the canonical name for a known unit, or the first raw spelling (trimmed) for an unknown one.
  2. Walk the recipes in order (index `r`) and their ingredients in order (index `p`). An ingredient with a quantity joins the group `(name_key(name), unit_key)`, and its quantity is added to the group's sum. An ingredient without one is held per `name_key` as a to-taste entry. Each entry records `(r, p, name, recipe.name)`.
  3. For each `name_key` that has to-taste entries: if any quantified group shares that `name_key`, add the entries to the group that sorts first. Sort keys are computed **before** any absorption. The entries add to `sources` but not to the quantity. If no quantified group shares it, the entries form one group with key `(nk, None)` and `quantity = unit = None`.
  4. For each group, order all of its entries, absorbed ones included, by `(r, p)`. `display_name` is the first entry's name. `sources` is the recipe names in that order, deduplicated.
  5. Sort by `(display_name.casefold(), "" if unit is None else unit.casefold())`.

  **`format_line`:** if `quantity is None`, return `display_name`. Otherwise `f"{display_name} — {format_quantity(q)}"`, followed by `f" {unit}"` plus `"s"` when `unit in PLURAL_UNITS and q > 1`, if the line has a unit.

- [ ] **Step 4: Run tests.** `.venv/bin/pytest tests/core -v` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add shopping_list/core/shopping.py tests/core/test_shopping.py
git commit -m "feat: aggregate selected recipes into a shopping list"
```

---

### Task 4: Shopping view

**Files:**
- Create: `shopping_list/ui/shopping_view.py`
- Test: `tests/ui/test_shopping_view.py`

**Interfaces:**
- Consumes: `RecipeRepository.list_summaries()` / `.get(id)`, which raises `KeyError` when the id is missing (PRD 1); `build_shopping_list`, `format_line` and `ShoppingLine.key` (Task 3).
- Produces: `ShoppingView(QWidget)`:
  - `__init__(self, repo: RecipeRepository, parent=None)` — builds the widgets, then calls `refresh_library()`
  - `status_message = Signal(str)` (Task 5 connects it to the status bar)
  - `refresh_library() -> None`: reloads the library rows, re-fetches every selected recipe by id, drops any that raise `KeyError`, and recomputes. Task 5 connects `LibraryView.recipes_changed` to it.
  - `add_recipe(recipe_id: int)` (a no-op when already selected), `remove_recipe(recipe_id: int)`, `clear_selection()`, `clear_checks()`, `copy_list()`, `selected_ids() -> list[int]` (in selection order)
  - `add_button(recipe_id) -> QPushButton` and `remove_button(recipe_id) -> QPushButton`, which raise `KeyError` when that row doesn't exist
  - Widgets: `filter_edit` (placeholder `"Filter recipes"`, case-insensitive substring match on the name, as in PRD 1); `library_list: QListWidget` with rows `"{name} — serves {servings}"` and an **Add** button per row, which shows `"Added"` and is disabled while that recipe is selected; `selected_list: QListWidget` with the recipe name and a **Remove** button per row; `list_widget: QListWidget` with one checkable item per line (text `format_line(line)`, `Qt.UserRole` = `line.key`, tooltip `"From: " + ", ".join(line.sources)`); `empty_label` (`EMPTY_SELECTION`, visible only while the selection is empty); `copy_button`, `clear_checks_button`, `clear_selection_button`
  - Module constant `EMPTY_SELECTION = "Add recipes to build your shopping list."`

Behaviour:
- Check state is `self._checked: set[key]`, updated from `list_widget.itemChanged`. On every recompute, rebuild the items with signals blocked, restore the checks for keys that are still present, and drop the keys that are gone. Checked items get `font.setStrikeOut(True)` and the palette's disabled text colour.
- **Copy list:** `n` unchecked lines → `QGuiApplication.clipboard().setText("\n".join("- " + format_line(l) for l in unchecked))`, then emit `"Copied {n} item"` + `"s"` when n ≠ 1. When n is 0 (everything checked, or nothing selected), emit `"Nothing left to copy"` and leave the clipboard alone.

- [ ] **Step 1: Write the failing tests** in `tests/ui/test_shopping_view.py`:

```python
from fractions import Fraction as F
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from shopping_list.core.models import Ingredient as I, Recipe
from shopping_list.storage.db import connect
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui.shopping_view import EMPTY_SELECTION, ShoppingView

ALL = ["baking powder — 3½ tsp", "bread — 2", "butter — 1 tbsp", "egg — 3", "flour — 1½ cups",
       "milk — 1¼ cups", "salt", "sugar — 1 tbsp"]

def seeded(qtbot):
    repo = RecipeRepository(connect(":memory:"))
    with repo.transaction():
        pancakes = repo.add(Recipe("Pancakes", 4, [
            I("flour", F(3, 2), "cup"), I("milk", F(5, 4), "cup"), I("egg", F(1), None),
            I("sugar", F(1), "tbsp"), I("baking powder", F(7, 2), "tsp"), I("salt", None, None)]))
        toast = repo.add(Recipe("Toast", 2, [I("bread", F(2), None), I("butter", F(1), "tbsp"),
                                             I("eggs", F(2), None)]))
    v = ShoppingView(repo); qtbot.addWidget(v)
    return repo, v, pancakes, toast

def texts(v): return [v.list_widget.item(i).text() for i in range(v.list_widget.count())]
def item(v, text): return v.list_widget.findItems(text, Qt.MatchExactly)[0]

def test_empty_selection_hint(qtbot):
    _, v, *_ = seeded(qtbot); v.show()
    assert v.empty_label.isVisible() and v.empty_label.text() == EMPTY_SELECTION
    assert v.list_widget.count() == 0

def test_add_two_recipes_builds_list(qtbot):
    _, v, pancakes, toast = seeded(qtbot); v.show()
    v.add_button(pancakes).click(); v.add_button(toast).click()
    assert texts(v) == ALL and not v.empty_label.isVisible()
    assert v.add_button(pancakes).text() == "Added" and not v.add_button(pancakes).isEnabled()
    assert item(v, "egg — 3").toolTip() == "From: Pancakes, Toast"
    assert v.selected_ids() == [pancakes, toast]

def test_add_twice_is_noop(qtbot):
    _, v, pancakes, _ = seeded(qtbot)
    v.add_recipe(pancakes); v.add_recipe(pancakes)
    assert v.selected_ids() == [pancakes] and v.selected_list.count() == 1

def test_check_survives_adding_recipe(qtbot):
    _, v, pancakes, toast = seeded(qtbot)
    v.add_recipe(pancakes); item(v, "salt").setCheckState(Qt.Checked)
    v.add_recipe(toast)
    salt = item(v, "salt")
    assert salt.checkState() == Qt.Checked and salt.font().strikeOut()

def test_removed_line_loses_check(qtbot):
    _, v, pancakes, toast = seeded(qtbot)
    v.add_recipe(toast); item(v, "bread — 2").setCheckState(Qt.Checked)
    v.remove_recipe(toast); v.add_recipe(toast)
    assert item(v, "bread — 2").checkState() == Qt.Unchecked

def test_copy_unchecked(qtbot):
    _, v, pancakes, toast = seeded(qtbot)
    v.add_recipe(pancakes); v.add_recipe(toast)
    item(v, "egg — 3").setCheckState(Qt.Checked); item(v, "salt").setCheckState(Qt.Checked)
    with qtbot.waitSignal(v.status_message) as sig:
        v.copy_button.click()
    assert sig.args == ["Copied 6 items"]
    expected = [t for t in ALL if t not in ("egg — 3", "salt")]
    assert QGuiApplication.clipboard().text() == "\n".join("- " + t for t in expected)

def test_copy_single_item_message(qtbot):
    _, v, _, toast = seeded(qtbot)
    v.add_recipe(toast)
    for t in ("butter — 1 tbsp", "eggs — 2"):
        item(v, t).setCheckState(Qt.Checked)
    with qtbot.waitSignal(v.status_message) as sig:
        v.copy_list()
    assert sig.args == ["Copied 1 item"] and QGuiApplication.clipboard().text() == "- bread — 2"

def test_copy_when_all_checked(qtbot):
    _, v, _, toast = seeded(qtbot)
    v.add_recipe(toast)
    for i in range(v.list_widget.count()):
        v.list_widget.item(i).setCheckState(Qt.Checked)
    QGuiApplication.clipboard().setText("sentinel")
    with qtbot.waitSignal(v.status_message) as sig:
        v.copy_list()
    assert sig.args == ["Nothing left to copy"] and QGuiApplication.clipboard().text() == "sentinel"

def test_copy_with_empty_selection(qtbot):
    _, v, *_ = seeded(qtbot)
    QGuiApplication.clipboard().setText("sentinel")
    with qtbot.waitSignal(v.status_message) as sig:
        v.copy_list()
    assert sig.args == ["Nothing left to copy"] and QGuiApplication.clipboard().text() == "sentinel"

def test_clear_checks_and_selection(qtbot):
    _, v, pancakes, toast = seeded(qtbot); v.show()
    v.add_recipe(pancakes); v.add_recipe(toast)
    item(v, "salt").setCheckState(Qt.Checked)
    v.clear_checks_button.click()
    assert item(v, "salt").checkState() == Qt.Unchecked
    v.remove_button(toast).click()
    assert len(texts(v)) == 6 and v.add_button(toast).text() == "Add" and v.add_button(toast).isEnabled()
    v.clear_selection_button.click()
    assert v.selected_ids() == [] and v.list_widget.count() == 0 and v.empty_label.isVisible()

def test_filter_hides_library_rows(qtbot):
    _, v, *_ = seeded(qtbot)
    v.filter_edit.setText("TOA")
    visible = [v.library_list.item(i).text() for i in range(v.library_list.count())
               if not v.library_list.item(i).isHidden()]
    assert visible == ["Toast — serves 2"]

def test_refresh_library_drops_deleted_recipe(qtbot):
    repo, v, pancakes, toast = seeded(qtbot)
    v.add_recipe(pancakes); v.add_recipe(toast)
    with repo.transaction():
        repo.delete(toast)
    v.refresh_library()
    assert v.selected_ids() == [pancakes] and len(texts(v)) == 6 and v.library_list.count() == 1

def test_duplicate_named_recipes_selectable_separately(qtbot):
    repo, v, _, toast = seeded(qtbot)
    with repo.transaction():
        toast2 = repo.add(Recipe("Toast", 2, [I("jam", F(1), "tbsp")]))
    v.refresh_library(); v.add_recipe(toast2)
    assert v.add_button(toast).isEnabled() and not v.add_button(toast2).isEnabled()
    assert texts(v) == ["jam — 1 tbsp"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/ui/test_shopping_view.py -v`
Expected: FAIL with `ModuleNotFoundError: shopping_list.ui.shopping_view`

- [ ] **Step 3: Implement `ShoppingView`** to match the Interfaces block. Keep the selection as `list[Recipe]` with ids from `repo.get`. Build per-row widgets with `QListWidget.setItemWidget`, keep `dict[int, QPushButton]` maps for `add_button`/`remove_button`, and give the library item `Qt.UserRole` = id and `NAME_ROLE` (imported from `ui/library_view.py`) = name for filtering. Layout: the library list on the left; on the right, the selected list on top and below it a button row, the empty label and `list_widget`.

- [ ] **Step 4: Run tests.** `.venv/bin/pytest tests/ui/test_shopping_view.py -v` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add shopping_list/ui/shopping_view.py tests/ui/test_shopping_view.py
git commit -m "feat: shopping view with selection, check-off and copy"
```

---

### Task 5: Shopping tab in the main window

**Files:**
- Modify: `shopping_list/ui/main_window.py`
- Test: `tests/ui/test_main.py`

**Interfaces:**
- Consumes: `ShoppingView` (Task 4); `LibraryView.recipes_changed` (PRD 1).
- Produces: `MainWindow.shopping: ShoppingView` as tab index 1 `"Shopping"`. `library.recipes_changed` is connected to `shopping.refresh_library`, and `shopping.status_message` to `self.statusBar().showMessage(msg, 5000)`. Update the module docstring to say it hosts the Library and Shopping tabs.

- [ ] **Step 1: Write the failing tests.** In `tests/ui/test_main.py`, extend `test_main_window` with `and w.tabs.tabText(1) == "Shopping"`, then add:

```python
from fractions import Fraction as F
from shopping_list.core.models import Ingredient, Recipe

def test_library_change_refreshes_shopping(qtbot):
    repo = RecipeRepository(connect(":memory:"))
    with repo.transaction():
        rid = repo.add(Recipe("Toast", 2, [Ingredient("bread", F(2), None)]))
    w = MainWindow(repo); qtbot.addWidget(w)
    w.shopping.add_recipe(rid)
    with repo.transaction():
        repo.delete(rid)
    w.library.recipes_changed.emit()
    assert w.shopping.selected_ids() == [] and w.shopping.list_widget.count() == 0

def test_shopping_status_shows_in_status_bar(qtbot):
    w = MainWindow(RecipeRepository(connect(":memory:"))); qtbot.addWidget(w)
    w.shopping.copy_list()
    assert w.statusBar().currentMessage() == "Nothing left to copy"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/ui/test_main.py -v`
Expected: FAIL with `AttributeError: 'MainWindow' object has no attribute 'shopping'`, or the tab-text assertion fails.

- [ ] **Step 3: Implement** the tab and the two connections in `MainWindow.__init__`.

- [ ] **Step 4: Run the full suite.** `.venv/bin/pytest -q` → all PASS (185 from PRD 1 plus the new tests).

- [ ] **Step 5: Manual acceptance run.** Run `.venv/bin/python -m shopping_list` and walk through the spec's acceptance criteria. Import the template, add Pancakes alone, and check for 6 lines with `salt` bare. Add Garlic Pasta. Check a line, add another recipe, and confirm it stays checked. Hover a line to see the `From:` tooltip. Check 2 lines, Copy list, and paste into a text editor: one `- ` line per unchecked item. Delete a selected recipe in Library: it disappears from Shopping. Confirm the library detail shows `1½`, not `3/2`.

- [ ] **Step 6: Commit**

```bash
git add shopping_list/ui/main_window.py tests/ui/test_main.py
git commit -m "feat: Shopping tab in the main window"
```
