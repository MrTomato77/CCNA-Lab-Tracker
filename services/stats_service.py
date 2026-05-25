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
    row["completion_percent"] = round(((row["done"] or 0) / total) * 100, 1)
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


# ── Quiz stats ─────────────────────────────────────────────────────────────

async def quiz_summary() -> dict:
    """Quiz aggregate stats: mastered, quizable, total sessions, avg accuracy, best streak."""
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM questions") as cur:
        parsed_total = (await cur.fetchone())[0]
    async with db.execute(
        "SELECT COUNT(*) FROM questions WHERE needs_review = 0"
    ) as cur:
        quizable_total = (await cur.fetchone())[0]
    async with db.execute(
        "SELECT COUNT(*) FROM question_progress WHERE correct_streak >= 2"
    ) as cur:
        mastered_count = (await cur.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM quiz_sessions") as cur:
        total_sessions = (await cur.fetchone())[0]
    async with db.execute("SELECT MAX(best_streak) FROM quiz_sessions") as cur:
        best_streak = (await cur.fetchone())[0] or 0
    
    # Calculate average accuracy across all sessions
    async with db.execute(
        """SELECT AVG(CAST(total_correct AS FLOAT) / NULLIF(total_seen, 0)) * 100
           FROM quiz_sessions WHERE total_seen > 0"""
    ) as cur:
        avg_accuracy = round((await cur.fetchone())[0] or 0.0, 1)
    
    return {
        "mastered_count": mastered_count,
        "quizable_total": quizable_total,
        "parsed_total": parsed_total,
        "total_sessions": total_sessions,
        "avg_accuracy": avg_accuracy,
        "best_streak_ever": best_streak,
    }


async def quiz_accuracy_trend(limit: int = 10) -> list[dict]:
    """Last N sessions with accuracy for trend chart."""
    db = await get_db()
    async with db.execute(
        """SELECT id, started_at, 
                  CAST(total_correct AS FLOAT) / NULLIF(total_seen, 0) * 100 AS accuracy
           FROM quiz_sessions
           WHERE total_seen > 0 AND batch_size IS NOT NULL
           ORDER BY id DESC
           LIMIT ?
        """, (limit,)
    ) as cur:
        rows = await cur.fetchall()
    return [
        {
            "session_id": r["id"],
            "started_at": r["started_at"],
            "accuracy": round(r["accuracy"], 1),
        }
        for r in rows
    ]
