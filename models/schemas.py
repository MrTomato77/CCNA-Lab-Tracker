from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, field_validator
from core.constants import Status

class StatusUpdate(BaseModel):
    status: Status

class TimerSave(BaseModel):
    started_at: datetime
    duration: int

    @field_validator("duration")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("duration must be >= 0")
        return v

class FolderScan(BaseModel):
    folder_path: str

    @field_validator("folder_path")
    @classmethod
    def safe_path(cls, v: str) -> str:
        folder_path = v.strip()
        if not folder_path:
            raise ValueError("folder_path is required")
        if ".." in Path(folder_path).parts:
            raise ValueError("path traversal not allowed")
        if len(folder_path) > 4096:
            raise ValueError("folder_path too long")
        return folder_path
