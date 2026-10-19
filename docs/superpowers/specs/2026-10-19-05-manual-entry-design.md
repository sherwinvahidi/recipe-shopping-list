# PRD 5 — Manual Recipe Entry & Editing

**Date:** 2026-10-19
**Depends on:** PRD 1 (recipe library, `RecipeTableEditor`)
**See also:** `2026-10-19-00-overview.md`

## Problem

Adding one recipe currently means building a CSV, and fixing a typo in an
imported recipe means re-importing it. Users need to create and edit recipes
directly in the app.

## Goals

- Create a recipe from scratch in the app.
- Edit any existing recipe: name, servings, ingredients.
- Apply exactly the same parsing and validation rules as CSV import.

## Non-goals

- Recipe instructions, photos, tags or notes.
- Undo history beyond cancelling the editor.
- Importing from URLs or free text.

## User stories

1. As a user, I click **New recipe**, enter a name, servings and ingredients, and save it to my library.
2. As a user, I select a recipe and click **Edit** to fix a quantity or add an ingredient.
3. As a user, I see the same inline errors and warnings I'd see on import, and can't save an invalid recipe.

## Functional requirements

### Editor dialog (`ui/recipe_editor_dialog.py`)

- Fields: **Name** (text), **Servings** (spin box, 1–999), and the ingredient
  table — the same `RecipeTableEditor` widget built in PRD 1, with **Add row**
  and **Delete row** buttons. The per-row *skip* checkbox is hidden in this
  mode (`RecipeTableEditor(show_skip=False)`).
- New recipe opens with one empty row; Edit opens with the recipe's rows in order.
- Empty rows (all three cells blank) are ignored on save rather than flagged.
- Validation calls the same `core/validation.py` rules as import (PRD 1):
  blank name or no ingredients is an error; every PRD 1 row rule applies.
- **Save** is disabled while any error exists. **Cancel** discards changes
  (asks to confirm if anything changed).

### Duplicate names

- Saving a **new** recipe whose normalized name matches an existing one asks:
  **Replace existing**, **Keep both**, or **Go back**.
- Editing a recipe and renaming it to match another recipe asks the same,
  where Replace deletes the *other* recipe.

### Persistence

- `RecipeRepository` gains `update(recipe_id: int, recipe: Recipe) -> None`:
  in one transaction, update name/servings and replace all ingredient rows.
- Library view gains **New recipe** and **Edit** (also on double-click) buttons.
- If the edited recipe is currently selected on the Shopping tab, the list
  recomputes with the new data; its target servings is kept if still valid.

## Acceptance criteria

- New recipe "Toast", 1 serving, `bread, 2,` and `butter, 1, tbsp` saves and appears in the library and Shopping tab.
- Entering quantity `1-2` shows the same error message as import and disables Save.
- Unknown unit `pinch` shows the same warning as import and still allows Save.
- Editing Pancakes' egg from `1` to `2` and saving updates the library view and any open shopping list.
- Renaming a recipe to an existing name triggers the duplicate prompt; Go back returns to the editor with changes intact.
- Cancel after edits prompts; confirming leaves the recipe unchanged.

## Testing

- `tests/core/test_validation.py` (extended) — empty-row skipping, no-ingredients error.
- `tests/storage/test_recipes.py` (extended) — `update` replaces ingredients atomically; rollback on failure.
- `tests/ui/test_recipe_editor.py` — smoke: create, edit, cancel-with-changes.
