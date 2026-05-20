"""Boundary validation tests for the quiz Pydantic schemas (v2)."""
import pytest
from pydantic import ValidationError

from models.quiz_schemas import AnswerSubmit, DontKnowSubmit, SessionStart


# ───────────────────────── SessionStart ─────────────────────────

def test_session_start_accepts_valid_batch_sizes():
    for v in (25, 50, 75, 100, "ENDLESS"):
        assert SessionStart.model_validate({"batch_size": v}).batch_size == v


def test_session_start_rejects_invalid_batch_sizes():
    for bad in (0, 13, 37, "infinity", [], None):
        with pytest.raises(ValidationError):
            SessionStart.model_validate({"batch_size": bad})


# ───────────────────────── AnswerSubmit ─────────────────────────

def test_answer_submit_uppercases_and_dedupes():
    out = AnswerSubmit.model_validate({"question_id": 1, "selected_labels": ["a", "B"]})
    assert out.selected_labels == ["A", "B"]


def test_answer_submit_rejects_empty_labels():
    with pytest.raises(ValidationError):
        AnswerSubmit.model_validate({"question_id": 1, "selected_labels": []})


def test_answer_submit_rejects_duplicate_labels():
    with pytest.raises(ValidationError):
        AnswerSubmit.model_validate({"question_id": 1, "selected_labels": ["A", "a"]})


def test_answer_submit_rejects_non_ascii_letter():
    """Cyrillic 'А' (U+0410) looks like ASCII 'A' but is not — must reject."""
    with pytest.raises(ValidationError):
        AnswerSubmit.model_validate({"question_id": 1, "selected_labels": ["А"]})


def test_answer_submit_rejects_multichar_label():
    with pytest.raises(ValidationError):
        AnswerSubmit.model_validate({"question_id": 1, "selected_labels": ["AB"]})


def test_answer_submit_rejects_excess_labels():
    with pytest.raises(ValidationError):
        AnswerSubmit.model_validate({
            "question_id": 1,
            "selected_labels": list("ABCDEFG"),  # 7 items, max is 6
        })


def test_answer_submit_rejects_non_positive_id():
    for bad in (0, -1):
        with pytest.raises(ValidationError):
            AnswerSubmit.model_validate({"question_id": bad, "selected_labels": ["A"]})


# ───────────────────────── DontKnowSubmit ─────────────────────────

def test_dont_know_submit_accepts_positive_id():
    assert DontKnowSubmit.model_validate({"question_id": 1}).question_id == 1


def test_dont_know_submit_requires_positive_question_id():
    for bad in (0, -1):
        with pytest.raises(ValidationError):
            DontKnowSubmit.model_validate({"question_id": bad})
