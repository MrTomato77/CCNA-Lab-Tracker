from datetime import datetime

from database.connection import get_db

async def save_timer_session(lab_id: str, started_at: datetime, duration: int) -> int:
    """
    duration == 0 → open new session (INSERT with NULL duration)
    duration  > 0 → close most recent open session (UPDATE + accumulate)

    Race safety: UPDATE filters on `duration IS NULL` so two concurrent stops
    can't both close the same row — the second matches zero rows.
    """
    db = await get_db()
    started_at_value = started_at.isoformat()

    if duration == 0:
        await db.execute(
            "INSERT INTO attempts (lab_id, started_at, duration) VALUES (?,?,NULL)",
            (lab_id, started_at_value)
        )
        await db.commit()
    else:
        async with db.execute("""
            UPDATE attempts
            SET duration = ?
            WHERE id = (
                SELECT id FROM attempts
                WHERE lab_id = ? AND duration IS NULL
                ORDER BY started_at DESC
                LIMIT 1
            )
            AND duration IS NULL
        """, (duration, lab_id)) as cur:
            closed = cur.rowcount > 0
        if closed:  # guard against double-credit from concurrent stops
            await db.execute(
                "UPDATE progress SET time_spent = time_spent + ? WHERE lab_id = ?",
                (duration, lab_id)
            )
        await db.commit()

    async with db.execute(
        "SELECT time_spent FROM progress WHERE lab_id=?", (lab_id,)
    ) as cur:
        row = await cur.fetchone()
    return row["time_spent"] if row else 0
