from robyn import Request, SubRouter
from loguru import logger
from core.responses import ErrorResponse, api_error, internal_error, lab_not_found, ok
from services.lab_service import get_all_labs, get_lab_by_id, read_summary, reset_all_labs

router = SubRouter(__name__, prefix="/api/labs")

@router.get("/")
async def all_labs(request: Request) -> dict:
    labs = await get_all_labs()
    return ok(labs)

# Register the more-specific /:lab_id/summary route BEFORE the catch-all
# /:lab_id so it doesn't get swallowed.
@router.get("/:lab_id/summary")
async def lab_summary(request: Request) -> dict | ErrorResponse:
    lab_id = request.path_params.get("lab_id")
    if not await get_lab_by_id(lab_id):
        return lab_not_found(lab_id)
    data = await read_summary(lab_id)
    if data is None:
        return api_error("Summary not authored yet.", "SUMMARY_MISSING", 404)
    return ok(data)

@router.get("/:lab_id")
async def single_lab(request: Request) -> dict | ErrorResponse:
    lab_id = request.path_params.get("lab_id")
    lab = await get_lab_by_id(lab_id)
    if not lab:
        return lab_not_found(lab_id)
    return ok(lab)

@router.post("/reset")
async def reset_all(request: Request) -> dict | ErrorResponse:
    try:
        await reset_all_labs()
        return ok(message="All labs have been reset successfully")
    except Exception:
        logger.bind(name="api").exception("Unexpected error in reset_all")
        return internal_error("RESET_FAILED")
