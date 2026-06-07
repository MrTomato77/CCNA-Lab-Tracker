"""Bundle on-disk assets (lab PDFs, quiz images, Packet Tracer .pka) into the DB.

Makes ``database/labs.db`` the single portable source of truth: after running
this, the app serves PDFs and images straight from the ``assets`` table and
materializes ``.pka`` files on demand, so handing the app to someone else is just
copying ``labs.db`` (+ the code) — no ``docs/``, ``data/quiz_images/`` or
``labs/`` folders and no machine-specific absolute paths.

Usage from the project root:

    python scripts/bundle_assets.py --probe   # list what would be bundled
    python scripts/bundle_assets.py           # write/refresh the assets table

Idempotent — re-running re-imports every file with INSERT OR REPLACE.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

import aiosqlite

ROOT = Path(__file__).resolve().parent.parent

DB_PATH    = ROOT / "database" / "labs.db"
DOCS_DIR   = ROOT / "docs"
IMAGES_DIR = ROOT / "data" / "quiz_images"
LABS_DIR   = ROOT / "labs"

# Mirror the allow-lists used at serve time (services/image_service.py,
# app.py is_safe_doc_path, services/file_importer.py extract_lab_id).
_PDF_RE   = re.compile(r"^LAB-\d{2}\.pdf$")
_IMAGE_RE = re.compile(r"^Q-\d{4}-\d+\.(?:png|jpg|gif|webp|bmp)$")
_PKA_RE   = re.compile(r"^LAB-\d{2}\.pka$")

_IMAGE_CONTENT_TYPES = {
    "png":  "image/png",
    "jpg":  "image/jpeg",
    "gif":  "image/gif",
    "webp": "image/webp",
    "bmp":  "image/bmp",
}


def _image_content_type(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower()
    return _IMAGE_CONTENT_TYPES.get(ext, "application/octet-stream")


def _collect() -> list[tuple[str, str, str, Path]]:
    """Return (kind, name, content_type, path) for every bundleable file."""
    items: list[tuple[str, str, str, Path]] = []
    if DOCS_DIR.is_dir():
        for p in sorted(DOCS_DIR.glob("*.pdf")):
            if _PDF_RE.match(p.name):
                items.append(("pdf", p.name, "application/pdf", p))
    if IMAGES_DIR.is_dir():
        for p in sorted(IMAGES_DIR.iterdir()):
            if p.is_file() and _IMAGE_RE.match(p.name):
                items.append(("image", p.name, _image_content_type(p.name), p))
    if LABS_DIR.is_dir():
        for p in sorted(LABS_DIR.glob("*.pka")):
            if _PKA_RE.match(p.name):
                items.append(("pka", p.name, "application/octet-stream", p))
    return items


def _fmt_size(n: int) -> str:
    mb = n / (1024 * 1024)
    return f"{mb:.1f} MB"


def probe() -> int:
    items = _collect()
    by_kind: dict[str, list[int]] = {"pdf": [], "image": [], "pka": []}
    for kind, _name, _ct, path in items:
        by_kind.setdefault(kind, []).append(path.stat().st_size)
    print(f"DB: {DB_PATH}")
    total = 0
    for kind in ("pdf", "image", "pka"):
        sizes = by_kind.get(kind, [])
        s = sum(sizes)
        total += s
        print(f"  {kind:6s}: {len(sizes):4d} files  {_fmt_size(s)}")
    print(f"  {'total':6s}: {len(items):4d} files  {_fmt_size(total)}")
    return 0


async def bundle() -> int:
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH} — run the server once to init it.",
              file=sys.stderr)
        return 1
    items = _collect()
    if not items:
        print("No bundleable assets found.", file=sys.stderr)
        return 1
    written = 0
    async with aiosqlite.connect(DB_PATH) as db:
        # The table normally exists (created at server startup); create it here
        # too so the script is usable standalone.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                kind         TEXT NOT NULL,
                name         TEXT NOT NULL,
                content_type TEXT NOT NULL,
                bytes        BLOB NOT NULL,
                PRIMARY KEY (kind, name)
            )
            """
        )
        for kind, name, content_type, path in items:
            data = path.read_bytes()
            await db.execute(
                "INSERT OR REPLACE INTO assets (kind, name, content_type, bytes) "
                "VALUES (?, ?, ?, ?)",
                (kind, name, content_type, data),
            )
            written += 1
        await db.commit()
    print(f"Bundled {written} assets into {DB_PATH.name}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="List what would be bundled without writing.")
    args = ap.parse_args(argv)
    if args.probe:
        return probe()
    return asyncio.run(bundle())


if __name__ == "__main__":
    sys.exit(main())
