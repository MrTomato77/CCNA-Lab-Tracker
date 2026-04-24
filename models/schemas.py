from pydantic import BaseModel, field_validator
from typing import Literal

class StatusUpdate(BaseModel):
    status: Literal["not_started", "in_progress", "done"]

class TimerSave(BaseModel):
    started_at: str
    duration: int

    @field_validator("duration")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("duration must be >= 0")
        return v

class FolderScan(BaseModel):
    folder_path: str
