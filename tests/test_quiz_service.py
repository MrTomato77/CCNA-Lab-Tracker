"""Tests for services/quiz_service.py."""
from __future__ import annotations

import json

import pytest

from services import quiz_service as svc


async def _seed(db, *, id: int, pool: str = "A", correct: list[str] | None = None,
                explanation: str = "Reason.", needs_review: int = 0,
                image_filenames: list[str] | None = None) -> None:
    """Insert a quizable question with safe defaults."""
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
    await db.commit()


@pytest.mark.asyncio
async def test_list_pools_returns_zero_counts_when_empty(tmp_db):
    pools = await svc.list_pools()
    ids = [p["id"] for p in pools]
    assert ids == ["A", "B", "C", "D", "ALL"]
    assert all(p["question_count"] == 0 for p in pools)


@pytest.mark.asyncio
async def test_list_pools_counts_only_quizable_rows(tmp_db):
    await _seed(tmp_db, id=1, pool="A")
    await _seed(tmp_db, id=2, pool="A", needs_review=1)  # flagged → excluded
    await _seed(tmp_db, id=3, pool="B")
    pools = {p["id"]: p["question_count"] for p in await svc.list_pools()}
    assert pools == {"A": 1, "B": 1, "C": 0, "D": 0, "ALL": 2}


@pytest.mark.asyncio
async def test_start_session_creates_row_and_returns_id(tmp_db):
    sid = await svc.start_session("B")
    assert isinstance(sid, int) and sid > 0
    async with tmp_db.execute(
        "SELECT pool, total_seen, total_correct, started_at, ended_at "
        "FROM quiz_sessions WHERE id = ?", (sid,)
    ) as cur:
        row = await cur.fetchone()
    assert row["pool"] == "B"
    assert row["total_seen"] == 0
    assert row["total_correct"] == 0
    assert row["ended_at"] is None
    assert row["started_at"].endswith("Z")


@pytest.mark.asyncio
async def test_require_session_returns_404_envelope_when_missing(tmp_db):
    row, err = await svc.require_session(9999)
    assert row is None
    assert err is not None
    body, _headers, status = err
    assert status == 404
    assert body["code"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_next_question_filters_by_pool_and_does_not_leak_answer(tmp_db):
    await _seed(tmp_db, id=1, pool="A", correct=["B"])
    await _seed(tmp_db, id=2, pool="B", correct=["A"])
    sid = await svc.start_session("A")
    payload = await svc.next_question(sid)
    assert payload is not None
    assert payload["question_id"] == 1
    assert "correct_labels" not in payload
    assert "explanation" not in payload
    assert payload["multi"] is False
    assert payload["image_urls"] == []


@pytest.mark.asyncio
async def test_next_question_skips_already_answered_in_session(tmp_db):
    await _seed(tmp_db, id=1, pool="A")
    sid = await svc.start_session("A")
    first = await svc.next_question(sid)
    assert first is not None
    await svc.submit_answer(sid, first["question_id"], ["B"])
    assert await svc.next_question(sid) is None


@pytest.mark.asyncio
async def test_next_question_all_pool_includes_every_pool(tmp_db):
    await _seed(tmp_db, id=1, pool="A")
    await _seed(tmp_db, id=2, pool="D")
    sid = await svc.start_session("ALL")
    seen: set[int] = set()
    for _ in range(2):
        q = await svc.next_question(sid)
        assert q is not None
        seen.add(q["question_id"])
        await svc.submit_answer(sid, q["question_id"], ["B"])
    assert seen == {1, 2}


@pytest.mark.asyncio
async def test_submit_answer_returns_correct_for_exact_match(tmp_db):
    await _seed(tmp_db, id=1, pool="A", correct=["B"], explanation="because B")
    sid = await svc.start_session("A")
    result = await svc.submit_answer(sid, 1, ["B"])
    assert result == {
        "is_correct": True,
        "correct_labels": ["B"],
        "explanation": "because B",
    }


@pytest.mark.asyncio
async def test_submit_answer_handles_multi_answer_order_insensitive(tmp_db):
    await _seed(tmp_db, id=1, pool="A", correct=["A", "C"])
    sid = await svc.start_session("A")
    assert (await svc.submit_answer(sid, 1, ["C", "A"]))["is_correct"] is True


@pytest.mark.asyncio
async def test_submit_answer_returns_wrong_for_partial_match(tmp_db):
    await _seed(tmp_db, id=1, pool="A", correct=["A", "B"])
    sid = await svc.start_session("A")
    assert (await svc.submit_answer(sid, 1, ["A"]))["is_correct"] is False


@pytest.mark.asyncio
async def test_submit_answer_updates_session_totals(tmp_db):
    await _seed(tmp_db, id=1, pool="A", correct=["B"])
    await _seed(tmp_db, id=2, pool="A", correct=["A"])
    sid = await svc.start_session("A")
    await svc.submit_answer(sid, 1, ["B"])    # correct
    await svc.submit_answer(sid, 2, ["B"])    # wrong
    summary = await svc.get_summary(sid)
    assert summary["total_seen"] == 2
    assert summary["total_correct"] == 1
    assert summary["accuracy"] == 50.0


@pytest.mark.asyncio
async def test_submit_answer_returns_none_for_missing_question(tmp_db):
    sid = await svc.start_session("A")
    assert await svc.submit_answer(sid, 9999, ["A"]) is None


@pytest.mark.asyncio
async def test_submit_answer_rejects_double_submit_in_same_session(tmp_db):
    await _seed(tmp_db, id=1, pool="A", correct=["B"])
    sid = await svc.start_session("A")
    first = await svc.submit_answer(sid, 1, ["B"])
    assert first is not None and first["is_correct"]
    # Second submission for the same (session, question) returns the
    # ALREADY_ANSWERED sentinel so the router can distinguish it from a
    # genuinely missing question and emit a 409 instead of a 404.
    second = await svc.submit_answer(sid, 1, ["B"])
    assert second is svc.ALREADY_ANSWERED
    summary = await svc.get_summary(sid)
    assert summary["total_seen"] == 1
    assert summary["total_correct"] == 1


@pytest.mark.asyncio
async def test_submit_answer_normalises_case_before_comparing(tmp_db):
    """The Pydantic validator uppercases incoming labels, but the service
    layer should not silently miscompare when called directly."""
    await _seed(tmp_db, id=1, pool="A", correct=["B"])
    sid = await svc.start_session("A")
    result = await svc.submit_answer(sid, 1, ["b"])
    assert result is not None and result["is_correct"] is True


@pytest.mark.asyncio
async def test_next_question_returns_none_when_pool_has_only_flagged_rows(tmp_db):
    await _seed(tmp_db, id=1, pool="A", needs_review=1)
    sid = await svc.start_session("A")
    assert await svc.next_question(sid) is None


@pytest.mark.asyncio
async def test_finish_session_returns_none_for_unknown_session(tmp_db):
    assert await svc.finish_session(9999) is None


@pytest.mark.asyncio
async def test_start_session_rejects_invalid_pool(tmp_db):
    with pytest.raises(ValueError):
        await svc.start_session("X")


@pytest.mark.asyncio
async def test_finish_session_sets_ended_at_and_is_idempotent(tmp_db):
    sid = await svc.start_session("A")
    first = await svc.finish_session(sid)
    assert first["ended_at"] is not None
    second = await svc.finish_session(sid)
    assert first["ended_at"] == second["ended_at"]


@pytest.mark.asyncio
async def test_get_summary_returns_none_for_unknown(tmp_db):
    assert await svc.get_summary(9999) is None


