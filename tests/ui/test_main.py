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
