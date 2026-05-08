from datetime import datetime, timezone
from robyn import Request, SubRouter
from core.responses import err
from services.lab_service import get_file_path, get_lab_by_id, update_last_opened
from services.pt_launcher import launch_pka

router = SubRouter(__name__, prefix="/api/labs")

@router.post("/:lab_id/open")
async def open_lab(request: Request):
    lab_id = request.path_params.get("lab_id")
    # Verify the lab id exists before falling through to launch_pka — a
    # bogus id like "LAB-99" used to surface as `NO_FILE_IMPORTED` (400),
    # which reads as "you forgot to import" instead of "no such lab".
    if not await get_lab_by_id(lab_id):
        return err({"success": False, "error": f"Lab {lab_id} not found",
                    "code": "LAB_NOT_FOUND"}, 404)
    file_path = await get_file_path(lab_id)
    result    = await launch_pka(file_path)
    if result["success"]:
        now = datetime.now(timezone.utc).isoformat()
        await update_last_opened(lab_id, now)
        return {"success": True}
    code   = result.get("code", "PT_UNKNOWN_ERROR")
    status = 400 if code == "NO_FILE_IMPORTED" else 500
    return err({"success": False, "error": result["error"], "code": code}, status)
