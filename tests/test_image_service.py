"""Tests for services/image_service.py."""
from __future__ import annotations

import pytest

from services import image_service


def test_safe_name_accepts_valid_pattern():
    assert image_service.is_safe_image_name("Q-0001-0.png")
    assert image_service.is_safe_image_name("Q-9999-3.jpg")


def test_safe_name_rejects_traversal_and_garbage():
    rejects = [
        "../../etc/passwd",
        "..\\windows\\system32.png",
        "Q-1-0.png",          # not 4 digits
        "Q-0001-0.exe",       # wrong extension
        "Q-0001-0",           # no extension
        "evil.png",
        "Q-0001-0.png/../x",
        "",
    ]
    for name in rejects:
        assert not image_service.is_safe_image_name(name), name


def test_content_type_for_known_and_unknown():
    assert image_service.content_type_for("Q-0001-0.png")  == "image/png"
    assert image_service.content_type_for("Q-0001-0.jpg")  == "image/jpeg"
    assert image_service.content_type_for("Q-0001-0.webp") == "image/webp"
    assert image_service.content_type_for("Q-0001-0.xyz")  == "application/octet-stream"


def test_resolve_image_path_returns_none_for_unsafe_name(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service, "IMAGES_DIR", tmp_path.resolve())
    assert image_service.resolve_image_path("../escape.png") is None
    assert image_service.resolve_image_path("Q-0001-0.exe") is None


def test_resolve_image_path_returns_none_for_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service, "IMAGES_DIR", tmp_path.resolve())
    assert image_service.resolve_image_path("Q-0001-0.png") is None


def test_resolve_image_path_returns_path_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service, "IMAGES_DIR", tmp_path.resolve())
    (tmp_path / "Q-0042-0.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    p = image_service.resolve_image_path("Q-0042-0.png")
    assert p is not None
    assert p.name == "Q-0042-0.png"


@pytest.mark.asyncio
async def test_read_image_returns_bytes_and_content_type(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service, "IMAGES_DIR", tmp_path.resolve())
    payload = b"\x89PNG\r\n\x1a\nsample"
    (tmp_path / "Q-0007-1.png").write_bytes(payload)
    result = await image_service.read_image("Q-0007-1.png")
    assert result == (payload, "image/png")


@pytest.mark.asyncio
async def test_read_image_returns_none_for_unsafe(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service, "IMAGES_DIR", tmp_path.resolve())
    assert await image_service.read_image("../etc/passwd") is None
