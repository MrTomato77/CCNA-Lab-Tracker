import aiosqlite
from pathlib import Path

DB_PATH    = Path(__file__).parent / "labs.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_db: aiosqlite.Connection | None = None

async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        raise RuntimeError("DB not initialized. Call init_db() first via startup_handler.")
    return _db

async def init_db():
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row   # access columns as row["name"]
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    # Idempotent migration: docs_path was added after the initial schema.
    # CREATE TABLE IF NOT EXISTS won't add the column to an existing table,
    # so apply ALTER TABLE here and swallow the "duplicate column" error
    # on subsequent boots.
    try:
        await _db.execute("ALTER TABLE labs ADD COLUMN docs_path TEXT DEFAULT NULL")
    except aiosqlite.OperationalError:
        pass
    for col in ("difficulty INTEGER", "estimated_minutes INTEGER"):
        try:
            await _db.execute(f"ALTER TABLE labs ADD COLUMN {col} DEFAULT NULL")
        except aiosqlite.OperationalError:
            pass
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

async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None
