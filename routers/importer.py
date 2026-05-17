from robyn import Request, SubRouter
from pydantic import ValidationError
from core.responses import ErrorResponse, api_error, ok, validation_error
from models.schemas import FolderScan
from services import lab_service
from services.file_importer import import_from_folder, import_from_bytes

router = SubRouter(__name__, prefix="/api/import")

@router.post("/upload")
async def upload_files(request: Request) -> dict | ErrorResponse:
    files_raw = request.files
    if not files_raw:
        return api_error("No files received.", "NO_FILES", 400)

    results = []
    if isinstance(files_raw, dict):  # Robyn multipart shape varies by version
        items = files_raw.values()
    else:
        items = files_raw if isinstance(files_raw, (list, tuple)) else [files_raw]

    for file_data in items:
        filename = getattr(file_data, "filename", None) or getattr(file_data, "file_name", "unknown.pka")
        content  = getattr(file_data, "data",     None) or getattr(file_data, "file_data", b"")
        results.append(await import_from_bytes(filename, content))

    imported = [r for r in results if r["status"] == "imported"]
    return ok({"results": results, "imported_count": len(imported), "total_count": len(results)})

@router.post("/scan")
async def scan_folder(request: Request) -> dict | ErrorResponse:
    try:
        data = FolderScan.model_validate(request.json())
    except ValidationError as e:
        return validation_error(e)
    try:
        results = await import_from_folder(data.folder_path)
    except ValueError as e:
        return api_error(str(e), "VALIDATION_ERROR", 400)
    imported = [r for r in results if r["status"] == "imported"]
    return ok({"results": results, "imported_count": len(imported), "total_count": len(results)})

@router.get("/status")
async def import_status(request: Request) -> dict:
    rows     = await lab_service.list_with_paths()
    imported = [r for r in rows if r["file_path"] is not None]
    missing  = [r for r in rows if r["file_path"] is None]
    return ok({"imported": imported, "missing": missing,
               "imported_count": len(imported), "total": len(rows)})
