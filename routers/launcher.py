from datetime import datetime, timezone
from robyn import Request, SubRouter
from services.lab_service import get_file_path, update_last_opened
from services.pt_launcher import launch_pka

router = SubRouter(__name__, prefix="/api/labs")

@router.post("/:lab_id/open")
async def open_lab(request: Request):
    lab_id   = request.path_params.get("lab_id")
    file_path = await get_file_path(lab_id)
    result   = await launch_pka(file_path)
    if result["success"]:
        now = datetime.now(timezone.utc).isoformat()
        await update_last_opened(lab_id, now)
    code = result.get("code", "PT_UNKNOWN_ERROR")
    if not result["success"]:
        status = 400 if code == "NO_FILE_IMPORTED" else 500
        return {"success": False, "error": result["error"], "code": code}, status
    return {"success": True}
