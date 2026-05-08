"""Sync lab metadata (difficulty + estimated time) into the DB.

Run from the project root after scripts/split_pdf.py:
    python scripts/extract_metadata.py

Re-running is safe: rows are updated in place.

──────────────────────────────────────────────────────────────────────────
Why difficulty is a hardcoded table instead of a PDF parse:

The PDF stars are drawn as nested vector paths inside clip groups. Path
detection worked for ~80% of labs but silently miscounted others (filled
and outline polygons share the same coordinate signature; inferring "this
one was the painted star" from the content stream needs the full PDF
graphics-state stack, which pypdf doesn't expose).

Difficulty is fixed editorial data — a 51-row dict is simpler and more
reliable than a fragile parser. Update DIFFICULTY when new labs are added.
Time, on the other hand, is reliably extractable from the text layer.
"""

import asyncio
import re
import sys
from pathlib import Path

import aiosqlite
from pypdf import PdfReader

ROOT     = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
DB_PATH  = ROOT / "database" / "labs.db"


# Manually-verified difficulty (1-5 stars) per lab.
# Source: CCNA lab booklet page-1 ratings, cross-checked by hand.
DIFFICULTY: dict[str, int] = {
    "LAB-01": 1, "LAB-02": 1, "LAB-03": 1, "LAB-04": 1, "LAB-05": 1,
    "LAB-06": 1, "LAB-07": 1, "LAB-08": 1, "LAB-09": 3, "LAB-10": 1,
    "LAB-11": 1, "LAB-12": 1, "LAB-13": 1, "LAB-14": 1, "LAB-15": 1,
    "LAB-16": 1, "LAB-17": 1, "LAB-18": 1, "LAB-19": 1, "LAB-20": 1,
    "LAB-21": 1, "LAB-22": 1, "LAB-23": 1, "LAB-24": 1, "LAB-25": 1,
    "LAB-26": 1, "LAB-27": 1, "LAB-28": 1, "LAB-29": 1, "LAB-30": 1,
    "LAB-31": 1, "LAB-32": 1, "LAB-33": 1, "LAB-34": 1, "LAB-35": 1,
    "LAB-36": 3, "LAB-37": 3, "LAB-38": 3, "LAB-39": 1, "LAB-40": 1,
    "LAB-41": 2, "LAB-42": 2, "LAB-43": 2, "LAB-44": 2, "LAB-45": 2,
    "LAB-46": 2, "LAB-47": 2, "LAB-48": 2, "LAB-49": 2, "LAB-50": 2,
    "LAB-51": 2,
}


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
