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

async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None
