from robyn import Request, SubRouter
from services.file_importer import import_from_folder, import_from_bytes
from database.connection import get_db

router = SubRouter(__name__, prefix="/api/import")

@router.post("/upload")
async def upload_files(request: Request):
    files_raw = request.files
    if not files_raw:
        return {"success": False, "error": "No files received.", "code": "NO_FILES"}, 400

    results = []
    # Auto-detect Robyn multipart version
    if isinstance(files_raw, dict):
        items = files_raw.values()
    else:
        items = files_raw if isinstance(files_raw, (list, tuple)) else [files_raw]

    for file_data in items:
        filename = getattr(file_data, "filename", None) or getattr(file_data, "file_name", "unknown.pka")
        content  = getattr(file_data, "data",     None) or getattr(file_data, "file_data", b"")
        results.append(await import_from_bytes(filename, content))

    imported = [r for r in results if r["status"] == "imported"]
    return {"success": True, "data": {"results": results, "imported_count": len(imported), "total_count": len(results)}}

@router.post("/scan")
async def scan_folder(request: Request):
    body = request.json()
    folder_path = (body.get("folder_path") or "").strip()
    if not folder_path:
        return {"success": False, "error": "folder_path is required.", "code": "VALIDATION_ERROR"}, 422
    try:
        results = await import_from_folder(folder_path)
    except ValueError as e:
        return {"success": False, "error": str(e), "code": "FOLDER_NOT_FOUND"}, 404
    imported = [r for r in results if r["status"] == "imported"]
    return {"success": True, "data": {"results": results, "imported_count": len(imported), "total_count": len(results)}}

@router.get("/status")
async def import_status(request: Request):
    db = await get_db()
    async with db.execute("SELECT id, name, category, file_path FROM labs ORDER BY id") as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    imported = [r for r in rows if r["file_path"] is not None]
    missing  = [r for r in rows if r["file_path"] is None]
    return {"success": True, "data": {"imported": imported, "missing": missing,
                                       "imported_count": len(imported), "total": len(rows)}}
