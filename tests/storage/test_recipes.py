import sqlite3, pytest
from fractions import Fraction as F
from shopping_list.core.models import Recipe, Ingredient, RecipeSummary
from shopping_list.storage.db import connect, MIGRATIONS
from shopping_list.storage.recipes import RecipeRepository

@pytest.fixture
def repo():
    r = RecipeRepository(connect(":memory:"))
    yield r
    r.conn.close()

PANCAKES = Recipe("Pancakes", 4, [Ingredient("flour", F(3, 2), "cup"), Ingredient("egg", F(1), None), Ingredient("salt", None, None)])

def test_schema_version():
    conn = connect(":memory:")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()

def test_migrations_idempotent_on_reopen(tmp_path):
    p = tmp_path / "r.db"; connect(p).close()
    conn = connect(p)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    conn.close()

def test_add_get_roundtrip_exact(repo):
    with repo.transaction():
        rid = repo.add(PANCAKES)
    got = repo.get(rid)
    assert got.ingredients == PANCAKES.ingredients and got.servings == 4 and got.id == rid

def test_list_summaries_sorted(repo):
    with repo.transaction():
        repo.add(Recipe("tea", 1, [Ingredient("tea", F(1), None)])); repo.add(PANCAKES)
    assert [(s.name, s.ingredient_count) for s in repo.list_summaries()] == [("Pancakes", 3), ("tea", 1)]

def test_find_by_name_normalized_and_duplicates_allowed(repo):
    with repo.transaction():
        repo.add(PANCAKES); repo.add(PANCAKES)
    assert len(repo.find_by_name("  pancakes ")) == 2

def test_replace(repo):
    with repo.transaction():
        old = repo.add(PANCAKES)
        new = repo.replace(old, Recipe("Pancakes", 2, [Ingredient("milk", F(1), "cup")]))
    assert [s.id for s in repo.list_summaries()] == [new]
    with pytest.raises(KeyError):
        repo.get(old)

def test_delete_cascades(repo):
    with repo.transaction():
        rid = repo.add(PANCAKES)
    with repo.transaction():
        repo.delete(rid)
    assert repo.conn.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0] == 0

def test_transaction_rollback(repo):
    with pytest.raises(RuntimeError):
        with repo.transaction():
            repo.add(PANCAKES); raise RuntimeError
    assert repo.list_summaries() == []

def test_servings_check_constraint(repo):
    with pytest.raises(sqlite3.IntegrityError):
        with repo.transaction():
            repo.add(Recipe("Bad", 0, []))

def test_get_missing_raises_keyerror(repo):
    with pytest.raises(KeyError):
        repo.get(999)

def test_replace_and_delete_missing_raise_and_roll_back(repo):
    with repo.transaction():
        keep = repo.add(PANCAKES)
    with pytest.raises(KeyError):
        with repo.transaction():
            repo.add(PANCAKES)
            repo.replace(999, PANCAKES)
    with pytest.raises(KeyError):
        with repo.transaction():
            repo.delete(999)
    assert [s.id for s in repo.list_summaries()] == [keep]

def test_transaction_not_reentrant(repo):
    with repo.transaction():
        with pytest.raises(RuntimeError, match="transaction already open"):
            with repo.transaction():
                pass
    with repo.transaction():  # still usable afterwards
        repo.add(PANCAKES)

def test_ingredient_order_preserved(repo):
    names = ["z", "a", "m"]
    with repo.transaction():
        rid = repo.add(Recipe("R", 1, [Ingredient(n, None, None) for n in names]))
    assert [i.name for i in repo.get(rid).ingredients] == names

def test_summaries_case_insensitive_sort_and_summary_type(repo):
    with repo.transaction():
        for n in ["banana", "Apple", "cherry"]:
            repo.add(Recipe(n, 1, []))
    sums = repo.list_summaries()
    assert [s.name for s in sums] == ["Apple", "banana", "cherry"]
    assert isinstance(sums[0], RecipeSummary) and sums[0].ingredient_count == 0

def test_failed_migration_is_atomic(monkeypatch, tmp_path):
    import shopping_list.storage.db as db
    monkeypatch.setattr(db, "MIGRATIONS", ["CREATE TABLE a (x INTEGER); CREATE TABLE a (x INTEGER);"])
    p = tmp_path / "bad.db"
    with pytest.raises(sqlite3.Error):
        db.connect(p)
    c = sqlite3.connect(p)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='a'").fetchone()[0] == 0
    c.close()
