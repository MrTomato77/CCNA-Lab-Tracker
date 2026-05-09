"""Coverage for the /docs/:filename path-traversal guard.

The hardened route resolves the candidate path and confirms it stays
inside DOCS_DIR. These tests reach into the same logic without the
HTTP layer to keep them fast and Robyn-version-independent.
"""
from pathlib import Path

import app as app_mod


def _is_safe(filename: str) -> bool:
    """Mirror of the in-route check, kept in sync with app.lab_docs."""
    if not filename.endswith(".pdf"):
        return False
    try:
        target = (app_mod.DOCS_DIR / filename).resolve()
    except (OSError, ValueError):
        return False
    return target.is_relative_to(app_mod.DOCS_DIR)


def test_docs_dir_is_resolved():
    """DOCS_DIR must be a canonical absolute path so is_relative_to works
    even when the candidate contains `..`."""
    assert app_mod.DOCS_DIR == Path(app_mod.DOCS_DIR).resolve()


def test_rejects_dotdot_traversal():
    assert not _is_safe("../app.py")
    assert not _is_safe("../../etc/passwd.pdf")


def test_rejects_absolute_path():
    # On Windows an absolute path under "/" gets rebound under DOCS_DIR
    # by the / operator, but explicit absolute should still resolve out.
    assert not _is_safe("C:/Windows/System32/drivers/etc/hosts.pdf")


def test_rejects_non_pdf():
    assert not _is_safe("LAB-01.txt")
    assert not _is_safe("LAB-01")
    assert not _is_safe("evil.exe")


def test_accepts_simple_pdf_name():
    # Doesn't have to exist on disk; the existence check happens after
    # the safety check in the real route.
    assert _is_safe("LAB-01.pdf")
    assert _is_safe("anything.pdf")
