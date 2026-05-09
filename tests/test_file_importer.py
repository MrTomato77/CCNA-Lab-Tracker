"""Coverage for `extract_lab_id` boundary behaviour.

The lab-ID regex used to accept LAB-00..LAB-99, which let junk filenames
like "LAB-99.pka" import successfully and orphan rows in the labs table.
A bounds check (1..51) was added; these tests pin it down so a future
edit to the regex can't quietly regress it.
"""
import pytest

from services.file_importer import extract_lab_id, _MAX_LAB_NUMBER


@pytest.mark.parametrize("filename", [
    "LAB-99.pka",
    "LAB-00.pka",
    "LAB-52.pka",
    "lab-99.pka",
    "no number here.pka",
    "LAB-AB.pka",
])
def test_rejects_out_of_range_or_garbage(filename):
    assert extract_lab_id(filename) is None


@pytest.mark.parametrize("filename,expected", [
    ("LAB-01.pka",                                  "LAB-01"),
    ("LAB-51.pka",                                  "LAB-51"),
    ("LAB-7.pka",                                   "LAB-07"),
    ("lab-12 something.pka",                        "LAB-12"),
    ("LAB-21-IPv4 Static and Default Route.pka",    "LAB-21"),
    ("LAB 5 spaced.pka",                            "LAB-05"),
])
def test_accepts_in_range_with_padding(filename, expected):
    assert extract_lab_id(filename) == expected


def test_max_lab_number_constant_matches_seed():
    """If LAB_DEFINITIONS in database/seed.py grows past _MAX_LAB_NUMBER,
    the bounds check would silently reject valid imports. Catch the drift
    here so the constant gets bumped intentionally."""
    from database import seed
    seeded_max = max(int(lab[0].split("-")[1]) for lab in seed.LAB_DEFINITIONS)
    assert seeded_max <= _MAX_LAB_NUMBER, (
        f"seed.LAB_DEFINITIONS goes up to LAB-{seeded_max}, but "
        f"file_importer._MAX_LAB_NUMBER is {_MAX_LAB_NUMBER}. Bump it."
    )
