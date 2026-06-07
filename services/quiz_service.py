"""Business logic for the Quiz/Practice module (v2 — unified queue).

Quiz tables (`questions`, `quiz_sessions`, `quiz_answers`, `question_progress`)
share the SQLite file with the lab tracker but no foreign keys cross the
boundary — this module never imports from `services/lab_service.py`.

v2 dropped the pool-picker model. Mastery is per-question and persists
across sessions: a question is mastered when ``question_progress.correct_streak``
reaches 2; mastered questions are excluded from ``next_question`` candidates.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from core.responses import ErrorResponse, api_error
from database.connection import get_db

ALREADY_ANSWERED = {"already_answered": True}
"""Sentinel returned by ``submit_answer`` when the question was already
answered in this session — the router maps it to 409."""

VALID_BATCH_SIZES: frozenset[int | str] = frozenset({25, 50, 75, 100, "ENDLESS"})

# Process-wide cache of in-flight session_streak counters. The session_streak
# is the current correct-streak within the live session — used to bump
# quiz_sessions.best_streak. Cleared on finish or process restart.
_session_streak: dict[int, int] = {}

_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _now_iso() -> str:
    """ISO-8601 UTC second-resolution, e.g. ``2026-05-19T12:34:56Z``."""
    return datetime.now(timezone.utc).strftime(_ISO_FMT)


# ── Candidate pool helper ───────────────────────────────────────────────

async def _candidate_count(db: aiosqlite.Connection) -> int:
    """Number of quizable questions whose progress (if any) is below mastery."""
    async with db.execute(
        """
        SELECT COUNT(*) FROM questions q
         LEFT JOIN question_progress p ON p.question_id = q.id
         WHERE q.needs_review = 0
           AND COALESCE(p.correct_streak, 0) < 2
        """
    ) as cur:
        return (await cur.fetchone())[0]


# ── Session lifecycle ───────────────────────────────────────────────────

async def start_session(batch_size: int | str) -> tuple[int, int]:
    """Open a session for *batch_size*; return ``(session_id, picked_n)``.

    ``batch_size`` must be one of {25, 50, 75, 100, "ENDLESS"}.
    ``picked_n`` is the effective cap given the current candidate count;
    for ENDLESS it equals all candidates.
    """
    if batch_size not in VALID_BATCH_SIZES:
        raise ValueError(
            f"batch_size must be one of {sorted(VALID_BATCH_SIZES, key=str)!r}"
        )
    db = await get_db()
    candidates = await _candidate_count(db)
    if batch_size == "ENDLESS":
        picked_n = candidates
        stored_batch = None
    else:
        picked_n = min(batch_size, candidates)
        stored_batch = batch_size
    cur = await db.execute(
        "INSERT INTO quiz_sessions (pool, batch_size, started_at) VALUES ('ALL', ?, ?)",
        (stored_batch, _now_iso()),
    )
    await db.commit()
    return cur.lastrowid, picked_n


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


# ── Question delivery ──────────────────────────────────────────────────

async def next_question(session_id: int) -> dict[str, Any] | None:
    """Pick a random un-mastered question for *session_id*.

    Returns one of:
      * ``None``                       — session row missing (caller bug;
                                         router should have called require_session)
      * ``{"exhausted": True}``        — batch cap hit or no candidates
      * ``{question_id, prompt_en, prompt_th, choices, multi, image_urls,
         current_streak, position: {seen, total | None}}``

    Never leaks ``correct_labels`` or ``explanation``.
    """
    db = await get_db()
    session = await _session_row(session_id)
    if session is None:
        # Router pre-check should make this unreachable; raise loudly so
        # a corrupted session can't be mistaken for an exhausted pool.
        raise LookupError(f"session {session_id} disappeared")
    cap = session["batch_size"]   # None == ENDLESS
    seen = session["total_seen"] or 0
    if cap is not None and seen >= cap:
        return {"exhausted": True}

    async with db.execute(
        """
        SELECT q.id, q.prompt_en, q.prompt_th, q.choices_json,
               q.correct_labels, q.image_filenames, q.question_type, q.pairs_json,
               COALESCE(p.correct_streak, 0) AS current_streak
          FROM questions q
          LEFT JOIN question_progress p ON p.question_id = q.id
         WHERE q.needs_review = 0
           AND COALESCE(p.correct_streak, 0) < 2
           AND q.id NOT IN (
               SELECT question_id FROM quiz_answers WHERE session_id = ?
           )
         ORDER BY RANDOM()
         LIMIT 1
        """,
        (session_id,),
    ) as cur:
        picked = await cur.fetchone()
    if picked is None:
        return {"exhausted": True}

    base = {
        "question_id":    picked["id"],
        "prompt_en":      picked["prompt_en"],
        "prompt_th":      picked["prompt_th"],
        "image_urls": [
            f"/api/quiz/images/{fname}"
            for fname in json.loads(picked["image_filenames"])
        ],
        "current_streak": picked["current_streak"],
        "position":       {"seen": seen, "total": cap},
        "question_type":  picked["question_type"] or "mcq",
    }

    if (picked["question_type"] or "mcq") == "drag_drop":
        pairs = json.loads(picked["pairs_json"] or "{}").get("pairs", [])
        # Bank of left items (shuffled); buckets are the distinct right targets
        # in authored order. The correct mapping is never sent to the client.
        items = [p["left"] for p in pairs]
        random.shuffle(items)
        buckets: list[str] = list(dict.fromkeys(p["right"] for p in pairs))
        return {**base, "items": items, "buckets": buckets}

    correct_count = len(json.loads(picked["correct_labels"]))
    return {
        **base,
        "choices": json.loads(picked["choices_json"]),
        "multi":   correct_count > 1,
    }


# ── Answer flow ────────────────────────────────────────────────────────

async def submit_answer(
    session_id: int,
    question_id: int,
    selected_labels: list[str],
    matches: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Persist an answer and return correctness + reveal info.

    ``selected_labels`` is used for mcq questions; ``matches`` (item→bucket) for
    drag_drop. Returns ``None`` if the question doesn't exist, ``ALREADY_ANSWERED``
    on a repeat submit, else the reveal payload. Also updates per-question and
    per-session streaks.
    """
    db = await get_db()
    async with db.execute(
        "SELECT correct_labels, explanation, question_type, pairs_json "
        "FROM questions WHERE id = ?",
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

    qtype = row["question_type"] or "mcq"
    if qtype == "drag_drop":
        pairs = json.loads(row["pairs_json"] or "{}").get("pairs", [])
        if not pairs:
            return None  # not actually answerable
        authored = {p["left"]: p["right"] for p in pairs}
        matches = matches or {}
        is_correct = (
            len(matches) == len(authored)
            and all(matches.get(left) == right for left, right in authored.items())
        )
        # Store as a JSON list so the summary's json.loads stays list-shaped.
        persisted = json.dumps(
            [f"{left} → {bucket}" for left, bucket in matches.items()],
            ensure_ascii=False,
        )
        reveal: dict[str, Any] = {
            "question_type": "drag_drop",
            "pairs":         pairs,        # correct mapping (reveal after submit)
            "your_matches":  matches,
            "explanation":   row["explanation"],
        }
    else:
        correct_labels = json.loads(row["correct_labels"])
        if not correct_labels:
            # Defence in depth: a quizable mcq must have at least one correct
            # label. Empty would make any selection 'correct'.
            return None
        normalized_selected = sorted(label.upper() for label in selected_labels)
        normalized_correct  = sorted(label.upper() for label in correct_labels)
        is_correct = normalized_selected == normalized_correct
        persisted = json.dumps(selected_labels)
        reveal = {
            "question_type":  "mcq",
            "correct_labels": correct_labels,
            "explanation":    row["explanation"],
        }

    now = _now_iso()
    await db.execute(
        """INSERT INTO quiz_answers
             (session_id, question_id, selected_labels, is_correct, answered_at)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, question_id, persisted, int(is_correct), now),
    )
    await _bump_question_progress(db, question_id, is_correct, now)

    cur_streak = _session_streak.get(session_id, 0)
    cur_streak = cur_streak + 1 if is_correct else 0
    _session_streak[session_id] = cur_streak
    await db.execute(
        """UPDATE quiz_sessions
              SET total_seen    = total_seen + 1,
                  total_correct = total_correct + ?,
                  best_streak   = MAX(best_streak, ?)
            WHERE id = ?""",
        (int(is_correct), cur_streak, session_id),
    )
    await db.commit()
    return {"is_correct": is_correct, **reveal}


async def dont_know(session_id: int, question_id: int) -> dict[str, Any] | None:
    """User opts out of guessing.

    Reveals correct + explanation, resets the per-question streak to 0,
    and counts the question as seen (not correct).

    Returns:
      * ``None``              — question doesn't exist
      * ``ALREADY_ANSWERED``  — repeated submit for this (session, question)
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
    now = _now_iso()
    await db.execute(
        """INSERT INTO quiz_answers
             (session_id, question_id, selected_labels, is_correct, answered_at)
           VALUES (?, ?, '[]', 0, ?)""",
        (session_id, question_id, now),
    )
    await _bump_question_progress(db, question_id, is_correct=False, now=now)
    _session_streak[session_id] = 0
    await db.execute(
        "UPDATE quiz_sessions SET total_seen = total_seen + 1 WHERE id = ?",
        (session_id,),
    )
    await db.commit()
    return {
        "is_correct":     False,
        "correct_labels": correct_labels,
        "explanation":    row["explanation"],
    }


async def _bump_question_progress(
    db: aiosqlite.Connection,
    question_id: int,
    is_correct: bool,
    now: str,
) -> None:
    """UPSERT question_progress: +1 streak on correct, reset to 0 on wrong."""
    # Parameterized CASE WHEN keeps the SQL fully literal — the bool flag
    # is never interpolated into the statement text.
    flag = 1 if is_correct else 0
    await db.execute(
        """
        INSERT INTO question_progress
            (question_id, correct_streak, last_seen_at, last_answer_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(question_id) DO UPDATE SET
            correct_streak = CASE WHEN ? = 1 THEN correct_streak + 1 ELSE 0 END,
            last_seen_at   = excluded.last_seen_at,
            last_answer_at = excluded.last_answer_at
        """,
        (question_id, flag, now, now, flag),
    )


# ── Reset ──────────────────────────────────────────────────────────────

async def reset_progress() -> dict[str, int]:
    """Truncate all quiz tables. Returns row counts per table.

    Clears ``question_progress``, ``quiz_answers``, ``quiz_sessions``, AND
    the in-memory ``_session_streak`` cache. Question content (the
    ``questions`` table) is preserved — it's source-of-truth data from the
    parser.

    Delete order: ``quiz_answers`` first, then ``quiz_sessions``, then
    ``question_progress`` — keeps things safe if anyone re-adds FK
    constraints later.
    """
    db = await get_db()
    counts: dict[str, int] = {}
    # Hard-coded literal tuple — these are not user input, so the f-string
    # below carries no SQL-injection risk.
    for tbl in ("quiz_answers", "quiz_sessions", "question_progress"):
        async with db.execute(f"SELECT COUNT(*) FROM {tbl}") as cur:
            counts[tbl] = (await cur.fetchone())[0]
        await db.execute(f"DELETE FROM {tbl}")
    await db.commit()
    _session_streak.clear()
    return {
        "cleared_progress": counts["question_progress"],
        "cleared_sessions": counts["quiz_sessions"],
        "cleared_answers":  counts["quiz_answers"],
    }


# ── Dashboard ──────────────────────────────────────────────────────────

async def get_dashboard() -> dict[str, Any]:
    """Aggregate counts + recent sessions for the Quiz landing page."""
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM questions") as cur:
        parsed_total = (await cur.fetchone())[0]
    async with db.execute(
        "SELECT COUNT(*) FROM questions WHERE needs_review = 0"
    ) as cur:
        quizable_total = (await cur.fetchone())[0]
    async with db.execute(
        "SELECT COUNT(*) FROM questions WHERE needs_review = 1"
    ) as cur:
        flagged_count = (await cur.fetchone())[0]
    async with db.execute(
        "SELECT COUNT(*) FROM question_progress WHERE correct_streak >= 2"
    ) as cur:
        mastered_count = (await cur.fetchone())[0]
    async with db.execute(
        """SELECT COUNT(*) FROM question_progress
             WHERE correct_streak < 2 AND last_seen_at IS NOT NULL"""
    ) as cur:
        wrong_queue_count = (await cur.fetchone())[0]

    async with db.execute(
        """SELECT id, started_at, ended_at, total_seen, total_correct,
                  best_streak, batch_size
             FROM quiz_sessions
            WHERE batch_size IS NOT NULL
            ORDER BY id DESC
            LIMIT 5"""
    ) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    recent_sessions = [_decorate_session_row(r) for r in rows]
    latest_session = recent_sessions[0] if recent_sessions else None

    return {
        "mastered_count":    mastered_count,
        "quizable_total":    quizable_total,
        "parsed_total":      parsed_total,
        "flagged_count":     flagged_count,
        "wrong_queue_count": wrong_queue_count,
        "recent_sessions":   recent_sessions,
        "latest_session":    latest_session,
    }


def _decorate_session_row(row: dict[str, Any]) -> dict[str, Any]:
    total = row["total_seen"] or 0
    correct = row["total_correct"] or 0
    accuracy = round((correct / total) * 100, 1) if total else 0.0
    duration = _duration_seconds(row["started_at"], row["ended_at"])
    return {**row, "accuracy": accuracy, "duration_sec": duration}


# ── Finish + summary ───────────────────────────────────────────────────

async def finish_session(session_id: int) -> dict[str, Any] | None:
    """Mark *session_id* ended (if not already) and return its summary."""
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
    _session_streak.pop(session_id, None)
    return await get_summary(session_id)


async def get_summary(session_id: int) -> dict[str, Any] | None:
    """Read a session's final-or-in-progress totals + wrong-answer detail."""
    session = await _session_row(session_id)
    if session is None:
        return None
    total = session["total_seen"] or 0
    correct = session["total_correct"] or 0
    accuracy = round((correct / total) * 100, 1) if total else 0.0
    duration = _duration_seconds(session["started_at"], session["ended_at"])

    db = await get_db()
    async with db.execute(
        """SELECT q.id AS question_id, q.prompt_en, q.prompt_th, q.choices_json,
                  q.correct_labels, q.explanation, a.selected_labels
             FROM quiz_answers a
             JOIN questions q ON q.id = a.question_id
            WHERE a.session_id = ? AND a.is_correct = 0
            ORDER BY a.id ASC""",
        (session_id,),
    ) as cur:
        wrong_rows = await cur.fetchall()
    wrong_answers = [
        {
            "question_id":     r["question_id"],
            "prompt_en":       r["prompt_en"],
            "prompt_th":       r["prompt_th"],
            "choices":         json.loads(r["choices_json"]),
            "correct_labels":  json.loads(r["correct_labels"]),
            "selected_labels": json.loads(r["selected_labels"]),
            "explanation":     r["explanation"],
        }
        for r in wrong_rows
    ]

    async with db.execute(
        """SELECT q.id AS question_id, q.prompt_en, q.prompt_th, q.choices_json,
                  q.correct_labels, q.explanation, a.selected_labels
             FROM quiz_answers a
             JOIN questions q ON q.id = a.question_id
            WHERE a.session_id = ? AND a.is_correct = 1
            ORDER BY a.id ASC""",
        (session_id,),
    ) as cur:
        correct_rows = await cur.fetchall()
    correct_answers = [
        {
            "question_id":     r["question_id"],
            "prompt_en":       r["prompt_en"],
            "prompt_th":       r["prompt_th"],
            "choices":         json.loads(r["choices_json"]),
            "correct_labels":  json.loads(r["correct_labels"]),
            "selected_labels": json.loads(r["selected_labels"]),
            "explanation":     r["explanation"],
        }
        for r in correct_rows
    ]

    return {
        "session_id":      session_id,
        "batch_size":      session["batch_size"],
        "started_at":      session["started_at"],
        "ended_at":        session["ended_at"],
        "total_seen":      total,
        "total_correct":   correct,
        "accuracy":        accuracy,
        "duration_sec":    duration,
        "best_streak":     session["best_streak"] or 0,
        "wrong_answers":   wrong_answers,
        "correct_answers": correct_answers,
    }


# ── Time helpers ───────────────────────────────────────────────────────

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
