"""Main window: hosts the Library and Shopping tabs."""
from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget

from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui.library_view import LibraryView
from shopping_list.ui.shopping_view import ShoppingView


class MainWindow(QMainWindow):
    def __init__(self, repo: RecipeRepository):
        super().__init__()
        self.setWindowTitle("Recipe Shopping List")
        self.library = LibraryView(repo)
        self.shopping = ShoppingView(repo)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.library, "Library")
        self.tabs.addTab(self.shopping, "Shopping")
        self.library.recipes_replaced.connect(self.shopping.follow_replacements)
        self.library.recipes_changed.connect(self.shopping.refresh_library)
        self.shopping.status_message.connect(
            lambda msg: self.statusBar().showMessage(msg, 5000))
        self.setCentralWidget(self.tabs)
        self.resize(900, 600)
