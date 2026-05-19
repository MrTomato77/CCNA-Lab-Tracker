"""Shared pytest fixtures.

Tests use in-memory SQLite via aiosqlite. The app's connection module
holds a module-level `_db` singleton; tests swap it for a fresh
in-memory connection so nothing touches the real labs.db.
"""
import sys
from pathlib import Path

import aiosqlite
import pytest_asyncio

# Make repo root importable when tests are run from the repo root.
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from database import connection as conn_mod  # noqa: E402


@pytest_asyncio.fixture
async def tmp_db():
    """Fresh in-memory DB with the production schema applied."""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    schema = (REPO_ROOT / "database" / "schema.sql").read_text(encoding="utf-8")
    await db.executescript(schema)
    quiz_schema = (REPO_ROOT / "database" / "quiz_schema.sql").read_text(encoding="utf-8")
    await db.executescript(quiz_schema)
    await db.commit()

    saved, conn_mod._db = conn_mod._db, db
    try:
        yield db
    finally:
        conn_mod._db = saved
        await db.close()


@pytest_asyncio.fixture
async def seeded_db(tmp_db):
    """tmp_db with one synthetic lab row + a progress row, enough for
    timer / progress tests without pulling the full 51-lab seed."""
    await tmp_db.execute(
        "INSERT INTO labs (id, name, category) VALUES (?,?,?)",
        ("LAB-01", "Test Lab", "CLI & Basic"),
    )
    await tmp_db.execute(
        "INSERT INTO progress (lab_id, status, time_spent) VALUES (?,?,?)",
        ("LAB-01", "not_started", 0),
    )
    await tmp_db.commit()
    yield tmp_db
