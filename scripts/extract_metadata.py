"""Sync lab metadata (difficulty + estimated time) into the DB.

Run from the project root after scripts/split_pdf.py:
    python scripts/extract_metadata.py

Re-running is safe: rows are updated in place.

Difficulty is editorial data and lives in `core/constants.py` (PDF star
extraction was unreliable across nested clip groups, so the values come
from the lab booklet's printed star ratings). Time, on the other hand, is
reliably extractable from the text layer.
"""

import asyncio
import logging
import re
import sys
from pathlib import Path

import aiosqlite
from pypdf import PdfReader
from pypdf.errors import PdfReadError

# Make the project root importable so `core.constants` resolves when the
# script is invoked as `python scripts/extract_metadata.py` from the repo
# root (no package install).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.constants import DIFFICULTY  # noqa: E402
from database.connection import _add_column_if_missing  # noqa: E402

DOCS_DIR = ROOT / "docs"
DB_PATH  = ROOT / "database" / "labs.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def extract_page1(pdf_path: Path) -> tuple[int | None, int | None]:
    """Return (difficulty 1-5, estimated_minutes) for a lab PDF.

    Difficulty comes from the editorial DIFFICULTY table (above).
    Estimated minutes is parsed from the page-1 text layer.
    """
    lab_id = pdf_path.stem
    difficulty = DIFFICULTY.get(lab_id)

    minutes: int | None = None
    try:
        reader = PdfReader(str(pdf_path))
        if reader.pages:
            text = reader.pages[0].extract_text() or ""
            # Pattern: "Time : 10 นาที"  or  "Time : 10 min"
            time_m = re.search(r'Time\s*[：:]\s*(\d+)', text, re.IGNORECASE)
            if time_m:
                minutes = int(time_m.group(1))
    except (PdfReadError, KeyError, ValueError) as exc:
        log.warning("%s: %s", pdf_path.name, exc)

    return difficulty, minutes


async def main() -> int:
    pdfs = sorted(DOCS_DIR.glob("LAB-*.pdf"))
    if not pdfs:
        log.error("No LAB-XX.pdf files found in %s", DOCS_DIR)
        log.error("Run scripts/split_pdf.py first.")
        return 1

    if not DB_PATH.exists():
        log.error("Database not found at %s", DB_PATH)
        log.error("Start the server once to initialise the DB, then re-run.")
        return 1

    log.info("Scanning %s PDFs in %s/", len(pdfs), DOCS_DIR.name)

    async with aiosqlite.connect(DB_PATH) as db:
        for col_name, col_def in [
            ("difficulty", "INTEGER DEFAULT NULL"),
            ("estimated_minutes", "INTEGER DEFAULT NULL"),
        ]:
            await _add_column_if_missing(db, "labs", col_name, col_def)
        await db.commit()

        updated = skipped = 0
        for pdf in pdfs:
            lab_id = pdf.stem              # "LAB-01"
            difficulty, minutes = extract_page1(pdf)

            tag = f"diff={difficulty}  time={minutes}m"
            if difficulty is None and minutes is None:
                log.info("%s: no metadata extracted - skipped (check PDF text)", lab_id)
                skipped += 1
            else:
                await db.execute(
                    "UPDATE labs SET difficulty=?, estimated_minutes=? WHERE id=?",
                    (difficulty, minutes, lab_id),
                )
                log.info("%s: %s", lab_id, tag)
                updated += 1

        await db.commit()

    log.info("Done. Updated: %s, skipped (no data): %s", updated, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
