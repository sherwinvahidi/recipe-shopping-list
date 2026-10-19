import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from fractions import Fraction
from typing import Iterator

from shopping_list.core.models import Ingredient, Recipe, RecipeSummary
from shopping_list.core.validation import normalize_recipe_name


class RecipeRepository:
    """Write methods do not commit; wrap them in `transaction()`."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self.conn.in_transaction:
            raise RuntimeError("transaction already open")
        self.conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise
        else:
            try:
                self.conn.execute("COMMIT")
            except BaseException:
                if self.conn.in_transaction:
                    self.conn.execute("ROLLBACK")
                raise

    def add(self, recipe: Recipe) -> int:
        cur = self.conn.execute(
            "INSERT INTO recipes (name, servings, created_at) VALUES (?, ?, ?)",
            (recipe.name, recipe.servings, datetime.now(timezone.utc).isoformat()),
        )
        rid = cur.lastrowid
        self.conn.executemany(
            "INSERT INTO ingredients (recipe_id, position, name, quantity, unit) VALUES (?, ?, ?, ?, ?)",
            [
                (rid, pos, ing.name, None if ing.quantity is None else str(ing.quantity), ing.unit)
                for pos, ing in enumerate(recipe.ingredients)
            ],
        )
        return rid

    def replace(self, existing_id: int, recipe: Recipe) -> int:
        # Insert before deleting: without AUTOINCREMENT, SQLite would reuse the
        # old id if it was the highest rowid, so the new id must differ.
        new_id = self.add(recipe)
        self.delete(existing_id)
        return new_id

    def delete(self, recipe_id: int) -> None:
        cur = self.conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
        if cur.rowcount == 0:
            raise KeyError(recipe_id)

    def get(self, recipe_id: int) -> Recipe:
        row = self.conn.execute(
            "SELECT name, servings FROM recipes WHERE id = ?", (recipe_id,)
        ).fetchone()
        if row is None:
            raise KeyError(recipe_id)
        rows = self.conn.execute(
            "SELECT name, quantity, unit FROM ingredients WHERE recipe_id = ? ORDER BY position",
            (recipe_id,),
        ).fetchall()
        ingredients = [
            Ingredient(n, None if q is None else Fraction(q), u) for n, q, u in rows
        ]
        return Recipe(row[0], row[1], ingredients, id=recipe_id)

    def list_summaries(self) -> list[RecipeSummary]:
        rows = self.conn.execute(
            "SELECT r.id, r.name, r.servings, COUNT(i.id) FROM recipes r "
            "LEFT JOIN ingredients i ON i.recipe_id = r.id GROUP BY r.id"
        ).fetchall()
        summaries = [RecipeSummary(*row) for row in rows]
        summaries.sort(key=lambda s: (normalize_recipe_name(s.name), s.id))
        return summaries

    def find_by_name(self, name: str) -> list[RecipeSummary]:
        target = normalize_recipe_name(name)
        return [s for s in self.list_summaries() if normalize_recipe_name(s.name) == target]
