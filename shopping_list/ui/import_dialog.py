"""Import dialog: load a CSV (file or paste), fix issues in a preview, commit."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea,
                               QTabWidget, QVBoxLayout, QWidget)

from shopping_list.core.importer import (ImportPreview, PreviewRecipe,
                                         parse_csv_file, parse_csv_text,
                                         revalidate)
from shopping_list.core.models import Recipe, RecipeSummary
from shopping_list.import_commit import (DuplicateChoice, ImportResult,
                                         Resolver, commit_import)
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui.recipe_table_editor import RecipeTableEditor

ERROR_STYLE = "color: #b02a37;"
WARNING_STYLE = "color: #8a6d3b;"
NOTICE_STYLE = "color: grey;"
UNITS_HINT = "Tip: use fl oz for liquids — oz always means weight."


def ask_duplicate(parent: QWidget, recipe: Recipe,
                  existing: list[RecipeSummary]) -> DuplicateChoice | None:
    """Ask what to do with a recipe whose name already exists. None = cancel import."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle("Duplicate recipe")
    if len(existing) > 1:
        box.setText(f"{len(existing)} recipes named '{recipe.name}' already exist.")
    else:
        box.setText(f"A recipe named '{recipe.name}' already exists.")
    replace = box.addButton("Replace", QMessageBox.AcceptRole)
    skip = box.addButton("Skip", QMessageBox.AcceptRole)
    keep = box.addButton("Keep both", QMessageBox.AcceptRole)
    cancel = box.addButton("Cancel import", QMessageBox.RejectRole)
    box.setEscapeButton(cancel)
    apply_all = QCheckBox("Apply to all remaining")
    box.setCheckBox(apply_all)
    box.exec()
    clicked = box.clickedButton()
    action = {replace: "replace", skip: "skip", keep: "keep_both"}.get(clicked)
    if action is None:
        return None
    return DuplicateChoice(action, apply_all.isChecked())


class ImportDialog(QDialog):
    def __init__(self, repo: RecipeRepository, resolve: Resolver | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Import recipes")
        self.setAcceptDrops(True)
        self.resize(720, 640)
        self._repo = repo
        self._resolve: Resolver = resolve or (
            lambda recipe, existing: ask_duplicate(self, recipe, existing))
        self._preview: ImportPreview | None = None
        self._group_labels: list[tuple[PreviewRecipe, QLabel]] = []
        self.result: ImportResult | None = None
        self.recipe_editors: list[RecipeTableEditor] = []
        self.recipe_name_edits: list[QLineEdit] = []
        self.recipe_servings_edits: list[QLineEdit] = []
        self.recipe_skip_boxes: list[QCheckBox] = []

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        file_tab = QWidget()
        file_layout = QVBoxLayout(file_tab)
        self.drop_label = QLabel("Drop a .csv file here")
        self.drop_label.setStyleSheet("border: 2px dashed grey; padding: 16px;")
        self.drop_label.setAlignment(self.drop_label.alignment().AlignCenter)
        file_layout.addWidget(self.drop_label)
        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self._browse)
        file_layout.addWidget(self.browse_button)
        tabs.addTab(file_tab, "File")

        paste_tab = QWidget()
        paste_layout = QVBoxLayout(paste_tab)
        self.paste_edit = QPlainTextEdit()
        self.paste_edit.setPlaceholderText("Paste CSV or spreadsheet rows here")
        paste_layout.addWidget(self.paste_edit)
        self.preview_button = QPushButton("Preview")
        self.preview_button.clicked.connect(lambda: self.load_text(self.paste_edit.toPlainText()))
        paste_layout.addWidget(self.preview_button)
        tabs.addTab(paste_tab, "Paste")

        self.file_issue_label = QLabel()
        self.file_issue_label.setStyleSheet(ERROR_STYLE)
        self.file_issue_label.setWordWrap(True)
        self.file_issue_label.hide()
        layout.addWidget(self.file_issue_label)
        self.notice_label = QLabel()
        self.notice_label.setStyleSheet(NOTICE_STYLE)
        self.notice_label.setWordWrap(True)
        self.notice_label.hide()
        layout.addWidget(self.notice_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        layout.addWidget(self._scroll, 1)
        self._new_container()

        self.hint_label = QLabel(UNITS_HINT)
        self.hint_label.setStyleSheet(NOTICE_STYLE)
        layout.addWidget(self.hint_label)

        self.import_button = QPushButton("Import 0 recipes")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._on_import)
        layout.addWidget(self.import_button)

    # --- loading -----------------------------------------------------------
    def load_text(self, text: str) -> None:
        self._show(parse_csv_text(text))

    def load_file(self, path: Path) -> None:
        self._show(parse_csv_file(Path(path)))

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a CSV file", "",
                                              filter="CSV files (*.csv)")
        if path:
            self.load_file(Path(path))

    @staticmethod
    def _csv_drop_path(event) -> Path | None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            if path.suffix.lower() == ".csv":
                return path
        return None

    def dragEnterEvent(self, event) -> None:
        if self._csv_drop_path(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        path = self._csv_drop_path(event)
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self.load_file(path)

    # --- preview building --------------------------------------------------
    def _new_container(self) -> QVBoxLayout:
        container = QWidget()
        box = QVBoxLayout(container)
        self._scroll.setWidget(container)  # deletes the previous container
        return box

    def _show(self, preview: ImportPreview) -> None:
        self._preview = preview
        self.recipe_editors, self.recipe_name_edits = [], []
        self.recipe_servings_edits, self.recipe_skip_boxes = [], []
        self._group_labels = []
        box = self._new_container()
        for recipe in preview.recipes:
            box.addWidget(self._build_group(recipe))
        box.addStretch(1)
        self._refresh()

    def _build_group(self, recipe: PreviewRecipe) -> QGroupBox:
        group = QGroupBox()
        v = QVBoxLayout(group)
        header = QHBoxLayout()
        name = QLineEdit(recipe.name)
        name.setPlaceholderText("Recipe name")
        servings = QLineEdit(recipe.servings)
        servings.setPlaceholderText("Servings")
        servings.setMaximumWidth(90)
        skip = QCheckBox("Skip recipe")
        skip.setChecked(recipe.skipped)
        header.addWidget(name, 1)
        header.addWidget(servings)
        header.addWidget(skip)
        v.addLayout(header)
        issue_label = QLabel()
        issue_label.setWordWrap(True)
        issue_label.hide()
        v.addWidget(issue_label)
        editor = RecipeTableEditor(show_skip=True)
        editor.set_rows(recipe.rows)
        v.addWidget(editor)

        name.textChanged.connect(lambda text, r=recipe: self._set_field(r, "name", text))
        servings.textChanged.connect(lambda text, r=recipe: self._set_field(r, "servings", text))
        skip.toggled.connect(lambda on, r=recipe: self._set_field(r, "skipped", on))
        editor.rows_edited.connect(self._refresh)

        self.recipe_name_edits.append(name)
        self.recipe_servings_edits.append(servings)
        self.recipe_skip_boxes.append(skip)
        self.recipe_editors.append(editor)
        self._group_labels.append((recipe, issue_label))
        return group

    def _set_field(self, recipe: PreviewRecipe, attr: str, value) -> None:
        setattr(recipe, attr, value)
        self._refresh()

    # --- refresh -----------------------------------------------------------
    def _refresh(self) -> None:
        preview = self._preview
        if preview is None:
            return
        revalidate(preview)
        for editor in self.recipe_editors:
            editor.refresh_issues()

        errors = [i.message for i in preview.file_issues if i.level == "error"]
        self.file_issue_label.setText("\n".join(errors))
        self.file_issue_label.setVisible(bool(errors))
        self.notice_label.setText("\n".join(preview.notices))
        self.notice_label.setVisible(bool(preview.notices))

        for recipe, label in self._group_labels:
            label.setText("\n".join(i.message for i in recipe.issues))
            has_error = any(i.level == "error" for i in recipe.issues)
            label.setStyleSheet(ERROR_STYLE if has_error else WARNING_STYLE)
            label.setVisible(bool(recipe.issues))

        n = len(preview.active_recipes)
        self.import_button.setText("Import 1 recipe" if n == 1 else f"Import {n} recipes")
        self.import_button.setEnabled(preview.is_importable)

    # --- commit ------------------------------------------------------------
    def _on_import(self) -> None:
        if self._preview is None or not self._preview.is_importable:
            return
        try:
            result = commit_import(self._preview, self._repo, self._resolve)
        except sqlite3.Error as err:
            QMessageBox.critical(self, "Import failed", f"Nothing was imported.\n\n{err}")
            return
        if result is None:
            return
        self.result = result
        self.accept()
