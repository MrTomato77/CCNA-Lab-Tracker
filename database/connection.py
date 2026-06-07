import asyncio

import aiosqlite
from pathlib import Path
from loguru import logger

DB_PATH          = Path(__file__).parent / "labs.db"
SCHEMA_PATH      = Path(__file__).parent / "schema.sql"
QUIZ_SCHEMA_PATH = Path(__file__).parent / "quiz_schema.sql"

_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()
_ALLOWED_MIGRATION_TABLES = frozenset({"labs", "progress", "attempts", "quiz_sessions", "questions"})


async def _add_column_if_missing(
    db: aiosqlite.Connection,
    table: str,
    col: str,
    decl: str,
) -> None:
    """PRAGMA-driven additive migration — pre-checks column list so real errors
    (locked DB, disk full) propagate instead of being swallowed as duplicates."""
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


async def _run_schema_migrations(db: aiosqlite.Connection) -> None:
    await db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    await db.executescript(QUIZ_SCHEMA_PATH.read_text(encoding="utf-8"))
    await _add_column_if_missing(db, "labs", "docs_path",         "TEXT DEFAULT NULL")
    await _add_column_if_missing(db, "labs", "difficulty",        "INTEGER DEFAULT NULL")
    await _add_column_if_missing(db, "labs", "estimated_minutes", "INTEGER DEFAULT NULL")
    await _add_column_if_missing(db, "labs", "summary",           "TEXT DEFAULT NULL")
    await _add_column_if_missing(db, "labs", "core_commands",     "TEXT DEFAULT NULL")
    await _add_column_if_missing(db, "labs", "verify_commands",   "TEXT DEFAULT NULL")
    await _add_column_if_missing(db, "labs", "gotchas",           "TEXT DEFAULT NULL")
    # v2 quiz columns — additive, idempotent.
    await _add_column_if_missing(db, "quiz_sessions", "batch_size",  "INTEGER")
    await _add_column_if_missing(db, "quiz_sessions", "best_streak", "INTEGER NOT NULL DEFAULT 0")
    # Drag-and-drop support: a second question type whose answer is a set of
    # left→right (item→bucket) pairs, authored into questions.pairs_json.
    await _add_column_if_missing(db, "questions", "question_type", "TEXT NOT NULL DEFAULT 'mcq'")
    await _add_column_if_missing(db, "questions", "pairs_json",    "TEXT")


async def _cleanup_stale_attempts(db: aiosqlite.Connection) -> None:
    # Zombie-session guard: a crash mid-timer leaves duration IS NULL, which
    # would resume as a multi-day timer. Delete without crediting time.
    await db.execute("DELETE FROM attempts WHERE duration IS NULL")


async def _seed_if_empty(db: aiosqlite.Connection) -> None:
    async with db.execute("SELECT COUNT(*) FROM labs") as cur:
        if (await cur.fetchone())[0] == 0:
            from database.seed import seed_labs
            await seed_labs(db)


async def _sync_asset_paths(db: aiosqlite.Connection) -> None:
    # Derive each lab's "has docs?" / "imported?" markers from the assets table
    # (the portable source of truth). Stored as the bare filename — a truthy,
    # machine-independent value the UI's `lab.docs_path` / `lab.file_path` checks
    # rely on — never a machine-specific absolute path.
    async with db.execute("SELECT name FROM assets WHERE kind='pdf'") as cur:
        pdfs = {r["name"] for r in await cur.fetchall()}
    async with db.execute("SELECT name FROM assets WHERE kind='pka'") as cur:
        pkas = {r["name"] for r in await cur.fetchall()}
    async with db.execute("SELECT id FROM labs") as cur:
        lab_ids = [r["id"] for r in await cur.fetchall()]
    for lab_id in lab_ids:
        pdf_name = f"{lab_id}.pdf"
        pka_name = f"{lab_id}.pka"
        await db.execute(
            "UPDATE labs SET docs_path=?, file_path=? WHERE id=?",
            (
                pdf_name if pdf_name in pdfs else None,
                pka_name if pka_name in pkas else None,
                lab_id,
            ),
        )


async def init_db() -> None:
    """Initialize the process-wide SQLite connection and run migrations."""
    global _db
    async with _db_lock:
        if _db is not None:
            return
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
        await _run_schema_migrations(_db)
        await _cleanup_stale_attempts(_db)
        await _db.commit()
        await _seed_if_empty(_db)
        await _sync_asset_paths(_db)
        await _db.commit()


async def close_db() -> None:
    """Close the process-wide SQLite connection if it is open."""
    global _db
    async with _db_lock:
        if _db is None:
            return
        await _db.close()
        _db = None
