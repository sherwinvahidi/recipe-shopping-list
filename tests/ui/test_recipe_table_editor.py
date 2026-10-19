from PySide6.QtCore import Qt

from shopping_list.core.importer import parse_csv_text, revalidate
from shopping_list.ui.recipe_table_editor import (
    RecipeTableEditor, COL_QUANTITY, COL_UNIT, COL_SKIP, ERROR_COLOR, WARNING_COLOR)

H = "recipe,servings,ingredient,quantity,unit\n"


def make(qtbot, text, **kw):
    p = parse_csv_text(text)
    w = RecipeTableEditor(**kw)
    qtbot.addWidget(w)
    w.set_rows(p.recipes[0].rows)
    return p, w


def test_error_and_warning_styling(qtbot):
    p, w = make(qtbot, H + "A,1,milk,1-2,cup\nA,1,garlic,4,clove\n")
    t = w.table
    assert t.item(0, COL_QUANTITY).background().color() == ERROR_COLOR
    assert "single positive number" in t.item(0, COL_QUANTITY).toolTip()
    assert t.item(1, COL_UNIT).background().color() == WARNING_COLOR


def test_edit_writes_back_and_signals(qtbot):
    p, w = make(qtbot, H + "A,1,milk,1-2,cup\n")
    with qtbot.waitSignal(w.rows_edited):
        w.table.item(0, COL_QUANTITY).setText("2")
    assert p.recipes[0].rows[0].quantity == "2"
    revalidate(p)
    w.refresh_issues()
    assert w.table.item(0, COL_QUANTITY).background().color() != ERROR_COLOR


def test_skip_toggle(qtbot):
    p, w = make(qtbot, H + "A,1,milk,1,cup\n")
    with qtbot.waitSignal(w.rows_edited):
        w.table.item(0, COL_SKIP).setCheckState(Qt.Checked)
    assert p.recipes[0].rows[0].skipped


def test_skip_column_hidden(qtbot):
    _, w = make(qtbot, H + "A,1,milk,1,cup\n", show_skip=False)
    assert w.table.isColumnHidden(COL_SKIP)


def test_set_rows_replaces_and_clean_cells_unstyled(qtbot):
    p, w = make(qtbot, H + "A,1,milk,1,cup\nA,1,egg,2,\n")
    assert w.table.rowCount() == 2
    w.set_rows(p.recipes[0].rows[:1])
    assert w.table.rowCount() == 1
    assert w.table.item(0, COL_QUANTITY).toolTip() == ""
    assert w.table.item(0, COL_QUANTITY).background().style() == Qt.NoBrush
