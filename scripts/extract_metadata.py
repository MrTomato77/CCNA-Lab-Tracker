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
import re
import sys
from pathlib import Path

import aiosqlite
from pypdf import PdfReader

# Make the project root importable so `core.constants` resolves when the
# script is invoked as `python scripts/extract_metadata.py` from the repo
# root (no package install).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.constants import DIFFICULTY  # noqa: E402

DOCS_DIR = ROOT / "docs"
DB_PATH  = ROOT / "database" / "labs.db"


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
    except Exception as exc:
        print(f"  [warn] {pdf_path.name}: {exc}")

    return difficulty, minutes


async def main() -> int:
    pdfs = sorted(DOCS_DIR.glob("LAB-*.pdf"))
    if not pdfs:
        print(f"[ERROR] No LAB-XX.pdf files found in {DOCS_DIR}")
        print("        Run scripts/split_pdf.py first.")
        return 1

    if not DB_PATH.exists():
        print(f"[ERROR] Database not found at {DB_PATH}")
        print("        Start the server once to initialise the DB, then re-run.")
        return 1

    print(f"Scanning {len(pdfs)} PDFs in {DOCS_DIR.name}/")

    async with aiosqlite.connect(DB_PATH) as db:
        for col in ("difficulty INTEGER", "estimated_minutes INTEGER"):
            try:
                await db.execute(f"ALTER TABLE labs ADD COLUMN {col} DEFAULT NULL")
            except Exception:
                pass
        await db.commit()

        updated = skipped = 0
        for pdf in pdfs:
            lab_id = pdf.stem              # "LAB-01"
            difficulty, minutes = extract_page1(pdf)

            tag = f"diff={difficulty}  time={minutes}m"
            if difficulty is None and minutes is None:
                print(f"  {lab_id}: no metadata extracted — skipped  (check PDF text)")
                skipped += 1
            else:
                await db.execute(
                    "UPDATE labs SET difficulty=?, estimated_minutes=? WHERE id=?",
                    (difficulty, minutes, lab_id),
                )
                print(f"  {lab_id}: {tag}")
                updated += 1

        await db.commit()

    print(f"\nDone. Updated: {updated}, skipped (no data): {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
