"""Pydantic schemas for the quiz API.

Mirrors the boundary-validation style of ``models/schemas.py``. Only the
inbound request payloads are typed here — outbound shapes are plain dicts
built by the service layer.
"""
from __future__ import annotations

from pydantic import BaseModel, field_validator

from core.exam_pools import SessionPool


class SessionStart(BaseModel):
    pool: SessionPool


class AnswerSubmit(BaseModel):
    question_id: int
    selected_labels: list[str]

    @field_validator("question_id")
    @classmethod
    def positive_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("question_id must be positive")
        return v

    @field_validator("selected_labels")
    @classmethod
    def labels_are_clean(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("selected_labels must not be empty")
        if len(v) > 6:
            raise ValueError("too many labels")
        normalized: list[str] = []
        for label in v:
            if (
                not isinstance(label, str)
                or len(label) != 1
                or not ("A" <= label.upper() <= "Z")
            ):
                raise ValueError("each label must be a single A-Z letter")
            normalized.append(label.upper())
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate labels not allowed")
        return normalized
