"""Load hand-authored drag-and-drop pairs into the quiz DB.

Drag-and-drop questions present their items and answer key as images, so the
matching pairs cannot be parsed from the DOCX. They are authored by reading the
answer images into ``data/drag_drop_pairs.json`` (the source of truth), then
applied here.

For each question id with non-empty ``pairs``, this sets:
  - question_type = 'drag_drop'
  - pairs_json    = the authored {"pairs": [...]}
  - needs_review  = 0   (now answerable → enters the quiz pool)

Ids not present (or with empty pairs) are left untouched, so coverage rises
incrementally as more are authored. Idempotent and re-runnable. Re-run this
after any ``parse_questions.py`` rebuild (which resets these columns).

Usage from the project root:

    python scripts/load_drag_pairs.py --probe   # show what would change
    python scripts/load_drag_pairs.py           # apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import aiosqlite

ROOT      = Path(__file__).resolve().parent.parent
DB_PATH   = ROOT / "database" / "labs.db"
DATA_FILE = ROOT / "data" / "drag_drop_pairs.json"


def _load_authored() -> dict[str, dict]:
    if not DATA_FILE.exists():
        print(f"No data file at {DATA_FILE}", file=sys.stderr)
        return {}
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for qid, entry in raw.items():
        pairs = (entry or {}).get("pairs") or []
        # Each pair needs both sides; skip malformed/empty.
        clean = [p for p in pairs if p.get("left") and p.get("right")]
        if clean:
            out[str(qid)] = {"pairs": clean}
    return out


async def run(apply: bool) -> int:
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}", file=sys.stderr)
        return 1
    authored = _load_authored()
    if not authored:
        print("Nothing to load (no authored pairs).")
        return 0

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        existing = {
            str(r["id"])
            for r in await (await db.execute("SELECT id FROM questions")).fetchall()
        }
        applied = skipped = 0
        for qid, entry in authored.items():
            if qid not in existing:
                print(f"  skip Q{qid}: not in questions table", file=sys.stderr)
                skipped += 1
                continue
            buckets = sorted({p["right"] for p in entry["pairs"]})
            print(f"  Q{qid}: {len(entry['pairs'])} items → {len(buckets)} buckets "
                  f"({', '.join(buckets)})")
            if apply:
                await db.execute(
                    "UPDATE questions SET question_type='drag_drop', "
                    "pairs_json=?, needs_review=0 WHERE id=?",
                    (json.dumps(entry, ensure_ascii=False), qid),
                )
            applied += 1
        if apply:
            await db.commit()
    verb = "Applied" if apply else "Would apply"
    print(f"{verb} {applied} drag-drop question(s); skipped {skipped}.")
    if not apply:
        print("(dry run — re-run without --probe to write)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true", help="Dry run; show changes only.")
    args = ap.parse_args(argv)
    return asyncio.run(run(apply=not args.probe))


if __name__ == "__main__":
    sys.exit(main())
