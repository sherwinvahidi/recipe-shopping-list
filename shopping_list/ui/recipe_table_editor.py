"""Reusable editable table of recipe ingredient rows with issue styling."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from shopping_list.core.importer import PreviewRow

COL_INGREDIENT = 0
COL_QUANTITY = 1
COL_UNIT = 2
COL_SKIP = 3

ERROR_COLOR = QColor("#f8d7da")
WARNING_COLOR = QColor("#fff3cd")
SKIPPED_TEXT_COLOR = QColor("grey")

_TEXT_ATTRS = {COL_INGREDIENT: "ingredient", COL_QUANTITY: "quantity", COL_UNIT: "unit"}
_COL_FIELDS = {COL_INGREDIENT: "ingredient", COL_QUANTITY: "quantity", COL_UNIT: "unit"}


class RecipeTableEditor(QWidget):
    rows_edited = Signal()

    def __init__(self, show_skip: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self._rows: list[PreviewRow] = []
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["Ingredient", "Quantity", "Unit", "Skip"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            COL_INGREDIENT, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.setColumnHidden(COL_SKIP, not show_skip)
        self.table.itemChanged.connect(self._on_item_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)

    def set_rows(self, rows: list[PreviewRow]) -> None:
        self._rows = rows
        blocked = self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            self.table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for col, attr in _TEXT_ATTRS.items():
                    self.table.setItem(r, col, QTableWidgetItem(getattr(row, attr)))
                skip = QTableWidgetItem()
                skip.setFlags((skip.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
                skip.setCheckState(Qt.Checked if row.skipped else Qt.Unchecked)
                self.table.setItem(r, COL_SKIP, skip)
            self._restyle()
        finally:
            self.table.blockSignals(blocked)

    def refresh_issues(self) -> None:
        blocked = self.table.blockSignals(True)
        try:
            self._restyle()
        finally:
            self.table.blockSignals(blocked)

    def _restyle(self) -> None:
        for r, row in enumerate(self._rows):
            for col in (COL_INGREDIENT, COL_QUANTITY, COL_UNIT):
                item = self.table.item(r, col)
                if item is None:
                    continue
                field = _COL_FIELDS[col]
                issues = [i for i in row.issues
                          if i.field == field or (i.field is None and col == COL_INGREDIENT)]
                issues.sort(key=lambda i: i.level != "error")
                if any(i.level == "error" for i in issues):
                    item.setBackground(QBrush(ERROR_COLOR))
                elif issues:
                    item.setBackground(QBrush(WARNING_COLOR))
                else:
                    item.setBackground(QBrush())
                item.setToolTip("\n".join(i.message for i in issues))
                item.setForeground(QBrush(SKIPPED_TEXT_COLOR) if row.skipped else QBrush())

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        r, col = item.row(), item.column()
        if not 0 <= r < len(self._rows):
            return
        row = self._rows[r]
        if col == COL_SKIP:
            row.skipped = item.checkState() == Qt.Checked
            self.refresh_issues()
        elif col in _TEXT_ATTRS:
            setattr(row, _TEXT_ATTRS[col], item.text())
        else:
            return
        self.rows_edited.emit()
