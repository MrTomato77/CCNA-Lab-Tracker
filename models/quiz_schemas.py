"""Pydantic schemas for the quiz API."""
from typing import Literal

from pydantic import BaseModel, field_validator


_BATCH_INTS = {25, 50, 75, 100}


class SessionStart(BaseModel):
    batch_size: int | Literal["ENDLESS"]

    @field_validator("batch_size")
    @classmethod
    def valid_batch(cls, v):
        if v == "ENDLESS":
            return v
        if not isinstance(v, int) or v not in _BATCH_INTS:
            raise ValueError("batch_size must be 25, 50, 75, 100, or 'ENDLESS'")
        return v


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


class DontKnowSubmit(BaseModel):
    question_id: int

    @field_validator("question_id")
    @classmethod
    def positive_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("question_id must be positive")
        return v
