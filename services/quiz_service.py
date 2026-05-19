"""Business logic for the Quiz/Practice module.

Quiz tables (`questions`, `quiz_sessions`, `quiz_answers`) share the SQLite
file with the lab tracker but no foreign keys cross the boundary — this
module never imports from `services/lab_service.py` or vice-versa.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from core.exam_pools import POOL_ALL, POOL_LABELS, POOL_VALUES, SESSION_POOL_VALUES
from core.responses import ErrorResponse, api_error
from database.connection import get_db

ALREADY_ANSWERED = {"already_answered": True}
"""Sentinel returned by ``submit_answer`` when the question was already
answered in this session — the router maps it to 409."""

_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _now_iso() -> str:
    """ISO-8601 UTC second-resolution, e.g. ``2026-05-19T12:34:56Z``."""
    return datetime.now(timezone.utc).strftime(_ISO_FMT)


async def list_pools() -> list[dict[str, Any]]:
    """Return per-pool question counts (quizable only) plus an `ALL` row."""
    db = await get_db()
    async with db.execute(
        """
        SELECT pool, COUNT(*) AS n
          FROM questions
         WHERE needs_review = 0
         GROUP BY pool
        """
    ) as cur:
        counts = {row["pool"]: row["n"] for row in await cur.fetchall()}

    out = [
        {"id": pool, "name": POOL_LABELS[pool], "question_count": counts.get(pool, 0)}
        for pool in POOL_VALUES
    ]
    out.append({
        "id": POOL_ALL,
        "name": POOL_LABELS[POOL_ALL],
        "question_count": sum(counts.values()),
    })
    return out


async def start_session(pool: str) -> int:
    """Open a session for *pool*; return its id."""
    if pool not in SESSION_POOL_VALUES:
        raise ValueError(f"invalid pool {pool!r}")
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO quiz_sessions (pool, started_at) VALUES (?, ?)",
        (pool, _now_iso()),
    )
    await db.commit()
    return cur.lastrowid


async def _session_row(session_id: int) -> dict[str, Any] | None:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM quiz_sessions WHERE id = ?", (session_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def require_session(
    session_id: int,
) -> tuple[dict[str, Any] | None, ErrorResponse | None]:
    """Mirror of `lab_service.require_lab` — return (row, err) for the router."""
    row = await _session_row(session_id)
    if row is None:
        return None, api_error(
            f"Session {session_id} not found.", "SESSION_NOT_FOUND", 404,
        )
    return row, None


async def next_question(session_id: int) -> dict[str, Any] | None:
    """Pick a random unseen quizable question for *session_id*.

    Returns the question payload without leaking the correct answer, or
    `None` when the session has exhausted its pool. The router must have
    already verified the session exists via ``require_session`` — this
    function assumes the session row is valid.
    """
    db = await get_db()
    session = await _session_row(session_id)
    if session is None:
        # Router pre-check should make this unreachable; raise loudly so
        # a corrupted session can't be mistaken for an exhausted pool.
        raise LookupError(f"session {session_id} disappeared")

    pool = session["pool"]
    if pool == POOL_ALL:
        pool_filter = ""
        params: tuple[Any, ...] = (session_id,)
    else:
        pool_filter = "AND q.pool = ?"
        params = (session_id, pool)

    sql = f"""
        SELECT q.id, q.prompt_en, q.prompt_th, q.choices_json,
               q.correct_labels, q.image_filenames
          FROM questions q
         WHERE q.needs_review = 0
           AND q.id NOT IN (
               SELECT question_id FROM quiz_answers WHERE session_id = ?
           )
           {pool_filter}
         ORDER BY RANDOM()
         LIMIT 1
    """
    async with db.execute(sql, params) as cur:
        picked = await cur.fetchone()
    if picked is None:
        return None

    correct_count = len(json.loads(picked["correct_labels"]))
    return {
        "question_id":  picked["id"],
        "prompt_en":    picked["prompt_en"],
        "prompt_th":    picked["prompt_th"],
        "choices":      json.loads(picked["choices_json"]),
        "multi":        correct_count > 1,
        "image_urls":   [
            f"/api/quiz/images/{fname}"
            for fname in json.loads(picked["image_filenames"])
        ],
    }


async def submit_answer(
    session_id: int,
    question_id: int,
    selected_labels: list[str],
) -> dict[str, Any] | None:
    """Persist an answer and return correctness + reveal info.

    Returns:
        * ``None`` if the question doesn't exist
        * ``ALREADY_ANSWERED`` (sentinel dict) if the question has been
          answered in this session — the second submission is ignored
          so a repeated POST can't inflate ``total_correct``
        * ``{is_correct, correct_labels, explanation}`` on success
    """
    db = await get_db()
    async with db.execute(
        "SELECT correct_labels, explanation FROM questions WHERE id = ?",
        (question_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None

    async with db.execute(
        "SELECT 1 FROM quiz_answers WHERE session_id = ? AND question_id = ?",
        (session_id, question_id),
    ) as cur:
        if await cur.fetchone() is not None:
            return ALREADY_ANSWERED

    correct_labels = json.loads(row["correct_labels"])
    if not correct_labels:
        # Defence in depth: a quizable question must have at least one
        # correct label. Empty would make any selection 'correct'.
        return None
    normalized_selected = sorted(label.upper() for label in selected_labels)
    normalized_correct  = sorted(label.upper() for label in correct_labels)
    is_correct = normalized_selected == normalized_correct

    await db.execute(
        """
        INSERT INTO quiz_answers
            (session_id, question_id, selected_labels, is_correct, answered_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            session_id,
            question_id,
            json.dumps(selected_labels),
            int(is_correct),
            _now_iso(),
        ),
    )
    await db.execute(
        """
        UPDATE quiz_sessions
           SET total_seen    = total_seen + 1,
               total_correct = total_correct + ?
         WHERE id = ?
        """,
        (int(is_correct), session_id),
    )
    await db.commit()
    return {
        "is_correct":     is_correct,
        "correct_labels": correct_labels,
        "explanation":    row["explanation"],
    }


async def finish_session(session_id: int) -> dict[str, Any] | None:
    """Mark *session_id* ended (if not already) and return a summary."""
    db = await get_db()
    session = await _session_row(session_id)
    if session is None:
        return None
    if session["ended_at"] is None:
        await db.execute(
            "UPDATE quiz_sessions SET ended_at = ? WHERE id = ?",
            (_now_iso(), session_id),
        )
        await db.commit()
    return await get_summary(session_id)


async def get_summary(session_id: int) -> dict[str, Any] | None:
    """Read a session's final or in-progress totals."""
    session = await _session_row(session_id)
    if session is None:
        return None
    total = session["total_seen"] or 0
    correct = session["total_correct"] or 0
    accuracy = round((correct / total) * 100, 1) if total else 0.0
    duration = _duration_seconds(session["started_at"], session["ended_at"])
    return {
        "session_id":    session_id,
        "pool":          session["pool"],
        "started_at":    session["started_at"],
        "ended_at":      session["ended_at"],
        "total_seen":    total,
        "total_correct": correct,
        "accuracy":      accuracy,
        "duration_sec":  duration,
    }


def _duration_seconds(started_at: str | None, ended_at: str | None) -> int | None:
    """Seconds between two ISO-8601 UTC timestamps stored as text."""
    if not started_at:
        return None
    start = _parse_iso(started_at)
    if start is None:
        return None
    if ended_at:
        end = _parse_iso(ended_at)
        if end is None:
            return None
        return int((end - start).total_seconds())
    return int((datetime.now(timezone.utc) - start).total_seconds())


def _parse_iso(value: str) -> datetime | None:
    """Parse ``_ISO_FMT`` text into a timezone-aware UTC datetime."""
    try:
        return datetime.strptime(value, _ISO_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
