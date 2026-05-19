"""Boundary validation tests for the quiz Pydantic schemas."""
import pytest
from pydantic import ValidationError

from models.quiz_schemas import AnswerSubmit, SessionStart


def test_session_start_accepts_letters_and_all():
    for pool in ("A", "B", "C", "D", "ALL"):
        assert SessionStart.model_validate({"pool": pool}).pool == pool


def test_session_start_rejects_unknown_pool():
    with pytest.raises(ValidationError):
        SessionStart.model_validate({"pool": "X"})
    with pytest.raises(ValidationError):
        SessionStart.model_validate({"pool": ""})


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
