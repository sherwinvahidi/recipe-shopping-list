from fractions import Fraction as F
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from shopping_list.core.models import Ingredient as I, Recipe
from shopping_list.storage.db import connect
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.ui.shopping_view import EMPTY_SELECTION, ShoppingView

ALL = ["baking powder — 3½ tsp", "bread — 2", "butter — 1 tbsp", "egg — 3", "flour — 1½ cups",
       "milk — 1¼ cups", "salt", "sugar — 1 tbsp"]

def seeded(qtbot):
    repo = RecipeRepository(connect(":memory:"))
    with repo.transaction():
        pancakes = repo.add(Recipe("Pancakes", 4, [
            I("flour", F(3, 2), "cup"), I("milk", F(5, 4), "cup"), I("egg", F(1), None),
            I("sugar", F(1), "tbsp"), I("baking powder", F(7, 2), "tsp"), I("salt", None, None)]))
        toast = repo.add(Recipe("Toast", 2, [I("bread", F(2), None), I("butter", F(1), "tbsp"),
                                             I("eggs", F(2), None)]))
    v = ShoppingView(repo); qtbot.addWidget(v)
    return repo, v, pancakes, toast

def texts(v): return [v.list_widget.item(i).text() for i in range(v.list_widget.count())]
def item(v, text): return v.list_widget.findItems(text, Qt.MatchExactly)[0]

def test_empty_selection_hint(qtbot):
    _, v, *_ = seeded(qtbot); v.show()
    assert v.empty_label.isVisible() and v.empty_label.text() == EMPTY_SELECTION
    assert v.list_widget.count() == 0

def test_add_two_recipes_builds_list(qtbot):
    _, v, pancakes, toast = seeded(qtbot); v.show()
    v.add_button(pancakes).click(); v.add_button(toast).click()
    assert texts(v) == ALL and not v.empty_label.isVisible()
    assert v.add_button(pancakes).text() == "Added" and not v.add_button(pancakes).isEnabled()
    assert item(v, "egg — 3").toolTip() == "From: Pancakes, Toast"
    assert v.selected_ids() == [pancakes, toast]
    assert v.selected_list.item(0).text() == "Pancakes — serves 4"

def test_add_twice_is_noop(qtbot):
    _, v, pancakes, _ = seeded(qtbot)
    v.add_recipe(pancakes); v.add_recipe(pancakes)
    assert v.selected_ids() == [pancakes] and v.selected_list.count() == 1

def test_check_survives_adding_recipe(qtbot):
    _, v, pancakes, toast = seeded(qtbot)
    v.add_recipe(pancakes); item(v, "salt").setCheckState(Qt.Checked)
    v.add_recipe(toast)
    salt = item(v, "salt")
    assert salt.checkState() == Qt.Checked and salt.font().strikeOut()

def test_removed_line_loses_check(qtbot):
    _, v, pancakes, toast = seeded(qtbot)
    v.add_recipe(toast); item(v, "bread — 2").setCheckState(Qt.Checked)
    v.remove_recipe(toast); v.add_recipe(toast)
    assert item(v, "bread — 2").checkState() == Qt.Unchecked

def test_copy_unchecked(qtbot):
    _, v, pancakes, toast = seeded(qtbot)
    v.add_recipe(pancakes); v.add_recipe(toast)
    item(v, "egg — 3").setCheckState(Qt.Checked); item(v, "salt").setCheckState(Qt.Checked)
    with qtbot.waitSignal(v.status_message) as sig:
        v.copy_button.click()
    assert sig.args == ["Copied 6 items"]
    expected = [t for t in ALL if t not in ("egg — 3", "salt")]
    assert QGuiApplication.clipboard().text() == "\n".join("- " + t for t in expected)

def test_copy_single_item_message(qtbot):
    _, v, _, toast = seeded(qtbot)
    v.add_recipe(toast)
    for t in ("butter — 1 tbsp", "eggs — 2"):
        item(v, t).setCheckState(Qt.Checked)
    with qtbot.waitSignal(v.status_message) as sig:
        v.copy_list()
    assert sig.args == ["Copied 1 item"] and QGuiApplication.clipboard().text() == "- bread — 2"

def test_copy_when_all_checked(qtbot):
    _, v, _, toast = seeded(qtbot)
    v.add_recipe(toast)
    for i in range(v.list_widget.count()):
        v.list_widget.item(i).setCheckState(Qt.Checked)
    QGuiApplication.clipboard().setText("sentinel")
    with qtbot.waitSignal(v.status_message) as sig:
        v.copy_list()
    assert sig.args == ["Nothing left to copy"] and QGuiApplication.clipboard().text() == "sentinel"

def test_copy_with_empty_selection(qtbot):
    _, v, *_ = seeded(qtbot)
    QGuiApplication.clipboard().setText("sentinel")
    with qtbot.waitSignal(v.status_message) as sig:
        v.copy_list()
    assert sig.args == ["Nothing left to copy"] and QGuiApplication.clipboard().text() == "sentinel"

def test_clear_checks_and_selection(qtbot):
    _, v, pancakes, toast = seeded(qtbot); v.show()
    v.add_recipe(pancakes); v.add_recipe(toast)
    item(v, "salt").setCheckState(Qt.Checked)
    v.clear_checks_button.click()
    assert item(v, "salt").checkState() == Qt.Unchecked
    v.remove_button(toast).click()
    assert len(texts(v)) == 6 and v.add_button(toast).text() == "Add" and v.add_button(toast).isEnabled()
    v.clear_selection_button.click()
    assert v.selected_ids() == [] and v.list_widget.count() == 0 and v.empty_label.isVisible()

def test_filter_hides_library_rows(qtbot):
    _, v, *_ = seeded(qtbot)
    v.filter_edit.setText("TOA")
    visible = [v.library_list.item(i).text() for i in range(v.library_list.count())
               if not v.library_list.item(i).isHidden()]
    assert visible == ["Toast — serves 2"]

def test_refresh_library_drops_deleted_recipe(qtbot):
    repo, v, pancakes, toast = seeded(qtbot)
    v.add_recipe(pancakes); v.add_recipe(toast)
    with repo.transaction():
        repo.delete(toast)
    with qtbot.waitSignal(v.status_message) as sig:
        v.refresh_library()
    assert sig.args == ["'Toast' was removed from the shopping list"]
    assert v.selected_ids() == [pancakes] and len(texts(v)) == 6 and v.library_list.count() == 1

def test_refresh_library_follows_replaced_recipe(qtbot):
    repo, v, pancakes, toast = seeded(qtbot)
    v.add_recipe(pancakes); v.add_recipe(toast)
    item(v, "bread — 2").setCheckState(Qt.Checked)
    with repo.transaction():
        new_id = repo.replace(toast, Recipe("Toast", 2, [I("bread", F(3), None)]))
    v.refresh_library()
    assert v.selected_ids() == [pancakes, new_id] and toast not in v.selected_ids()
    assert "bread — 3" in texts(v) and "bread — 2" not in texts(v)
    assert not v.add_button(new_id).isEnabled()

def test_duplicate_named_recipes_selectable_separately(qtbot):
    repo, v, _, toast = seeded(qtbot)
    with repo.transaction():
        toast2 = repo.add(Recipe("Toast", 2, [I("jam", F(1), "tbsp")]))
    v.refresh_library(); v.add_recipe(toast2)
    assert v.add_button(toast).isEnabled() and not v.add_button(toast2).isEnabled()
    assert texts(v) == ["jam — 1 tbsp"]
