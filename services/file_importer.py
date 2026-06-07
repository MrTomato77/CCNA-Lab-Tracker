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

# 100 MB cap: rejects ZIP bombs / large unrelated files; real .pka files are ~1-5 MB.
_MAX_FILE_BYTES = 100 * 1024 * 1024
_MAX_FILE_MB = _MAX_FILE_BYTES // (1024 * 1024)

def extract_lab_id(filename: str) -> str | None:
    """Extract LAB-XX from irregular filenames (e.g. 'LAB-07 VLAN.pka', 'LAB-21-IPv4.pka').
    Returns zero-padded 'LAB-07' or None. Numbers outside 1..51 return None
    so junk files like 'LAB-99.pka' are skipped cleanly."""
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

def _result(
    filename: str,
    status: str,
    *,
    lab_id: str | None = None,
    reason: str | None = None,
    dest: Path | None = None,
) -> dict:
    result = {"file": filename}
    if lab_id is not None:
        result["lab_id"] = lab_id
    result["status"] = status
    if reason is not None:
        result["reason"] = reason
    if dest is not None:
        result["dest"] = str(dest)
    return result

def _validate_filename(filename: str) -> tuple[str | None, dict | None]:
    lab_id = extract_lab_id(filename)
    if not lab_id:
        return None, _result(
            filename,
            "skipped",
            reason="Cannot extract LAB-XX from filename",
        )
    return lab_id, None

def _validate_size(filename: str, lab_id: str, size: int) -> dict | None:
    if size == 0:
        return _result(
            filename,
            "skipped",
            lab_id=lab_id,
            reason="Empty file payload",
        )
    if size > _MAX_FILE_BYTES:
        return _result(
            filename,
            "skipped",
            lab_id=lab_id,
            reason=f"File exceeds {_MAX_FILE_MB} MB limit",
        )
    return None

async def _store_lab_pka(lab_id: str, content: bytes) -> None:
    """Persist the .pka into the assets table (source of truth) and set the
    lab's availability marker. The on-disk copy under labs/ is just a launch
    cache — pt_launcher re-materializes from the DB if it's missing."""
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO assets (kind, name, content_type, bytes) "
        "VALUES ('pka', ?, 'application/octet-stream', ?)",
        (f"{lab_id}.pka", content),
    )
    await db.execute("UPDATE labs SET file_path=? WHERE id=?", (f"{lab_id}.pka", lab_id))
    await db.commit()

async def import_from_bytes(filename: str, content: bytes) -> dict:
    lab_id, validation_failure = _validate_filename(filename)
    if validation_failure:
        return validation_failure
    assert lab_id is not None
    validation_failure = _validate_size(filename, lab_id, len(content))
    if validation_failure:
        return validation_failure
    dest = dest_path(lab_id)
    try:
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)
        await _store_lab_pka(lab_id, content)
        return _result(filename, "imported", lab_id=lab_id, dest=dest)
    except Exception as e:
        logger.error(f"Upload write failed: {e}")
        return _result(filename, "error", lab_id=lab_id, reason=str(e))

async def import_single_file(src: Path) -> dict:
    if src.suffix.lower() != ".pka":
        return _result(src.name, "skipped", reason="Not a .pka file")
    lab_id, validation_failure = _validate_filename(src.name)
    if validation_failure:
        return validation_failure
    assert lab_id is not None
    try:
        size = src.stat().st_size
    except OSError as e:
        return _result(src.name, "error", lab_id=lab_id, reason=str(e))
    validation_failure = _validate_size(src.name, lab_id, size)
    if validation_failure:
        return validation_failure
    dest = dest_path(lab_id)
    try:
        shutil.copy2(str(src), str(dest))
        await _store_lab_pka(lab_id, dest.read_bytes())
        logger.success(f"Imported {src.name} → {dest.name}")
        return _result(src.name, "imported", lab_id=lab_id, dest=dest)
    except Exception as e:
        logger.error(f"Copy failed: {e}")
        return _result(src.name, "error", lab_id=lab_id, reason=str(e))

async def import_from_folder(folder_path: str) -> list[dict]:
    folder = Path(folder_path).resolve()
    try:
        folder.relative_to(ALLOWED_IMPORT_ROOT)
    except ValueError as exc:
        raise ValueError(f"folder_path must be inside {ALLOWED_IMPORT_ROOT}") from exc
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder_path}")
    # Drop symlinks — rglob() follows them silently and could pull
    # .pka-named symlinks pointing anywhere on disk into the pipeline.
    pka_files = []
    for f in folder.rglob("*.pka"):
        if f.is_symlink():
            logger.warning(f"Skipping symlink: {f}")
            continue
        pka_files.append(f)
    if not pka_files:
        raise ValueError(f"No .pka files found in: {folder_path}")
    return [await import_single_file(f) for f in pka_files]
