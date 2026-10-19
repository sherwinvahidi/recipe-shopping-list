import sqlite3
from pathlib import Path

# Index i upgrades PRAGMA user_version i -> i+1.
MIGRATIONS: list[str] = [
    """
    CREATE TABLE recipes (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        servings INTEGER NOT NULL CHECK (servings > 0),
        created_at TEXT NOT NULL
    );
    CREATE TABLE ingredients (
        id INTEGER PRIMARY KEY,
        recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        name TEXT NOT NULL,
        quantity TEXT NULL,
        unit TEXT NULL
    );
    CREATE INDEX ix_ingredients_recipe_id ON ingredients(recipe_id);
    """,
]


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i in range(version, len(MIGRATIONS)):
        # Each migration and its version bump commit together or not at all.
        script = f"BEGIN;\n{MIGRATIONS[i]}\nPRAGMA user_version = {i + 1};\nCOMMIT;"
        try:
            conn.executescript(script)
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _migrate(conn)
    except Exception:
        conn.close()
        raise
    return conn
