"""Safe access to quiz images stored under `data/quiz_images/`.

The directory is gitignored and populated by `scripts/parse_questions.py`.
This module only resolves and reads files — it never writes or extracts.
"""
from __future__ import annotations

import re
from pathlib import Path

import aiofiles

IMAGES_DIR = (Path(__file__).resolve().parent.parent / "data" / "quiz_images").resolve()

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


def resolve_image_path(filename: str) -> Path | None:
    """Return the on-disk path for *filename* if it's safe and exists."""
    if not is_safe_image_name(filename):
        return None
    candidate = (IMAGES_DIR / filename).resolve()
    if not candidate.is_relative_to(IMAGES_DIR):
        return None
    if not candidate.is_file():
        return None
    return candidate


def content_type_for(filename: str) -> str:
    """Return the HTTP content-type for an image filename's extension."""
    ext = filename.rsplit(".", 1)[-1].lower()
    return _CONTENT_TYPES.get(ext, "application/octet-stream")


async def read_image(filename: str) -> tuple[bytes, str] | None:
    """Read *filename* and return ``(bytes, content_type)`` or ``None``."""
    path = resolve_image_path(filename)
    if path is None:
        return None
    async with aiofiles.open(path, "rb") as f:
        data = await f.read()
    return data, content_type_for(filename)
