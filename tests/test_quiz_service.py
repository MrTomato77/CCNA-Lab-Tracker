"""Tests for services/quiz_service.py (v2 — unified queue)."""
from __future__ import annotations

import json

import pytest

from services import quiz_service as svc


async def _seed(db, *, id: int, pool: str = "A", correct: list[str] | None = None,
                explanation: str = "Reason.", needs_review: int = 0,
                image_filenames: list[str] | None = None,
                streak: int | None = None) -> None:
    """Insert a quizable question + optional question_progress row.

    `streak` lets tests construct "one away from mastery" scenarios.
    """
    correct = correct or ["B"]
    image_filenames = image_filenames or []
    choices = [{"label": L, "text": f"choice {L}"} for L in ("A", "B", "C", "D")]
    await db.execute(
        """INSERT INTO questions
           (id, pool, topic, prompt_en, prompt_th, choices_json,
            correct_labels, explanation, source_table,
            image_filenames, needs_review)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (id, pool, 1, f"prompt #{id}", f"prompt-th #{id}",
         json.dumps(choices), json.dumps(correct), explanation, id,
         json.dumps(image_filenames), needs_review),
    )
    if streak is not None:
        # Mirror the production invariant: any row in question_progress was
        # touched at least once, so last_seen_at + last_answer_at are set.
        # Otherwise the wrong-queue counter (which filters on
        # last_seen_at IS NOT NULL) would never see fixture rows.
        await db.execute(
            """INSERT INTO question_progress
                 (question_id, correct_streak, last_seen_at, last_answer_at)
               VALUES (?, ?, '2026-05-20T00:00:00Z', '2026-05-20T00:00:00Z')""",
            (id, streak),
        )
    await db.commit()


# ───────────────────────── require_session ─────────────────────────

@pytest.mark.asyncio
async def test_require_session_returns_404_envelope_when_missing(tmp_db):
    row, err = await svc.require_session(9999)
    assert row is None
    assert err is not None
    body, _headers, status = err
    assert status == 404
    assert body["code"] == "SESSION_NOT_FOUND"


# ───────────────────────── start_session ─────────────────────────

@pytest.mark.asyncio
async def test_start_session_with_batch_size(tmp_db):
    for q_id in range(1, 11):
        await _seed(tmp_db, id=q_id)
    sid, picked_n = await svc.start_session(25)
    assert isinstance(sid, int) and sid > 0
    assert picked_n == 10  # only 10 candidates exist
    async with tmp_db.execute(
        "SELECT batch_size, best_streak, total_seen FROM quiz_sessions WHERE id=?",
        (sid,),
    ) as cur:
        row = await cur.fetchone()
    assert row["batch_size"] == 25
    assert row["best_streak"] == 0
    assert row["total_seen"] == 0


@pytest.mark.asyncio
async def test_start_session_caps_picked_n_to_candidates(tmp_db):
    for q_id in range(1, 21):
        await _seed(tmp_db, id=q_id)
    _, picked_n = await svc.start_session(100)
    assert picked_n == 20


@pytest.mark.asyncio
async def test_start_session_endless_returns_all_candidates(tmp_db):
    for q_id in range(1, 6):
        await _seed(tmp_db, id=q_id)
    sid, picked_n = await svc.start_session("ENDLESS")
    assert picked_n == 5
    async with tmp_db.execute(
        "SELECT batch_size FROM quiz_sessions WHERE id=?", (sid,)
    ) as cur:
        # ENDLESS → batch_size column stays NULL
        assert (await cur.fetchone())["batch_size"] is None


@pytest.mark.asyncio
async def test_start_session_excludes_mastered_from_candidate_count(tmp_db):
    await _seed(tmp_db, id=1, streak=2)  # mastered
    await _seed(tmp_db, id=2, streak=1)
    await _seed(tmp_db, id=3)
    _, picked_n = await svc.start_session("ENDLESS")
    assert picked_n == 2   # only id=2 and id=3 are candidates


@pytest.mark.asyncio
async def test_start_session_rejects_invalid_batch(tmp_db):
    with pytest.raises(ValueError):
        await svc.start_session(37)
    with pytest.raises(ValueError):
        await svc.start_session("infinity")


# ───────────────────────── next_question ─────────────────────────

@pytest.mark.asyncio
async def test_next_question_excludes_mastered(tmp_db):
    await _seed(tmp_db, id=1, streak=2)   # mastered
    await _seed(tmp_db, id=2, streak=1)
    sid, _ = await svc.start_session("ENDLESS")
    q = await svc.next_question(sid)
    assert q is not None
    assert q["question_id"] == 2


@pytest.mark.asyncio
async def test_next_question_does_not_leak_correct_or_explanation(tmp_db):
    await _seed(tmp_db, id=1, explanation="secret")
    sid, _ = await svc.start_session("ENDLESS")
    q = await svc.next_question(sid)
    assert q is not None
    assert "correct_labels" not in q
    assert "explanation" not in q
    assert "current_streak" in q
    assert "position" in q
    assert q["multi"] is False
    assert q["image_urls"] == []


@pytest.mark.asyncio
async def test_next_question_returns_exhausted_when_batch_cap_reached(tmp_db):
    for q_id in range(1, 6):
        await _seed(tmp_db, id=q_id)
    sid, _ = await svc.start_session(25)
    # Force batch_size = 2 for a tighter test
    await tmp_db.execute("UPDATE quiz_sessions SET batch_size=2 WHERE id=?", (sid,))
    await tmp_db.commit()
    q1 = await svc.next_question(sid)
    await svc.submit_answer(sid, q1["question_id"], ["X"])  # wrong
    q2 = await svc.next_question(sid)
    await svc.submit_answer(sid, q2["question_id"], ["X"])  # wrong
    q3 = await svc.next_question(sid)
    assert q3 == {"exhausted": True}


@pytest.mark.asyncio
async def test_next_question_returns_exhausted_when_no_candidates(tmp_db):
    sid, _ = await svc.start_session("ENDLESS")  # zero candidates → picked_n=0
    assert await svc.next_question(sid) == {"exhausted": True}


# ───────────────────────── submit_answer ─────────────────────────

@pytest.mark.asyncio
async def test_submit_answer_returns_correct_for_exact_match(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"], explanation="because B")
    sid, _ = await svc.start_session("ENDLESS")
    result = await svc.submit_answer(sid, 1, ["B"])
    assert result == {
        "is_correct":     True,
        "correct_labels": ["B"],
        "explanation":    "because B",
    }


@pytest.mark.asyncio
async def test_submit_answer_handles_multi_answer_order_insensitive(tmp_db):
    await _seed(tmp_db, id=1, correct=["A", "C"])
    sid, _ = await svc.start_session("ENDLESS")
    assert (await svc.submit_answer(sid, 1, ["C", "A"]))["is_correct"] is True


@pytest.mark.asyncio
async def test_submit_answer_returns_wrong_for_partial_match(tmp_db):
    await _seed(tmp_db, id=1, correct=["A", "B"])
    sid, _ = await svc.start_session("ENDLESS")
    assert (await svc.submit_answer(sid, 1, ["A"]))["is_correct"] is False


@pytest.mark.asyncio
async def test_submit_answer_updates_session_totals(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"])
    await _seed(tmp_db, id=2, correct=["A"])
    sid, _ = await svc.start_session("ENDLESS")
    await svc.submit_answer(sid, 1, ["B"])    # correct
    await svc.submit_answer(sid, 2, ["B"])    # wrong
    summary = await svc.get_summary(sid)
    assert summary["total_seen"] == 2
    assert summary["total_correct"] == 1
    assert summary["accuracy"] == 50.0


@pytest.mark.asyncio
async def test_submit_answer_returns_none_for_missing_question(tmp_db):
    sid, _ = await svc.start_session("ENDLESS")
    assert await svc.submit_answer(sid, 9999, ["A"]) is None


@pytest.mark.asyncio
async def test_submit_answer_rejects_double_submit_in_same_session(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"])
    sid, _ = await svc.start_session("ENDLESS")
    first = await svc.submit_answer(sid, 1, ["B"])
    assert first is not None and first["is_correct"]
    second = await svc.submit_answer(sid, 1, ["B"])
    assert second is svc.ALREADY_ANSWERED
    summary = await svc.get_summary(sid)
    assert summary["total_seen"] == 1
    assert summary["total_correct"] == 1


@pytest.mark.asyncio
async def test_submit_answer_normalises_case_before_comparing(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"])
    sid, _ = await svc.start_session("ENDLESS")
    result = await svc.submit_answer(sid, 1, ["b"])
    assert result is not None and result["is_correct"] is True


@pytest.mark.asyncio
async def test_submit_answer_bumps_streak_on_correct(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"])
    sid, _ = await svc.start_session("ENDLESS")
    await svc.submit_answer(sid, 1, ["B"])
    async with tmp_db.execute(
        "SELECT correct_streak FROM question_progress WHERE question_id=1"
    ) as cur:
        assert (await cur.fetchone())["correct_streak"] == 1


@pytest.mark.asyncio
async def test_submit_answer_two_correct_in_a_row_masters_question(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"], streak=1)  # one away from mastery
    sid, _ = await svc.start_session("ENDLESS")
    await svc.submit_answer(sid, 1, ["B"])  # correct → streak becomes 2
    async with tmp_db.execute(
        "SELECT correct_streak FROM question_progress WHERE question_id=1"
    ) as cur:
        assert (await cur.fetchone())["correct_streak"] == 2
    # next session shouldn't see this question
    sid2, _ = await svc.start_session("ENDLESS")
    assert await svc.next_question(sid2) == {"exhausted": True}


@pytest.mark.asyncio
async def test_submit_answer_resets_streak_on_wrong(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"], streak=1)
    sid, _ = await svc.start_session("ENDLESS")
    await svc.submit_answer(sid, 1, ["A"])  # wrong
    async with tmp_db.execute(
        "SELECT correct_streak FROM question_progress WHERE question_id=1"
    ) as cur:
        assert (await cur.fetchone())["correct_streak"] == 0


@pytest.mark.asyncio
async def test_submit_answer_updates_session_best_streak(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"])
    await _seed(tmp_db, id=2, correct=["B"])
    await _seed(tmp_db, id=3, correct=["B"])
    sid, _ = await svc.start_session("ENDLESS")
    await svc.submit_answer(sid, 1, ["B"])  # session_streak now 1
    await svc.submit_answer(sid, 2, ["B"])  # session_streak now 2
    await svc.submit_answer(sid, 3, ["A"])  # session_streak resets
    async with tmp_db.execute(
        "SELECT best_streak FROM quiz_sessions WHERE id=?", (sid,)
    ) as cur:
        assert (await cur.fetchone())["best_streak"] == 2


# ───────────────────────── dont_know ─────────────────────────

@pytest.mark.asyncio
async def test_dont_know_returns_reveal_and_resets_streak(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"], explanation="because B", streak=1)
    sid, _ = await svc.start_session("ENDLESS")
    result = await svc.dont_know(sid, 1)
    assert result == {
        "is_correct":     False,
        "correct_labels": ["B"],
        "explanation":    "because B",
    }
    async with tmp_db.execute(
        "SELECT correct_streak FROM question_progress WHERE question_id=1"
    ) as cur:
        assert (await cur.fetchone())["correct_streak"] == 0


@pytest.mark.asyncio
async def test_dont_know_increments_total_seen_only(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"])
    sid, _ = await svc.start_session("ENDLESS")
    await svc.dont_know(sid, 1)
    async with tmp_db.execute(
        "SELECT total_seen, total_correct FROM quiz_sessions WHERE id=?", (sid,)
    ) as cur:
        row = await cur.fetchone()
    assert row["total_seen"] == 1
    assert row["total_correct"] == 0


@pytest.mark.asyncio
async def test_dont_know_returns_none_for_missing_question(tmp_db):
    sid, _ = await svc.start_session("ENDLESS")
    assert await svc.dont_know(sid, 9999) is None


# ───────────────────────── reset_progress ─────────────────────────

@pytest.mark.asyncio
async def test_reset_progress_clears_question_progress_rows(tmp_db):
    await _seed(tmp_db, id=1, streak=2)
    await _seed(tmp_db, id=2, streak=1)
    cleared = await svc.reset_progress()
    assert cleared == 2
    async with tmp_db.execute("SELECT COUNT(*) FROM question_progress") as cur:
        assert (await cur.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_reset_progress_does_not_touch_quiz_sessions(tmp_db):
    sid, _ = await svc.start_session("ENDLESS")
    await svc.reset_progress()
    async with tmp_db.execute("SELECT COUNT(*) FROM quiz_sessions") as cur:
        assert (await cur.fetchone())[0] == 1


# ───────────────────────── get_dashboard ─────────────────────────

@pytest.mark.asyncio
async def test_get_dashboard_empty_state(tmp_db):
    data = await svc.get_dashboard()
    assert data["mastered_count"]    == 0
    assert data["quizable_total"]    == 0
    assert data["parsed_total"]      == 0
    assert data["flagged_count"]     == 0
    assert data["wrong_queue_count"] == 0
    assert data["recent_sessions"]   == []
    assert data["latest_session"]    is None


@pytest.mark.asyncio
async def test_get_dashboard_counts_after_some_progress(tmp_db):
    await _seed(tmp_db, id=1, streak=2)   # mastered
    await _seed(tmp_db, id=2, streak=1)   # in wrong-queue
    await _seed(tmp_db, id=3)             # never touched, not in queue
    await _seed(tmp_db, id=4, needs_review=1)
    data = await svc.get_dashboard()
    assert data["mastered_count"]    == 1
    assert data["quizable_total"]    == 3
    assert data["parsed_total"]      == 4
    assert data["flagged_count"]     == 1
    assert data["wrong_queue_count"] == 1


@pytest.mark.asyncio
async def test_get_dashboard_excludes_v1_sessions_without_batch_size(tmp_db):
    # v1-style session row (no batch_size)
    await tmp_db.execute(
        "INSERT INTO quiz_sessions (pool, started_at) VALUES ('A', '2026-01-01T00:00:00Z')"
    )
    await tmp_db.commit()
    data = await svc.get_dashboard()
    assert data["recent_sessions"] == []
    assert data["latest_session"] is None


@pytest.mark.asyncio
async def test_get_dashboard_returns_recent_sessions_newest_first(tmp_db):
    for _ in range(7):  # 7 sessions to test we cap at 5
        sid, _ = await svc.start_session(25)
        await svc.finish_session(sid)
    data = await svc.get_dashboard()
    assert len(data["recent_sessions"]) == 5
    assert data["latest_session"] is not None
    ids = [s["id"] for s in data["recent_sessions"]]
    assert ids == sorted(ids, reverse=True)


# ───────────────────────── get_summary ─────────────────────────

@pytest.mark.asyncio
async def test_get_summary_includes_wrong_answers_list(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"], explanation="explain")
    await _seed(tmp_db, id=2, correct=["A"], explanation="other")
    sid, _ = await svc.start_session("ENDLESS")
    await svc.submit_answer(sid, 1, ["A"])  # wrong
    await svc.submit_answer(sid, 2, ["A"])  # correct
    summary = await svc.get_summary(sid)
    wrong = summary["wrong_answers"]
    assert len(wrong) == 1
    assert wrong[0]["question_id"]     == 1
    assert wrong[0]["correct_labels"]  == ["B"]
    assert wrong[0]["selected_labels"] == ["A"]
    assert wrong[0]["explanation"]     == "explain"
    assert wrong[0]["prompt_en"].startswith("prompt #1")


@pytest.mark.asyncio
async def test_get_summary_returns_none_for_unknown(tmp_db):
    assert await svc.get_summary(9999) is None


# ───────────────────────── finish_session ─────────────────────────

@pytest.mark.asyncio
async def test_finish_session_sets_ended_at_and_is_idempotent(tmp_db):
    sid, _ = await svc.start_session("ENDLESS")
    first = await svc.finish_session(sid)
    assert first["ended_at"] is not None
    second = await svc.finish_session(sid)
    assert first["ended_at"] == second["ended_at"]


@pytest.mark.asyncio
async def test_finish_session_returns_none_for_unknown_session(tmp_db):
    assert await svc.finish_session(9999) is None


@pytest.mark.asyncio
async def test_finish_session_clears_session_streak_cache(tmp_db):
    await _seed(tmp_db, id=1, correct=["B"])
    sid, _ = await svc.start_session("ENDLESS")
    await svc.submit_answer(sid, 1, ["B"])
    assert svc._session_streak.get(sid) == 1
    await svc.finish_session(sid)
    assert sid not in svc._session_streak
