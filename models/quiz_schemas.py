"""Pydantic schemas for the quiz API."""
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


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
    # mcq answers use selected_labels; drag_drop answers use matches (item→bucket).
    # Exactly one must be provided.
    question_id: int
    selected_labels: list[str] = []
    matches: dict[str, str] | None = None

    @field_validator("question_id")
    @classmethod
    def positive_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("question_id must be positive")
        return v

    @field_validator("selected_labels")
    @classmethod
    def labels_are_clean(cls, v: list[str]) -> list[str]:
        # May be empty for drag_drop (validated in the model check below).
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

    @model_validator(mode="after")
    def exactly_one_mode(self) -> "AnswerSubmit":
        has_labels = bool(self.selected_labels)
        has_matches = bool(self.matches)
        if has_labels == has_matches:
            raise ValueError("provide either selected_labels (mcq) or matches (drag_drop)")
        if self.matches is not None:
            if len(self.matches) > 12:
                raise ValueError("too many matches")
            for left, bucket in self.matches.items():
                if not isinstance(left, str) or not isinstance(bucket, str):
                    raise ValueError("matches must be string→string")
                if not left or not bucket:
                    raise ValueError("match keys/values must be non-empty")
                if len(left) > 400 or len(bucket) > 200:
                    raise ValueError("match text too long")
        return self


class DontKnowSubmit(BaseModel):
    question_id: int

    @field_validator("question_id")
    @classmethod
    def positive_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("question_id must be positive")
        return v
