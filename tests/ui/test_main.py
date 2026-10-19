from fractions import Fraction as F

from shopping_list.core.models import Ingredient, Recipe
from shopping_list.storage.db import connect
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui.main_window import MainWindow
from shopping_list import __main__ as entry


def test_main_window(qtbot):
    w = MainWindow(RecipeRepository(connect(":memory:"))); qtbot.addWidget(w)
    assert w.windowTitle() == "Recipe Shopping List" and w.tabs.tabText(0) == "Library" \
        and w.tabs.tabText(1) == "Shopping"


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


def test_open_database_creates_dirs(tmp_path):
    conn = entry.open_database(tmp_path / "a" / "b" / "recipes.db")
    assert (tmp_path / "a" / "b" / "recipes.db").exists(); conn.close()


def test_db_open_failure_shows_dialog_and_exits_1(qtbot, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(entry.QMessageBox, "critical", lambda *a: shown.append(a[2]))
    bad = tmp_path / "dir_not_file"; bad.mkdir()
    assert entry.main([], db_path=bad) == 1
    assert str(bad) in shown[0]


def test_library_replacements_reach_shopping(qtbot):
    repo = RecipeRepository(connect(":memory:"))
    with repo.transaction():
        rid = repo.add(Recipe("Toast", 2, [Ingredient("bread", F(2), None)]))
    w = MainWindow(repo); qtbot.addWidget(w)
    w.shopping.add_recipe(rid)
    with repo.transaction():
        new_id = repo.replace(rid, Recipe("Toast", 2, [Ingredient("bread", F(3), None)]))
    w.library.recipes_replaced.emit({rid: new_id})
    w.library.recipes_changed.emit()
    assert w.shopping.selected_ids() == [new_id]
