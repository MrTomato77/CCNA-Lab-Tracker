import aiosqlite
from database.connection import get_db

async def get_all_labs() -> list[dict]:
    db = await get_db()
    # open_session_started_at is NULL unless a timer is currently running.
    # Including it here lets the dashboard render 51 cards from ONE request
    # instead of 51 follow-up GET /api/labs/{id} fetches for attempt history.
    async with db.execute("""
        SELECT l.id, l.name, l.category, l.file_path, l.docs_path,
               p.status, p.time_spent, p.last_opened,
               (SELECT started_at FROM attempts a
                WHERE a.lab_id = l.id AND a.duration IS NULL
                ORDER BY a.started_at DESC LIMIT 1) AS open_session_started_at
        FROM labs l
        JOIN progress p ON l.id = p.lab_id
        ORDER BY l.id
    """) as cur:
        return [dict(r) for r in await cur.fetchall()]

async def get_lab_by_id(lab_id: str) -> dict | None:
    db = await get_db()
    async with db.execute("""
        SELECT l.id, l.name, l.category, l.file_path, l.docs_path,
               p.status, p.time_spent, p.last_opened
        FROM labs l
        JOIN progress p ON l.id = p.lab_id
        WHERE l.id = ?
    """, (lab_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    result = dict(row)
    # Fetch attempts — order DESC so open session (NULL duration) is first
    async with db.execute("""
        SELECT id, started_at, duration
        FROM attempts WHERE lab_id = ?
        ORDER BY started_at DESC
    """, (lab_id,)) as cur:
        result["attempts"] = [dict(a) for a in await cur.fetchall()]
    return result

async def update_status(lab_id: str, status: str) -> bool:
    db = await get_db()
    # Use per-statement cur.rowcount — db.total_changes is cumulative across
    # the connection's lifetime and will report True for every call after
    # the first successful update anywhere.
    async with db.execute(
        "UPDATE progress SET status=? WHERE lab_id=?",
        (status, lab_id)
    ) as cur:
        changed = cur.rowcount > 0
    await db.commit()
    return changed

async def update_last_opened(lab_id: str, timestamp: str):
    db = await get_db()
    await db.execute(
        "UPDATE progress SET last_opened=? WHERE lab_id=?",
        (timestamp, lab_id)
    )
    await db.commit()

async def get_file_path(lab_id: str) -> str | None:
    db = await get_db()
    async with db.execute("SELECT file_path FROM labs WHERE id=?", (lab_id,)) as cur:
        row = await cur.fetchone()
    return row["file_path"] if row else None

async def reset_all_labs():
    """Reset all labs to Not Started status and clear all timer data."""
    db = await get_db()
    await db.execute(
        "UPDATE progress SET status='not_started', time_spent=0, last_opened=NULL"
    )
    await db.execute("DELETE FROM attempts")
    await db.commit()

async def reset_lab(lab_id: str):
    """Reset a specific lab to Not Started and clear its attempts."""
    db = await get_db()
    await db.execute(
        "UPDATE progress SET status='not_started', time_spent=0, last_opened=NULL WHERE lab_id=?",
        (lab_id,)
    )
    await db.execute("DELETE FROM attempts WHERE lab_id=?", (lab_id,))
    await db.commit()
