from robyn import Request, SubRouter
from pydantic import ValidationError
from core.responses import err
from models.schemas import StatusUpdate, TimerSave
from services.lab_service import update_status, get_lab_by_id, reset_lab
from services.timer_service import save_timer_session

router = SubRouter(__name__, prefix="/api/labs")

@router.post("/:lab_id/status")
async def set_status(request: Request):
    lab_id = request.path_params.get("lab_id")
    if not await get_lab_by_id(lab_id):
        return err({"success": False, "error": f"Lab {lab_id} not found.", "code": "LAB_NOT_FOUND"}, 404)
    try:
        data = StatusUpdate.model_validate(request.json())
    except ValidationError as e:
        return err({"success": False, "error": e.errors()[0]["msg"], "code": "VALIDATION_ERROR"}, 422)
    await update_status(lab_id, data.status)
    return {"success": True, "data": {"lab_id": lab_id, "status": data.status}}

@router.post("/:lab_id/timer")
async def save_timer(request: Request):
    lab_id = request.path_params.get("lab_id")
    if not await get_lab_by_id(lab_id):
        return err({"success": False, "error": f"Lab {lab_id} not found.", "code": "LAB_NOT_FOUND"}, 404)
    try:
        data = TimerSave.model_validate(request.json())
    except ValidationError as e:
        return err({"success": False, "error": e.errors()[0]["msg"], "code": "VALIDATION_ERROR"}, 422)
    total = await save_timer_session(lab_id, data.started_at, data.duration)
    return {"success": True, "data": {"lab_id": lab_id, "time_spent": total}}

@router.post("/reset-single/:lab_id")
async def reset_single(request: Request):
    lab_id = request.path_params.get("lab_id")
    if not await get_lab_by_id(lab_id):
        return err({"success": False, "error": f"Lab {lab_id} not found.", "code": "LAB_NOT_FOUND"}, 404)
    try:
        await reset_lab(lab_id)
        return {"success": True, "message": f"Lab {lab_id} has been reset"}
    except Exception as e:
        return err({"success": False, "error": str(e), "code": "RESET_FAILED"}, 500)
