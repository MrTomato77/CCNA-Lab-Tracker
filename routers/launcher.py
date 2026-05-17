from datetime import datetime, timezone
from robyn import Request, SubRouter
from core.responses import ErrorResponse, err, ok
from services.lab_service import get_file_path, require_lab, update_last_opened
from services.pt_launcher import launch_pka, terminate_pt

router = SubRouter(__name__, prefix="/api/labs")

@router.post("/:lab_id/open")
async def open_lab(request: Request) -> dict | ErrorResponse:
    lab_id = request.path_params.get("lab_id")
    # Verify id first — bogus ids would surface as NO_FILE_IMPORTED instead of 404.
    _, err_resp = await require_lab(lab_id)
    if err_resp:
        return err_resp
    file_path = await get_file_path(lab_id)
    result    = await launch_pka(lab_id, file_path)
    if result["success"]:
        now = datetime.now(timezone.utc).isoformat()
        await update_last_opened(lab_id, now)
        return ok()
    code   = result.get("code", "PT_UNKNOWN_ERROR")
    status = 400 if code == "NO_FILE_IMPORTED" else 500
    return err({"success": False, "error": result["error"], "code": code}, status)


@router.post("/:lab_id/close")
async def close_lab(request: Request) -> dict | ErrorResponse:
    lab_id = request.path_params.get("lab_id")
    _, err_resp = await require_lab(lab_id)
    if err_resp:
        return err_resp
    result = terminate_pt(lab_id)
    if not result["success"]:
        return err(result, 500)
    return ok(data={"code": result.get("code")})
