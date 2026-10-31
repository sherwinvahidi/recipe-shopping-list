"""Shopping view: pick recipes, see the combined list, check off and copy."""
from __future__ import annotations

from fractions import Fraction

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

from shopping_list.core.models import Recipe
from shopping_list.core.shopping import (ShoppingLine, build_shopping_list,
                                         format_line)
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui.library_view import NAME_ROLE

EMPTY_SELECTION = "Add recipes to build your shopping list."


class ShoppingView(QWidget):
    status_message = Signal(str)

    def __init__(self, repo: RecipeRepository, parent=None):
        super().__init__(parent)
        self._repo = repo
        self._selected: list[Recipe] = []
        # Checked line key -> the quantity it had when checked.
        self._checked: dict[tuple, Fraction | None] = {}
        self._add_buttons: dict[int, QPushButton] = {}
        self._remove_buttons: dict[int, QPushButton] = {}

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter recipes")
        self.filter_edit.setClearButtonEnabled(True)
        self.library_list = QListWidget()
        self.selected_list = QListWidget()
        self.empty_label = QLabel(EMPTY_SELECTION)
        self.empty_label.setWordWrap(True)
        self.list_widget = QListWidget()
        self.copy_button = QPushButton("Copy list")
        self.clear_checks_button = QPushButton("Clear checks")
        self.clear_selection_button = QPushButton("Clear selection")

        left = QVBoxLayout()
        left.addWidget(self.filter_edit)
        left.addWidget(self.library_list, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.clear_checks_button)
        buttons.addStretch(1)
        buttons.addWidget(self.clear_selection_button)
        right = QVBoxLayout()
        right.addWidget(self.selected_list, 1)
        right.addLayout(buttons)
        right.addWidget(self.empty_label)
        right.addWidget(self.list_widget, 2)
        layout = QHBoxLayout(self)
        layout.addLayout(left, 1)
        layout.addLayout(right, 1)

        self.filter_edit.textChanged.connect(self._apply_filter)
        self.list_widget.itemChanged.connect(self._on_item_changed)
        self.copy_button.clicked.connect(self.copy_list)
        self.clear_checks_button.clicked.connect(self.clear_checks)
        self.clear_selection_button.clicked.connect(self.clear_selection)
        self.refresh_library()

    # --- public API ---
    def selected_ids(self) -> list[int]:
        return [r.id for r in self._selected]

    def add_button(self, recipe_id: int) -> QPushButton:
        return self._add_buttons[recipe_id]

    def remove_button(self, recipe_id: int) -> QPushButton:
        return self._remove_buttons[recipe_id]

    def follow_replacements(self, replaced_ids: dict[int, int]) -> None:
        """Point selected recipes at the recipes that replaced them."""
        seen: set[int] = set()
        followed: list[Recipe] = []
        for r in self._selected:
            r.id = replaced_ids.get(r.id, r.id)
            if r.id not in seen:
                seen.add(r.id)
                followed.append(r)
        self._selected = followed

    def refresh_library(self) -> None:
        kept: list[Recipe] = []
        removed: list[str] = []
        for r in self._selected:
            try:
                kept.append(self._repo.get(r.id))
            except KeyError:
                removed.append(r.name)
        self._selected = kept
        if len(removed) == 1:
            self.status_message.emit(f"'{removed[0]}' was removed from the shopping list")
        elif removed:
            names = ", ".join(f"'{n}'" for n in removed)
            self.status_message.emit(
                f"{len(removed)} recipes were removed from the shopping list: {names}")
        self._rebuild_library()
        self._rebuild_selected()
        self._recompute()

    def add_recipe(self, recipe_id: int) -> None:
        if recipe_id in self.selected_ids():
            return
        self._selected.append(self._repo.get(recipe_id))
        self._rebuild_selected()
        self._sync_add_buttons()
        self._recompute()

    def remove_recipe(self, recipe_id: int) -> None:
        self._selected = [r for r in self._selected if r.id != recipe_id]
        self._rebuild_selected()
        self._sync_add_buttons()
        self._recompute()

    def clear_selection(self) -> None:
        self._selected = []
        self._rebuild_selected()
        self._sync_add_buttons()
        self._recompute()

    def clear_checks(self) -> None:
        self._checked.clear()
        self._recompute()

    def copy_list(self) -> None:
        lines = [l for l in build_shopping_list(self._selected)
                 if not self._is_checked(l)]
        n = len(lines)
        if n == 0:
            self.status_message.emit("Nothing left to copy")
            return
        QGuiApplication.clipboard().setText(
            "\n".join("- " + format_line(l) for l in lines))
        self.status_message.emit(f"Copied {n} item{'' if n == 1 else 's'}")

    # --- internals ---
    @staticmethod
    def _row_widget(button: QPushButton) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.addStretch(1)
        lay.addWidget(button)
        return w

    def _attach(self, lst: QListWidget, item: QListWidgetItem,
                button: QPushButton) -> None:
        w = self._row_widget(button)
        item.setSizeHint(w.sizeHint())
        lst.setItemWidget(item, w)

    def _rebuild_library(self) -> None:
        self._add_buttons = {}
        self.library_list.clear()
        for s in self._repo.list_summaries():
            item = QListWidgetItem(f"{s.name} — serves {s.servings}")
            item.setData(Qt.UserRole, s.id)
            item.setData(NAME_ROLE, s.name)
            self.library_list.addItem(item)
            button = QPushButton("Add")
            button.clicked.connect(lambda _=False, rid=s.id: self.add_recipe(rid))
            self._add_buttons[s.id] = button
            self._attach(self.library_list, item, button)
        self._sync_add_buttons()
        self._apply_filter()

    def _sync_add_buttons(self) -> None:
        chosen = set(self.selected_ids())
        for rid, button in self._add_buttons.items():
            added = rid in chosen
            button.setText("Added" if added else "Add")
            button.setEnabled(not added)

    def _apply_filter(self) -> None:
        needle = self.filter_edit.text().strip().casefold()
        for i in range(self.library_list.count()):
            item = self.library_list.item(i)
            item.setHidden(needle not in item.data(NAME_ROLE).casefold())

    def _rebuild_selected(self) -> None:
        self._remove_buttons = {}
        self.selected_list.clear()
        for r in self._selected:
            item = QListWidgetItem(f"{r.name} — serves {r.servings}")
            item.setData(Qt.UserRole, r.id)
            self.selected_list.addItem(item)
            button = QPushButton("Remove")
            button.clicked.connect(lambda _=False, rid=r.id: self.remove_recipe(rid))
            self._remove_buttons[r.id] = button
            self._attach(self.selected_list, item, button)

    def _recompute(self) -> None:
        lines = build_shopping_list(self._selected)
        # A check survives only while its line still asks for the same amount.
        self._checked = {l.key: l.quantity for l in lines if self._is_checked(l)}
        disabled = self.palette().color(QPalette.Disabled, QPalette.Text)
        self.list_widget.blockSignals(True)
        try:
            self.list_widget.clear()
            for line in lines:
                item = QListWidgetItem(format_line(line))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setData(Qt.UserRole, (line.key, line.quantity))
                item.setToolTip("From: " + ", ".join(line.sources))
                checked = self._is_checked(line)
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                self._style(item, checked, disabled)
                self.list_widget.addItem(item)
        finally:
            self.list_widget.blockSignals(False)
        self.empty_label.setVisible(not self._selected)

    def _is_checked(self, line: ShoppingLine) -> bool:
        return line.key in self._checked and self._checked[line.key] == line.quantity

    @staticmethod
    def _style(item: QListWidgetItem, checked: bool, disabled) -> None:
        font = item.font()
        font.setStrikeOut(checked)
        item.setFont(font)
        if checked:
            item.setForeground(disabled)
        else:
            item.setData(Qt.ForegroundRole, None)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        key, quantity = item.data(Qt.UserRole)
        checked = item.checkState() == Qt.Checked
        if checked:
            self._checked[key] = quantity
        else:
            self._checked.pop(key, None)
        disabled = self.palette().color(QPalette.Disabled, QPalette.Text)
        self.list_widget.blockSignals(True)
        try:
            self._style(item, checked, disabled)
        finally:
            self.list_widget.blockSignals(False)
