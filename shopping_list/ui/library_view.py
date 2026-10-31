"""Library view: browse, filter, import and delete recipes."""
from __future__ import annotations

import sqlite3
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from shopping_list.core.quantity import format_quantity
from shopping_list.core.template import TEMPLATE_CSV
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui.import_dialog import ImportDialog

EMPTY_HINT = "No recipes yet — Import a CSV or save the template to get started."
NAME_ROLE = Qt.UserRole + 1


def _default_confirm(message: str) -> bool:
    return QMessageBox.question(None, "Delete recipe", message) == QMessageBox.Yes


class LibraryView(QWidget):
    recipes_changed = Signal()
    # Emitted before recipes_changed with {old id: new id} for replaced recipes.
    recipes_replaced = Signal(object)

    def __init__(self, repo: RecipeRepository,
                 confirm: Callable[[str], bool] | None = None, parent=None):
        super().__init__(parent)
        self._repo = repo
        self._confirm = confirm or _default_confirm

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter recipes")
        self.filter_edit.setClearButtonEnabled(True)
        self.import_button = QPushButton("Import…")
        self.template_button = QPushButton("Save template…")
        self.delete_button = QPushButton("Delete")
        self.delete_button.setEnabled(False)
        self.empty_label = QLabel(EMPTY_HINT)
        self.empty_label.setWordWrap(True)
        self.recipe_list = QListWidget()
        self.detail_table = QTableWidget(0, 3)
        self.detail_table.setHorizontalHeaderLabels(["Quantity", "Unit", "Ingredient"])
        self.detail_table.horizontalHeader().setStretchLastSection(True)
        self.detail_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        buttons = QHBoxLayout()
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.template_button)
        buttons.addStretch(1)
        buttons.addWidget(self.delete_button)
        body = QHBoxLayout()
        body.addWidget(self.recipe_list, 1)
        body.addWidget(self.detail_table, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.filter_edit)
        layout.addLayout(buttons)
        layout.addWidget(self.empty_label)
        layout.addLayout(body, 1)

        self.filter_edit.textChanged.connect(self._apply_filter)
        self.recipe_list.currentItemChanged.connect(self._sync_detail)
        self.import_button.clicked.connect(self._import)
        self.template_button.clicked.connect(self._save_template)
        self.delete_button.clicked.connect(self._delete)
        self.refresh()

    def refresh(self) -> None:
        self.recipe_list.blockSignals(True)
        self.recipe_list.clear()
        for s in self._repo.list_summaries():
            n = s.ingredient_count
            item = QListWidgetItem(
                f"{s.name} — serves {s.servings} · {n} ingredient{'' if n == 1 else 's'}")
            item.setData(Qt.UserRole, s.id)
            item.setData(NAME_ROLE, s.name)
            self.recipe_list.addItem(item)
        self.recipe_list.setCurrentItem(None)
        self.recipe_list.blockSignals(False)
        self.empty_label.setVisible(self.recipe_list.count() == 0)
        self._apply_filter()
        self._sync_detail()

    def _apply_filter(self) -> None:
        needle = self.filter_edit.text().strip().casefold()
        for i in range(self.recipe_list.count()):
            item = self.recipe_list.item(i)
            item.setHidden(needle not in item.data(NAME_ROLE).casefold())
        self._sync_detail()

    def _selected(self) -> QListWidgetItem | None:
        item = self.recipe_list.currentItem()
        return None if item is None or item.isHidden() else item

    def _sync_detail(self, *_) -> None:
        item = self._selected()
        self.delete_button.setEnabled(item is not None)
        self.detail_table.setRowCount(0)
        if item is None:
            return
        recipe = self._repo.get(item.data(Qt.UserRole))
        self.detail_table.setRowCount(len(recipe.ingredients))
        for row, ing in enumerate(recipe.ingredients):
            qty = "" if ing.quantity is None else format_quantity(ing.quantity, exact=True)
            for col, text in enumerate((qty, ing.unit or "", ing.name)):
                self.detail_table.setItem(row, col, QTableWidgetItem(text))

    def _import(self) -> None:
        dialog = ImportDialog(self._repo, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            if dialog.result is not None and dialog.result.replaced_ids:
                self.recipes_replaced.emit(dialog.result.replaced_ids)
            self.recipes_changed.emit()

    def _save_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save template", "recipe-template.csv", "CSV files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(TEMPLATE_CSV)
        except OSError as err:
            QMessageBox.critical(self, "Save failed", str(err))

    def _delete(self) -> None:
        item = self._selected()
        if item is None:
            return
        name = item.data(NAME_ROLE)
        if not self._confirm(f"Delete '{name}'? This can't be undone."):
            return
        try:
            with self._repo.transaction():
                self._repo.delete(item.data(Qt.UserRole))
        except sqlite3.Error as err:
            QMessageBox.critical(self, "Delete failed", str(err))
            return
        self.refresh()
        self.recipes_changed.emit()
