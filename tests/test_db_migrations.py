"""Coverage for the PRAGMA-based additive migration helper.

The previous try/except-OperationalError pattern silently swallowed
every error, masking real failures (locked DB, disk full) as if they
were "duplicate column". The new `_add_column_if_missing` checks
PRAGMA table_info first and only ALTERs when the column is absent.
"""
import aiosqlite
import pytest

from database.connection import _add_column_if_missing

pytestmark = pytest.mark.asyncio


async def _new_db():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute("CREATE TABLE labs (id INTEGER PRIMARY KEY, a INTEGER)")
    await db.commit()
    return db


async def test_adds_missing_column():
    """The helper adds an allowed missing column exactly once."""
    db = await _new_db()
    try:
        await _add_column_if_missing(db, "labs", "b", "INTEGER DEFAULT NULL")
        cur = await db.execute("PRAGMA table_info(labs)")
        cols = {r[1] for r in await cur.fetchall()}
        assert "b" in cols
    finally:
        await db.close()


async def test_idempotent_on_existing_column():
    """Running the migration twice must not raise; the column is left
    intact and no second ALTER is issued."""
    db = await _new_db()
    try:
        await _add_column_if_missing(db, "labs", "b", "INTEGER DEFAULT NULL")
        await _add_column_if_missing(db, "labs", "b", "INTEGER DEFAULT NULL")
        cur = await db.execute("PRAGMA table_info(labs)")
        cols = [r[1] for r in await cur.fetchall()]
        assert cols.count("b") == 1
    finally:
        await db.close()


async def test_real_errors_propagate():
    """Migration on a non-existent table must raise — not be swallowed.
    This is the core regression guard: the old try/except pattern would
    have masked this failure."""
    db = await _new_db()
    try:
        with pytest.raises(aiosqlite.OperationalError):
            await _add_column_if_missing(db, "labs", "x", "INTEGER DEFAULT )")
    finally:
        await db.close()


async def test_rejects_unexpected_table_or_column():
    db = await _new_db()
    try:
        with pytest.raises(ValueError):
            await _add_column_if_missing(db, "no_such_table", "x", "INTEGER")
        with pytest.raises(ValueError):
            await _add_column_if_missing(db, "labs", "bad-name", "INTEGER")
    finally:
        await db.close()
