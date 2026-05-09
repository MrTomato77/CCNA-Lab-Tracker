"""Coverage for the timer-stop race condition.

Two concurrent stops used to both UPDATE the same attempts row and
both credit progress.time_spent — doubling the saved time. The current
implementation guards via `WHERE duration IS NULL` + rowcount check.
This test fires both stops in parallel and asserts time_spent is
incremented exactly once.
"""
import asyncio

from services import timer_service


async def test_concurrent_stops_credit_time_only_once(seeded_db):
    started_at = "2026-05-09T10:00:00"
    duration   = 120

    # Start: persist the open session.
    await timer_service.save_timer_session("LAB-01", started_at, 0)

    # Two stops fire at the same time. Only one should win the UPDATE.
    results = await asyncio.gather(
        timer_service.save_timer_session("LAB-01", started_at, duration),
        timer_service.save_timer_session("LAB-01", started_at, duration),
    )

    # Both calls return the latest time_spent; must equal `duration`,
    # not 2*duration.
    async with seeded_db.execute(
        "SELECT time_spent FROM progress WHERE lab_id=?", ("LAB-01",)
    ) as cur:
        row = await cur.fetchone()
    assert row["time_spent"] == duration
    assert max(results) == duration

    # Exactly one closed attempt row.
    async with seeded_db.execute(
        "SELECT COUNT(*) AS n FROM attempts WHERE duration IS NOT NULL"
    ) as cur:
        row = await cur.fetchone()
    assert row["n"] == 1


async def test_open_then_close_accumulates(seeded_db):
    """Sequential open→close→open→close should sum durations."""
    await timer_service.save_timer_session("LAB-01", "2026-05-09T10:00:00", 0)
    await timer_service.save_timer_session("LAB-01", "2026-05-09T10:00:00", 60)
    await timer_service.save_timer_session("LAB-01", "2026-05-09T11:00:00", 0)
    final = await timer_service.save_timer_session("LAB-01", "2026-05-09T11:00:00", 90)
    assert final == 150
