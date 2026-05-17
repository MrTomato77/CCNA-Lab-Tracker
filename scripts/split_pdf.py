"""One-time script: split the master CCNA Labs PDF into 51 per-lab files.

Run from the project root:
    python scripts/split_pdf.py

Re-running is safe: existing per-lab files are skipped unless --force is passed.
"""

import argparse
import logging
import re
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.constants import MAX_LAB_NUMBER  # noqa: E402

SOURCE_PDF = ROOT / "docs" / "CCNA-Network-Labs-Professional_2024_Edition_v3.1_Signed.pdf"
OUT_DIR = ROOT / "docs"

LAB_RE = re.compile(r"\bLAB[-\s]?(\d{1,2})\b", re.IGNORECASE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def labs_on_page(text: str) -> list[int]:
    """Return the sorted unique lab numbers mentioned on a page."""
    return sorted({int(m.group(1)) for m in LAB_RE.finditer(text or "")})


def find_section_starts(reader: PdfReader) -> dict[int, int]:
    """Map lab number → 0-indexed start page.

    Heuristic: a section starts on the first page mentioning exactly one lab id
    (TOC pages mention many and are skipped). Later pages for the same lab are body pages.
    """
    starts: dict[int, int] = {}
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        labs = labs_on_page(text)
        if len(labs) != 1:
            continue
        lab_num = labs[0]
        if lab_num in starts:
            continue
        if not 1 <= lab_num <= MAX_LAB_NUMBER:
            continue
        starts[lab_num] = i
    return starts


def write_section(reader: PdfReader, start: int, end_exclusive: int, dest: Path) -> None:
    """Write a contiguous page range from the source PDF into dest."""
    writer = PdfWriter()
    for p in range(start, end_exclusive):
        writer.add_page(reader.pages[p])
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        writer.write(f)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Overwrite existing per-lab PDFs.")
    args = parser.parse_args()

    if not SOURCE_PDF.exists():
        log.error("Source PDF not found: %s", SOURCE_PDF)
        return 1

    reader = PdfReader(str(SOURCE_PDF))
    total_pages = len(reader.pages)
    log.info("Source: %s (%s pages)", SOURCE_PDF.name, total_pages)

    starts = find_section_starts(reader)
    if not starts:
        log.error("No lab section starts detected. Heuristic may need tuning.")
        return 1

    found_labs = sorted(starts.keys())
    missing = [n for n in range(1, MAX_LAB_NUMBER + 1) if n not in starts]
    log.info("Detected: %s/%s labs", len(found_labs), MAX_LAB_NUMBER)
    if missing:
        log.info("Missing: %s", ", ".join(f"LAB-{n:02d}" for n in missing))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for lab_num in found_labs:
        start = starts[lab_num]
        next_labs = [s for n, s in starts.items() if s > start]  # end at next section
        end = min(next_labs) if next_labs else total_pages
        dest = OUT_DIR / f"LAB-{lab_num:02d}.pdf"
        if dest.exists() and not args.force:
            log.info("LAB-%02d -> pages %s-%s (skipped, already exists)", lab_num, start + 1, end)
            skipped += 1
            continue
        write_section(reader, start, end, dest)
        size_kb = dest.stat().st_size / 1024
        log.info(
            "LAB-%02d -> pages %s-%s (%s pages, %.0f KB)",
            lab_num,
            start + 1,
            end,
            end - start,
            size_kb,
        )
        written += 1

    log.info("Done. Written: %s, skipped: %s, missing: %s", written, skipped, len(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
