"""Tests for the DOCX question parser.

Pure-function tests run anywhere. Integration tests against the real
Cert Empire docx are skipped if the (gitignored) source file is absent.
"""
from __future__ import annotations

import pytest

from scripts.parse_questions import (
    SOURCE_DOCX,
    classify_table,
    extract_table_images,
    is_mostly_thai,
    parse_header_text,
)


# ---------- pure-function tests (no docx needed) ----------

def test_parse_header_text_extracts_id_topic_pool():
    text = "Question #42 Topic 3 - Exam Pool C"
    assert parse_header_text(text) == (42, 3, "C")


def test_parse_header_text_tolerates_extra_whitespace_and_split_lines():
    text = "Question #1\n   Topic 1 - Exam Pool A\n"
    assert parse_header_text(text) == (1, 1, "A")


def test_parse_header_text_returns_none_on_garbage():
    assert parse_header_text("Hello world") is None
    assert parse_header_text("") is None


def test_parse_header_text_rejects_unknown_topic_or_pool():
    assert parse_header_text("Question #1 Topic 9 - Exam Pool A") is None
    assert parse_header_text("Question #1 Topic 1 - Exam Pool Z") is None


def test_is_mostly_thai_detects_thai_dominant():
    assert is_mostly_thai("คำสั่งใด ที่ป้อนบนสวิตช์") is True


def test_is_mostly_thai_rejects_english_dominant():
    assert is_mostly_thai("Which command entered on a switch") is False


def test_is_mostly_thai_on_empty_string():
    assert is_mostly_thai("") is False


# ---------- integration tests (need real docx) ----------

needs_docx = pytest.mark.skipif(
    not SOURCE_DOCX.exists(),
    reason=f"source docx not available at {SOURCE_DOCX}",
)


@pytest.fixture(scope="module")
def document():
    from docx import Document
    return Document(str(SOURCE_DOCX))


@needs_docx
def test_classify_table_extracts_q1_ground_truth(document):
    """Q#1 has 4 choices A-D; the correct answer is D (forward-time 20),
    marked by the green run shading in the source doc."""
    q = classify_table(document.tables[0], source_index=0)

    assert q is not None
    assert q.id == 1
    assert q.pool == "A"
    assert q.topic == 1
    assert q.prompt_en.startswith("Which command entered on a switch")
    assert q.prompt_th and "คำสั่ง" in q.prompt_th
    assert [c["label"] for c in q.choices] == ["A", "B", "C", "D"]
    assert q.correct_labels == ["D"]
    assert q.needs_review is False
    assert q.image_filenames == []  # populated only by extract_table_images
    assert q.explanation and "Forward Time" in q.explanation


@needs_docx
def test_classify_table_handles_multi_answer(document):
    """At least one of Q23/Q30 from earlier scans should be a multi-answer."""
    multi_seen = False
    for i in range(60):  # search the first 60 questions
        q = classify_table(document.tables[i], source_index=i)
        if q is not None and len(q.correct_labels) >= 2:
            multi_seen = True
            break
    assert multi_seen, "expected to find at least one multi-answer question"


@needs_docx
def test_extract_table_images_writes_files(document, tmp_path):
    """Q2 is known to embed at least one image (per the probe scan)."""
    table = document.tables[1]  # 0-indexed → table 1 == Q#2
    files = extract_table_images(document, table, tmp_path, qid=2)
    assert files, "expected Q#2 to embed at least one image"
    for fname in files:
        path = tmp_path / fname
        assert path.exists() and path.stat().st_size > 0
        assert fname.startswith("Q-0002-")
