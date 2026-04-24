import aiosqlite
from database.connection import get_db

async def save_timer_session(lab_id: str, started_at: str, duration: int) -> int:
    """
    duration == 0  → open new session (INSERT with NULL duration)
    duration  > 0  → close most recent open session (UPDATE + accumulate)

    Returns updated total time_spent for this lab.
    """
    db = await get_db()

    if duration == 0:
        # Start: persist open session immediately so timer survives refresh
        await db.execute(
            "INSERT INTO attempts (lab_id, started_at, duration) VALUES (?,?,NULL)",
            (lab_id, started_at)
        )
        await db.commit()
    else:
        # Stop: close the most recent open session for this lab
        await db.execute("""
            UPDATE attempts
            SET duration = ?
            WHERE id = (
                SELECT id FROM attempts
                WHERE lab_id = ? AND duration IS NULL
                ORDER BY started_at DESC
                LIMIT 1
            )
        """, (duration, lab_id))
        # Accumulate into progress.time_spent
        await db.execute(
            "UPDATE progress SET time_spent = time_spent + ? WHERE lab_id = ?",
            (duration, lab_id)
        )
        await db.commit()

    # Return updated total
    async with db.execute(
        "SELECT time_spent FROM progress WHERE lab_id=?", (lab_id,)
    ) as cur:
        row = await cur.fetchone()
    return row["time_spent"] if row else 0
