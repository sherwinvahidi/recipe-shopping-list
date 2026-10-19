import sqlite3

import pytest
from shopping_list.core.template import TEMPLATE_CSV
from shopping_list.import_commit import DuplicateChoice, ImportResult
from shopping_list.storage.db import connect
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui.import_dialog import ImportDialog
from shopping_list.ui.recipe_table_editor import COL_QUANTITY

H = "recipe,servings,ingredient,quantity,unit\n"


def dialog(qtbot, resolve=None):
    repo = RecipeRepository(connect(":memory:"))
    d = ImportDialog(repo, resolve=resolve)
    qtbot.addWidget(d)
    return repo, d


def test_template_import(qtbot):
    repo, d = dialog(qtbot)
    d.load_text(TEMPLATE_CSV)
    assert d.import_button.isEnabled() and d.import_button.text() == "Import 2 recipes"
    d.import_button.click()
    assert d.result == ImportResult(2, 0, 0) and len(repo.list_summaries()) == 2


def test_file_error_shown(qtbot):
    _, d = dialog(qtbot)
    d.load_text("recipe,ingredient\nA,b\n")
    assert "Missing required column(s): servings, quantity, unit" in d.file_issue_label.text()
    assert not d.import_button.isEnabled()


def test_fix_cell_enables_import(qtbot):
    _, d = dialog(qtbot)
    d.load_text(H + "A,1,milk,1-2,cup\n")
    assert not d.import_button.isEnabled()
    d.recipe_editors[0].table.item(0, COL_QUANTITY).setText("2")
    assert d.import_button.isEnabled() and d.import_button.text() == "Import 1 recipe"


def test_fix_servings_and_skip_recipe(qtbot):
    _, d = dialog(qtbot)
    d.load_text(H + "A,x,egg,1,\nB,1,egg,1,\n")
    assert not d.import_button.isEnabled()
    d.recipe_servings_edits[0].setText("2")
    assert d.import_button.text() == "Import 2 recipes" and d.import_button.isEnabled()
    d.recipe_skip_boxes[0].setChecked(True)
    assert d.import_button.text() == "Import 1 recipe"


def test_duplicates_routed_to_resolver(qtbot):
    seen = []
    repo, d = dialog(qtbot, resolve=lambda r, e: seen.append(r.name) or DuplicateChoice("replace", True))
    d.load_text(TEMPLATE_CSV)
    d.import_button.click()
    d2 = ImportDialog(repo, resolve=d._resolve)
    qtbot.addWidget(d2)
    d2.load_text(TEMPLATE_CSV)
    d2.import_button.click()
    assert seen == ["Pancakes"] and d2.result == ImportResult(0, 2, 0)


def test_cancel_keeps_dialog_open(qtbot):
    repo, d = dialog(qtbot, resolve=lambda r, e: None)
    d.load_text(TEMPLATE_CSV)
    d.import_button.click()
    d2 = ImportDialog(repo, resolve=lambda r, e: None)
    qtbot.addWidget(d2)
    d2.load_text(TEMPLATE_CSV)
    d2.import_button.click()
    assert d2.result is None and len(repo.list_summaries()) == 2


def test_load_file_from_drop(qtbot, tmp_path):
    path = tmp_path / "recipes.csv"
    path.write_text(TEMPLATE_CSV, encoding="utf-8")
    _, d = dialog(qtbot)
    d.load_file(path)
    assert d.import_button.text() == "Import 2 recipes"


def test_reload_rebuilds_preview(qtbot):
    _, d = dialog(qtbot)
    d.load_text(TEMPLATE_CSV)
    d.load_text(H + "A,1,egg,1,\n")
    assert len(d.recipe_editors) == 1 and len(d.recipe_name_edits) == 1
    assert d.import_button.text() == "Import 1 recipe"


def test_duplicate_box_default_is_keep_both(qtbot):
    from shopping_list.core.models import Recipe, RecipeSummary
    from shopping_list.ui.import_dialog import _build_duplicate_box
    box, buttons = _build_duplicate_box(None, Recipe("Soup", 2, []), [RecipeSummary(1, "Soup", 2, 1)])
    qtbot.addWidget(box)
    assert box.defaultButton() is buttons["keep_both"]
    assert box.defaultButton() is not buttons["replace"]
    assert box.text() == "A recipe named 'Soup' already exists."


def test_duplicate_box_multiple_matches_text(qtbot):
    from shopping_list.core.models import Recipe, RecipeSummary
    from shopping_list.ui.import_dialog import _build_duplicate_box
    existing = [RecipeSummary(1, "Soup", 2, 1), RecipeSummary(2, "Soup", 2, 1)]
    box, _ = _build_duplicate_box(None, Recipe("Soup", 2, []), existing)
    qtbot.addWidget(box)
    assert box.text() == "2 recipes named 'Soup' already exist. Replace removes all of them."


@pytest.mark.parametrize("exc", [sqlite3.OperationalError("disk full"), RuntimeError("weird")])
def test_import_failure_shows_critical_and_stays_open(qtbot, monkeypatch, exc):
    from shopping_list.ui import import_dialog
    _, d = dialog(qtbot)
    d.load_text(TEMPLATE_CSV)
    shown = []
    monkeypatch.setattr(import_dialog.QMessageBox, "critical",
                        lambda parent, title, text: shown.append((title, text)))

    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(import_dialog, "commit_import", boom)
    d.import_button.click()
    assert shown == [("Import failed", f"Nothing was imported.\n\n{exc}")]
    assert d.result is None


def test_renaming_to_same_name_blocks_import_until_resolved(qtbot):
    from shopping_list.core.importer import DUPLICATE_IN_IMPORT
    _, d = dialog(qtbot)
    d.load_text(TEMPLATE_CSV)
    d.recipe_name_edits[1].setText("pancakes")
    assert not d.import_button.isEnabled()
    labels = [label for _, label in d._group_labels]
    assert all(label.text() == DUPLICATE_IN_IMPORT and not label.isHidden() for label in labels)
    d.recipe_name_edits[1].setText("Pancakes 2")
    assert d.import_button.isEnabled()
    assert all(label.isHidden() for label in labels)


def test_import_failure_message_is_readable_for_key_error(qtbot, monkeypatch):
    from shopping_list.ui import import_dialog
    _, d = dialog(qtbot)
    d.load_text(TEMPLATE_CSV)
    shown = []
    monkeypatch.setattr(import_dialog.QMessageBox, "critical",
                        lambda parent, title, text: shown.append(text))

    def boom(*a, **k):
        raise KeyError(1)
    monkeypatch.setattr(import_dialog, "commit_import", boom)
    d.import_button.click()
    assert shown == ["Nothing was imported.\n\nUnexpected error (KeyError)."]
