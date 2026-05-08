"""Aggregate statistics for the analytics page."""
from core.constants import STATUS_DONE, STATUS_IN_PROGRESS, STATUS_NOT_STARTED
from database.connection import get_db


async def summary() -> dict:
    """Total / per-status counts + total time spent + import progress."""
    db = await get_db()
    async with db.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN p.status=? THEN 1 ELSE 0 END) AS done,
            SUM(CASE WHEN p.status=? THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN p.status=? THEN 1 ELSE 0 END) AS not_started,
            SUM(p.time_spent)                           AS total_time_spent,
            SUM(CASE WHEN l.file_path IS NOT NULL THEN 1 ELSE 0 END) AS imported
        FROM progress p JOIN labs l ON p.lab_id = l.id
    """, (STATUS_DONE, STATUS_IN_PROGRESS, STATUS_NOT_STARTED)) as cur:
        row = dict(await cur.fetchone())
    total = row["total"] or 1
    row["completion_percent"] = round((row["done"] / total) * 100, 1)
    return row


async def by_category() -> list[dict]:
    """Per-category status counts, ordered alphabetically."""
    db = await get_db()
    async with db.execute("""
        SELECT
            l.category,
            COUNT(*) AS total,
            SUM(CASE WHEN p.status=? THEN 1 ELSE 0 END) AS done,
            SUM(CASE WHEN p.status=? THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN p.status=? THEN 1 ELSE 0 END) AS not_started
        FROM labs l
        JOIN progress p ON l.id = p.lab_id
        GROUP BY l.category
        ORDER BY l.category
    """, (STATUS_DONE, STATUS_IN_PROGRESS, STATUS_NOT_STARTED)) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def slowest(limit: int = 5) -> list[dict]:
    """Labs with the highest accumulated time_spent — for finding bottlenecks."""
    db = await get_db()
    async with db.execute("""
        SELECT l.id, l.name, p.time_spent
        FROM labs l
        JOIN progress p ON l.id = p.lab_id
        WHERE p.time_spent > 0
        ORDER BY p.time_spent DESC
        LIMIT ?
    """, (limit,)) as cur:
        return [dict(r) for r in await cur.fetchall()]
