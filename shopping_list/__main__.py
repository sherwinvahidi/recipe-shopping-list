"""Application entry point."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox

from shopping_list.storage.db import connect
from shopping_list.ui.main_window import MainWindow
from shopping_list.storage.recipes import RecipeRepository

APP_NAME = "Recipe Shopping List"


def default_db_path() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "recipes.db"


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return connect(path)


def main(argv: list[str] | None = None, db_path: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    app.setApplicationName(APP_NAME)
    path = db_path if db_path is not None else default_db_path()
    try:
        conn = open_database(path)
    except (sqlite3.Error, OSError) as err:
        QMessageBox.critical(None, "Can't open recipes",
                             f"Could not open the recipe database at:\n{path}\n\n{err}")
        return 1
    try:
        window = MainWindow(RecipeRepository(conn))
        window.show()
        return app.exec()
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
