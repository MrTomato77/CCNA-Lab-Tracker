import asyncio

import aiosqlite
from pathlib import Path
from loguru import logger

DB_PATH    = Path(__file__).parent / "labs.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()
_ALLOWED_MIGRATION_TABLES = frozenset({"labs", "progress", "attempts"})


async def _add_column_if_missing(
    db: aiosqlite.Connection,
    table: str,
    col: str,
    decl: str,
) -> None:
    """PRAGMA-driven additive migration. The previous try/except-OperationalError
    pattern swallowed real failures (locked DB, disk full, schema corruption)
    as if they were "duplicate column" — leaving the app running on a half-
    migrated schema. Pre-checking the column list lets real errors propagate."""
    if table not in _ALLOWED_MIGRATION_TABLES or not col.isidentifier():
        raise ValueError(f"Unexpected table/col: {table!r}.{col!r}")
    cur  = await db.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in await cur.fetchall()}
    if col not in cols:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        logger.bind(name="db").info(f"migration: added {table}.{col}")

async def get_db() -> aiosqlite.Connection:
    """Return the initialized application database connection."""
    global _db
    if _db is None:
        raise RuntimeError("DB not initialized. Call init_db() first via startup_handler.")
    return _db

async def init_db() -> None:
    """Initialize the process-wide SQLite connection and run migrations."""
    global _db
    async with _db_lock:
        if _db is not None:
            return
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row   # access columns as row["name"]
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
        await _db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        # Idempotent additive migrations. CREATE TABLE IF NOT EXISTS won't add
        # columns to an existing table, so check via PRAGMA table_info and only
        # ALTER when the column is absent. Real errors propagate.
        await _add_column_if_missing(_db, "labs", "docs_path",         "TEXT DEFAULT NULL")
        await _add_column_if_missing(_db, "labs", "difficulty",        "INTEGER DEFAULT NULL")
        await _add_column_if_missing(_db, "labs", "estimated_minutes", "INTEGER DEFAULT NULL")
        await _add_column_if_missing(_db, "labs", "summary",           "TEXT DEFAULT NULL")
        await _add_column_if_missing(_db, "labs", "core_commands",     "TEXT DEFAULT NULL")
        await _add_column_if_missing(_db, "labs", "verify_commands",   "TEXT DEFAULT NULL")
        await _add_column_if_missing(_db, "labs", "gotchas",           "TEXT DEFAULT NULL")
        # Zombie-session cleanup: if the last run crashed mid-timer, an attempts
        # row with duration IS NULL would "resume" on next load as a multi-day
        # timer and add bogus hours to time_spent. Delete stale open sessions —
        # we can't verify their duration, so don't credit any time.
        await _db.execute("DELETE FROM attempts WHERE duration IS NULL")
        await _db.commit()
        async with _db.execute("SELECT COUNT(*) FROM labs") as cur:
            if (await cur.fetchone())[0] == 0:
                from database.seed import seed_labs
                await seed_labs(_db)
        # Auto-detect per-lab PDFs in docs/ and .pka files in labs/. Lets the
        # user run scripts/split_pdf.py / drop new files in either folder and
        # have docs_path / file_path populated on next restart without a
        # separate import step. Also self-heals if either folder gets renamed.
        project_root = Path(__file__).parent.parent
        docs_dir = project_root / "docs"
        labs_dir = project_root / "labs"
        async with _db.execute("SELECT id FROM labs") as cur:
            lab_ids = [r["id"] for r in await cur.fetchall()]
        for lab_id in lab_ids:
            pdf = docs_dir / f"{lab_id}.pdf"
            pka = labs_dir / f"{lab_id}.pka"
            await _db.execute(
                "UPDATE labs SET docs_path=?, file_path=? WHERE id=?",
                (
                    str(pdf) if pdf.exists() else None,
                    str(pka) if pka.exists() else None,
                    lab_id,
                ),
            )
        await _db.commit()

async def close_db() -> None:
    """Close the process-wide SQLite connection if it is open."""
    global _db
    async with _db_lock:
        if _db is None:
            return
        await _db.close()
        _db = None
