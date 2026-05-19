"""Business logic for the Quiz/Practice module.

Quiz tables (`questions`, `quiz_sessions`, `quiz_answers`) share the SQLite
file with the lab tracker but no foreign keys cross the boundary — this
module never imports from `services/lab_service.py` or vice-versa.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from typing import Any

from core.exam_pools import POOL_ALL, POOL_LABELS, POOL_VALUES, SESSION_POOL_VALUES
from core.responses import ErrorResponse, api_error
from database.connection import get_db


def _now_iso() -> str:
    """ISO-8601 UTC second-resolution, e.g. ``2026-05-19T12:34:56Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    `None` when the session has exhausted its pool.
    """
    db = await get_db()
    session = await _session_row(session_id)
    if session is None:
        return None

    pool = session["pool"]
    pool_filter = "" if pool == POOL_ALL else "AND q.pool = ?"
    params: tuple[Any, ...] = (
        (session_id, pool) if pool != POOL_ALL else (session_id,)
    )

    sql = f"""
        SELECT q.id, q.prompt_en, q.prompt_th, q.choices_json,
               q.correct_labels, q.image_filenames
          FROM questions q
         WHERE q.needs_review = 0
           AND q.id NOT IN (
               SELECT question_id FROM quiz_answers WHERE session_id = ?
           )
           {pool_filter}
    """
    async with db.execute(sql, params) as cur:
        rows = await cur.fetchall()
    if not rows:
        return None

    picked = random.choice(rows)
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

    Returns `None` if the question doesn't exist or has already been
    answered in this session — the second submission is ignored so a
    repeated POST can't inflate `total_correct`.
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
            return None

    correct_labels = json.loads(row["correct_labels"])
    is_correct = sorted(selected_labels) == sorted(correct_labels)

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
    if not started_at:
        return None
    try:
        start = datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    if ended_at:
        try:
            end = datetime.strptime(ended_at, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
        return int((end - start).total_seconds())
    return int((datetime.now(timezone.utc).replace(tzinfo=None) - start).total_seconds())


def is_valid_session_pool(pool: str) -> bool:
    return pool in SESSION_POOL_VALUES
