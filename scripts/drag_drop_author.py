"""List drag-and-drop questions to author (read-only helper).

Drag-drop pairs can't be parsed (the items/answers are images), so they are
authored by hand into ``data/drag_drop_pairs.json``. This lists every drag-drop
question with its id, prompt, and image filenames, marks which are already
authored, and flags the unusual image counts (not the typical "image-0 =
question, image-1 = answer" pattern) that need individual attention.

Usage:

    python scripts/drag_drop_author.py            # all drag-drop questions
    python scripts/drag_drop_author.py --todo     # only un-authored ones
    python scripts/drag_drop_author.py --ids      # bare id list (un-authored)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT      = Path(__file__).resolve().parent.parent
DB_PATH   = ROOT / "database" / "labs.db"
DATA_FILE = ROOT / "data" / "drag_drop_pairs.json"


def _authored_ids() -> set[str]:
    if not DATA_FILE.exists():
        return set()
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {str(k) for k, v in raw.items() if (v or {}).get("pairs")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--todo", action="store_true", help="Only un-authored questions.")
    ap.add_argument("--ids", action="store_true", help="Print only un-authored ids, space-separated.")
    args = ap.parse_args(argv)

    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}", file=sys.stderr)
        return 1

    authored = _authored_ids()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, prompt_en, image_filenames, question_type, needs_review "
        "FROM questions "
        "WHERE LOWER(prompt_en) LIKE '%drag%' AND LOWER(prompt_en) LIKE '%drop%' "
        "ORDER BY id"
    ).fetchall()
    con.close()

    todo_ids: list[str] = []
    shown = 0
    for r in rows:
        qid = str(r["id"])
        is_authored = qid in authored
        if args.todo and is_authored:
            continue
        if not is_authored:
            todo_ids.append(qid)
        if args.ids:
            continue
        imgs = json.loads(r["image_filenames"] or "[]")
        flag = "" if len(imgs) == 2 else f"  ⚠ {len(imgs)} images (check manually)"
        mark = "✓authored" if is_authored else "·todo"
        shown += 1
        print(f"Q{qid} [{mark}]{flag}")
        print(f"   prompt: {r['prompt_en'][:90]}")
        print(f"   images: {imgs}")

    if args.ids:
        print(" ".join(todo_ids))
        return 0

    total = len(rows)
    print(f"\n{shown} shown | {len(authored)} authored | {len(todo_ids)} to do | {total} total drag-drop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
