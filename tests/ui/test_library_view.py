from fractions import Fraction as F

from PySide6.QtWidgets import QDialog, QMessageBox

from shopping_list.core.models import Recipe, Ingredient
from shopping_list.core.template import TEMPLATE_CSV
from shopping_list.storage.db import connect
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui import library_view
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
    assert v.empty_label.text() == "No recipes yet — Import a CSV or save the template to get started."


def test_empty_hint_hidden_with_recipes(qtbot):
    _, v = seeded(qtbot); v.show()
    assert not v.empty_label.isVisible()


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


def test_filter_hiding_current_clears_detail(qtbot):
    _, v = seeded(qtbot); v.recipe_list.setCurrentRow(1)
    assert v.detail_table.rowCount() == 2
    v.filter_edit.setText("garlic")
    assert v.detail_table.rowCount() == 0
    assert not v.delete_button.isEnabled()


def test_delete_confirmed(qtbot):
    msgs = []
    repo, v = seeded(qtbot, confirm=lambda m: msgs.append(m) or True)
    v.recipe_list.setCurrentRow(1)
    with qtbot.waitSignal(v.recipes_changed):
        v.delete_button.click()
    assert msgs == ["Delete 'Pancakes'? This can't be undone."]
    assert [s.name for s in repo.list_summaries()] == ["Garlic Pasta"]
    assert v.recipe_list.count() == 1 and v.detail_table.rowCount() == 0


def test_delete_declined(qtbot):
    repo, v = seeded(qtbot, confirm=lambda m: False)
    v.recipe_list.setCurrentRow(0); v.delete_button.click()
    assert len(repo.list_summaries()) == 2


def test_delete_disabled_without_selection(qtbot):
    _, v = seeded(qtbot)
    assert not v.delete_button.isEnabled()


def test_refresh_clears_selection_keeps_filter(qtbot):
    repo, v = seeded(qtbot)
    v.filter_edit.setText("pan"); v.recipe_list.setCurrentRow(1)
    with repo.transaction():
        repo.add(Recipe("Panna Cotta", 6, [Ingredient("cream", F(1), "cup")]))
    v.refresh()
    assert v.recipe_list.currentItem() is None and v.detail_table.rowCount() == 0
    visible = [v.recipe_list.item(i).text() for i in range(v.recipe_list.count()) if not v.recipe_list.item(i).isHidden()]
    assert len(visible) == 2 and v.filter_edit.text() == "pan"


def test_import_accepted_refreshes(qtbot, monkeypatch):
    repo, v = seeded(qtbot)

    class FakeDialog:
        def __init__(self, r, parent=None):
            with r.transaction():
                r.add(Recipe("Soup", 2, [Ingredient("water", F(1), "l")]))
        def exec(self):
            return QDialog.Accepted
    monkeypatch.setattr(library_view, "ImportDialog", FakeDialog)
    with qtbot.waitSignal(v.recipes_changed):
        v.import_button.click()
    assert v.recipe_list.count() == 3


def test_import_rejected_no_signal(qtbot, monkeypatch):
    _, v = seeded(qtbot)

    class FakeDialog:
        def __init__(self, r, parent=None): pass
        def exec(self): return QDialog.Rejected
    monkeypatch.setattr(library_view, "ImportDialog", FakeDialog)
    with qtbot.assertNotEmitted(v.recipes_changed):
        v.import_button.click()


def test_save_template(qtbot, monkeypatch, tmp_path):
    _, v = seeded(qtbot)
    target = tmp_path / "t.csv"
    monkeypatch.setattr(library_view.QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(target), "CSV files (*.csv)"))
    v.template_button.click()
    assert target.read_text(encoding="utf-8") == TEMPLATE_CSV


def test_save_template_cancel(qtbot, monkeypatch, tmp_path):
    _, v = seeded(qtbot)
    monkeypatch.setattr(library_view.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    errs = []
    monkeypatch.setattr(library_view.QMessageBox, "critical",
                        lambda *a, **k: errs.append(a))
    v.template_button.click()
    assert list(tmp_path.iterdir()) == []
    assert errs == []


def test_save_template_error(qtbot, monkeypatch, tmp_path):
    _, v = seeded(qtbot)
    errs = []
    monkeypatch.setattr(library_view.QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(tmp_path / "missing" / "t.csv"), ""))
    monkeypatch.setattr(library_view.QMessageBox, "critical",
                        lambda parent, title, text: errs.append((title, text)))
    v.template_button.click()
    assert errs and errs[0][0] == "Save failed"
