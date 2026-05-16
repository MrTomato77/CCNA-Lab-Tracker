import os
import re
import shutil
import aiofiles
from pathlib import Path
from loguru import logger
from core.constants import MAX_LAB_NUMBER
from database.connection import get_db

LABS_FILES_DIR = Path(__file__).parent.parent / "labs"
ALLOWED_IMPORT_ROOT = Path(os.getenv("CCNA_IMPORT_ROOT", str(Path.home()))).resolve()

# Real .pka files are ~1–5 MB. A 100 MB ceiling rejects ZIP-bomb-style
# uploads and accidental drops of large unrelated files (videos, ISOs)
# without cramping any legitimate Packet Tracer save.
_MAX_FILE_BYTES = 100 * 1024 * 1024

def extract_lab_id(filename: str) -> str | None:
    """
    Extract LAB-XX from irregular filenames:
      'LAB-07 VLAN and Trunking.pka'
      'LAB-21-IPv4 Static and Default Route.pka'  (extra dash)
      'LAB-49 DHCP Snooing.pka'                   (typo — still matches)
    Returns 'LAB-07' (zero-padded) or None.

    Numbers outside 1..51 (the seeded range) return None so a junk file
    like 'LAB-99.pka' fails the import with a clear "skipped" reason
    instead of slipping through and orphaning a row in `labs`.
    """
    match = re.search(r'\bLAB[-\s]?(\d{1,2})\b', filename, re.IGNORECASE)
    if not match:
        return None
    n = int(match.group(1))
    if not (1 <= n <= MAX_LAB_NUMBER):
        return None
    return f"LAB-{n:02d}"

def dest_path(lab_id: str) -> Path:
    """Return the canonical destination path for an imported .pka lab file."""
    return LABS_FILES_DIR / f"{lab_id}.pka"

async def _update_db(lab_id: str, path: Path) -> None:
    db = await get_db()
    await db.execute("UPDATE labs SET file_path=? WHERE id=?", (str(path), lab_id))
    await db.commit()

async def import_from_bytes(filename: str, content: bytes) -> dict:
    """Browser upload — write bytes async."""
    lab_id = extract_lab_id(filename)
    if not lab_id:
        return {"file": filename, "status": "skipped", "reason": "Cannot extract LAB-XX from filename"}
    if not content:
        return {"file": filename, "lab_id": lab_id, "status": "skipped",
                "reason": "Empty file payload"}
    if len(content) > _MAX_FILE_BYTES:
        return {"file": filename, "lab_id": lab_id, "status": "skipped",
                "reason": f"File exceeds {_MAX_FILE_BYTES // (1024*1024)} MB limit"}
    dest = dest_path(lab_id)
    try:
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)
        await _update_db(lab_id, dest)
        return {"file": filename, "lab_id": lab_id, "status": "imported", "dest": str(dest)}
    except Exception as e:
        logger.error(f"Upload write failed: {e}")
        return {"file": filename, "lab_id": lab_id, "status": "error", "reason": str(e)}

async def import_single_file(src: Path) -> dict:
    """Folder scan — copy file with shutil (sync, acceptable for one-time copy)."""
    if src.suffix.lower() != ".pka":
        return {"file": src.name, "status": "skipped", "reason": "Not a .pka file"}
    lab_id = extract_lab_id(src.name)
    if not lab_id:
        return {"file": src.name, "status": "skipped", "reason": "Cannot extract LAB-XX from filename"}
    try:
        size = src.stat().st_size
    except OSError as e:
        return {"file": src.name, "lab_id": lab_id, "status": "error", "reason": str(e)}
    if size == 0:
        return {"file": src.name, "lab_id": lab_id, "status": "skipped",
                "reason": "Empty file payload"}
    if size > _MAX_FILE_BYTES:
        return {"file": src.name, "lab_id": lab_id, "status": "skipped",
                "reason": f"File exceeds {_MAX_FILE_BYTES // (1024*1024)} MB limit"}
    dest = dest_path(lab_id)
    try:
        shutil.copy2(str(src), str(dest))
        await _update_db(lab_id, dest)
        logger.success(f"Imported {src.name} → {dest.name}")
        return {"file": src.name, "lab_id": lab_id, "status": "imported", "dest": str(dest)}
    except Exception as e:
        logger.error(f"Copy failed: {e}")
        return {"file": src.name, "lab_id": lab_id, "status": "error", "reason": str(e)}

async def import_from_folder(folder_path: str) -> list[dict]:
    folder = Path(folder_path).resolve()
    try:
        folder.relative_to(ALLOWED_IMPORT_ROOT)
    except ValueError as exc:
        raise ValueError(f"folder_path must be inside {ALLOWED_IMPORT_ROOT}") from exc
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder_path}")
    # Drop symlinks before iterating — rglob() follows them silently and
    # would let a hostile drop-folder pull `.pka`-named symlinks pointing
    # anywhere on disk into the import pipeline.
    pka_files = []
    for f in folder.rglob("*.pka"):
        if f.is_symlink():
            logger.warning(f"Skipping symlink: {f}")
            continue
        pka_files.append(f)
    if not pka_files:
        raise ValueError(f"No .pka files found in: {folder_path}")
    return [await import_single_file(f) for f in pka_files]
