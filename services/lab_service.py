import json

import aiosqlite
from core.constants import STATUS_NOT_STARTED
from core.responses import ErrorResponse, lab_not_found
from database.connection import get_db
from loguru import logger

async def get_all_labs() -> list[dict]:
    db = await get_db()
    # open_session_started_at is NULL unless a timer is currently running.
    # Including it here lets the dashboard render 51 cards from ONE request
    # instead of 51 follow-up GET /api/labs/{id} fetches for attempt history.
    async with db.execute("""
        SELECT l.id, l.name, l.category, l.file_path, l.docs_path,
               l.difficulty, l.estimated_minutes,
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

async def update_last_opened(lab_id: str, timestamp: str) -> None:
    db = await get_db()
    async with db.execute(
        "UPDATE progress SET last_opened=? WHERE lab_id=?",
        (timestamp, lab_id)
    ):
        pass
    await db.commit()

async def get_file_path(lab_id: str) -> str | None:
    db = await get_db()
    async with db.execute("SELECT file_path FROM labs WHERE id=?", (lab_id,)) as cur:
        row = await cur.fetchone()
    return row["file_path"] if row else None

async def reset_all_labs() -> None:
    """Reset all labs to Not Started status and clear all timer data."""
    db = await get_db()
    await db.execute(
        "UPDATE progress SET status=?, time_spent=0, last_opened=NULL",
        (STATUS_NOT_STARTED,),
    )
    await db.execute("DELETE FROM attempts")
    await db.commit()

async def reset_lab(lab_id: str) -> None:
    """Reset a specific lab to Not Started and clear its attempts."""
    db = await get_db()
    await db.execute(
        "UPDATE progress SET status=?, time_spent=0, last_opened=NULL WHERE lab_id=?",
        (STATUS_NOT_STARTED, lab_id),
    )
    await db.execute("DELETE FROM attempts WHERE lab_id=?", (lab_id,))
    await db.commit()

async def list_with_paths() -> list[dict]:
    """Used by /api/import/status to show which labs have .pka and .pdf files."""
    db = await get_db()
    async with db.execute(
        "SELECT id, name, category, file_path, docs_path FROM labs ORDER BY id"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


def _safe_json(raw: str | None, lab_id: str, field: str) -> list | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.bind(name="db").error(f"Corrupt JSON in labs.{field} for {lab_id}: {raw!r}")
        return None


async def read_summary(lab_id: str) -> dict | None:
    """Return cheat-sheet dict for the lab. Returns None when the lab
    has no summary content at all (all 4 columns NULL); otherwise omits
    any individual NULL field from the dict so the frontend renders
    only populated sections."""
    db = await get_db()
    async with db.execute(
        "SELECT summary, core_commands, verify_commands, gotchas FROM labs WHERE id = ?",
        (lab_id,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    out: dict = {}
    if row["summary"]:
        out["summary"] = row["summary"]
    core_commands = _safe_json(row["core_commands"], lab_id, "core_commands")
    if core_commands is not None:
        out["core_commands"] = core_commands
    verify_commands = _safe_json(row["verify_commands"], lab_id, "verify_commands")
    if verify_commands is not None:
        out["verify_commands"] = verify_commands
    gotchas = _safe_json(row["gotchas"], lab_id, "gotchas")
    if gotchas is not None:
        out["gotchas"] = gotchas
    return out or None


async def require_lab(lab_id: str | None) -> tuple[dict | None, ErrorResponse | None]:
    """Lookup helper for routers: returns (lab, None) when found, or
    (None, lab_not_found_response) when missing. Centralizes the
    `if not await get_lab_by_id(lab_id): return lab_not_found(lab_id)`
    pattern that was duplicated across 6 route handlers."""
    lab = await get_lab_by_id(lab_id)
    if not lab:
        return None, lab_not_found(lab_id)
    return lab, None
