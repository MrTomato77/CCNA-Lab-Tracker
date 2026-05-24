"""Tests for app.py's recursive static-file preload and HTML partial stitching."""

from pathlib import Path

import pytest


def test_load_static_recursive_finds_nested_css(tmp_path, monkeypatch):
    """Recursive walk picks up `nested/file.css` under public/."""
    from app import _load_static_recursive

    pub = tmp_path / "public"
    (pub / "core").mkdir(parents=True)
    (pub / "nav").mkdir()
    (pub / "core" / "tokens.css").write_text(":root { --x: 1; }", encoding="utf-8")
    (pub / "nav" / "nav.css").write_text(".nav { display: flex; }", encoding="utf-8")
    (pub / "nav" / "nav.js").write_text("// nav js", encoding="utf-8")
    (pub / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    static = _load_static_recursive(pub)
    assert static["core/tokens.css"] == ":root { --x: 1; }"
    assert static["nav/nav.css"] == ".nav { display: flex; }"
    assert static["nav/nav.js"] == "// nav js"
    assert "index.html" in static


def test_build_index_substitutes_include_markers():
    """`<!--INCLUDE:nav/nav.html-->` in shell is replaced with the partial's contents."""
    from app import _build_index

    static = {
        "index.html": "<body><!--INCLUDE:nav/nav.html--><main></main></body>",
        "nav/nav.html": "<nav>NAV</nav>",
    }
    assert _build_index(static) == "<body><nav>NAV</nav><main></main></body>"


def test_build_index_handles_multiple_markers():
    from app import _build_index
    static = {
        "index.html": "<!--INCLUDE:a.html-->X<!--INCLUDE:b.html-->",
        "a.html": "AA",
        "b.html": "BB",
    }
    assert _build_index(static) == "AAXBB"


def test_build_index_raises_on_unknown_marker():
    from app import _build_index
    static = {"index.html": "<!--INCLUDE:missing.html-->"}
    with pytest.raises(KeyError, match="missing.html"):
        _build_index(static)


def test_build_index_does_not_recurse():
    """A partial that itself contains an INCLUDE marker is NOT re-expanded."""
    from app import _build_index
    static = {
        "index.html": "<!--INCLUDE:a.html-->",
        "a.html": "<!--INCLUDE:b.html-->",
        "b.html": "DEEP",
    }
    assert _build_index(static) == "<!--INCLUDE:b.html-->"


def test_serve_static_rejects_path_traversal(monkeypatch):
    """`..` segments in a static URL must 404, not escape PUBLIC/."""
    from app import _resolve_static_path

    assert _resolve_static_path("nav/nav.css") == "nav/nav.css"
    assert _resolve_static_path("core/tokens.css") == "core/tokens.css"
    assert _resolve_static_path("../etc/passwd") is None
    assert _resolve_static_path("nav/../../app.py") is None
    assert _resolve_static_path("/absolute/path") is None
    assert _resolve_static_path("nav\\nav.css") is None
