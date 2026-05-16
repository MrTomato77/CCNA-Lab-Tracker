from robyn import Request, SubRouter
from loguru import logger
from pydantic import ValidationError
from core.responses import ErrorResponse, internal_error, ok, validation_error
from models.schemas import StatusUpdate, TimerSave
from services.lab_service import update_status, require_lab, reset_lab
from services.timer_service import save_timer_session

router = SubRouter(__name__, prefix="/api/labs")

@router.post("/:lab_id/status")
async def set_status(request: Request) -> dict | ErrorResponse:
    lab_id = request.path_params.get("lab_id")
    _, err_resp = await require_lab(lab_id)
    if err_resp:
        return err_resp
    try:
        data = StatusUpdate.model_validate(request.json())
    except ValidationError as e:
        return validation_error(e)
    await update_status(lab_id, data.status)
    return ok({"lab_id": lab_id, "status": data.status})

@router.post("/:lab_id/timer")
async def save_timer(request: Request) -> dict | ErrorResponse:
    lab_id = request.path_params.get("lab_id")
    _, err_resp = await require_lab(lab_id)
    if err_resp:
        return err_resp
    try:
        data = TimerSave.model_validate(request.json())
    except ValidationError as e:
        return validation_error(e)
    total = await save_timer_session(lab_id, data.started_at, data.duration)
    return ok({"lab_id": lab_id, "time_spent": total})

@router.post("/reset-single/:lab_id")
async def reset_single(request: Request) -> dict | ErrorResponse:
    lab_id = request.path_params.get("lab_id")
    _, err_resp = await require_lab(lab_id)
    if err_resp:
        return err_resp
    try:
        await reset_lab(lab_id)
        return ok(message=f"Lab {lab_id} has been reset")
    except Exception:
        logger.bind(name="api").exception("Unexpected error in reset_single")
        return internal_error("RESET_FAILED")
