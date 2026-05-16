"""Boundary validation for API request schemas."""
from datetime import datetime

import pytest
from pydantic import ValidationError

from models.schemas import FolderScan, TimerSave


def test_timer_save_requires_iso_datetime():
    data = TimerSave.model_validate({"started_at": "2026-05-09T10:00:00", "duration": 30})
    assert isinstance(data.started_at, datetime)

    with pytest.raises(ValidationError):
        TimerSave.model_validate({"started_at": "yesterday", "duration": 30})


def test_folder_scan_rejects_traversal_and_blank():
    assert FolderScan.model_validate({"folder_path": "C:/Users/MrTomato/Downloads"}).folder_path

    for folder_path in ("", "../etc/passwd", "safe/../unsafe"):
        with pytest.raises(ValidationError):
            FolderScan.model_validate({"folder_path": folder_path})
