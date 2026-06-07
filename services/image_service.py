"""Safe access to quiz images.

Images are stored as BLOBs in the ``assets`` table (kind='image') so the DB is
the single portable source of truth. Populated by ``scripts/bundle_assets.py``
(originals extracted from the source DOCX by ``scripts/parse_questions.py``).
This module only reads — it never writes or extracts.
"""
from __future__ import annotations

import re

from database.connection import get_db

_SAFE_NAME_RE = re.compile(r"^Q-\d{4}-\d+\.(?:png|jpg|gif|webp|bmp)$")

_CONTENT_TYPES = {
    "png":  "image/png",
    "jpg":  "image/jpeg",
    "gif":  "image/gif",
    "webp": "image/webp",
    "bmp":  "image/bmp",
}


def is_safe_image_name(filename: str) -> bool:
    """True when *filename* matches the `Q-NNNN-i.ext` allow-list pattern."""
    return bool(_SAFE_NAME_RE.fullmatch(filename))


def content_type_for(filename: str) -> str:
    """Return the HTTP content-type for an image filename's extension."""
    ext = filename.rsplit(".", 1)[-1].lower()
    return _CONTENT_TYPES.get(ext, "application/octet-stream")


async def read_image(filename: str) -> tuple[bytes, str] | None:
    """Read *filename* from the assets table; return ``(bytes, content_type)``.

    Returns ``None`` if the name fails the allow-list or isn't stored.
    """
    if not is_safe_image_name(filename):
        return None
    db = await get_db()
    async with db.execute(
        "SELECT bytes, content_type FROM assets WHERE kind='image' AND name=?",
        (filename,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    content_type = row["content_type"] or content_type_for(filename)
    return bytes(row["bytes"]), content_type
