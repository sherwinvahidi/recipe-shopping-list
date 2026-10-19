"""Main window: hosts the Library tab (PRD 2 adds a Shopping tab)."""
from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget

from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui.library_view import LibraryView


class MainWindow(QMainWindow):
    def __init__(self, repo: RecipeRepository):
        super().__init__()
        self.setWindowTitle("Recipe Shopping List")
        self.library = LibraryView(repo)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.library, "Library")
        self.setCentralWidget(self.tabs)
        self.resize(900, 600)
