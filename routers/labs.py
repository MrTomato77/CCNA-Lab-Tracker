from robyn import Request, SubRouter
from core.responses import err
from services.lab_service import get_all_labs, get_lab_by_id, reset_all_labs

router = SubRouter(__name__, prefix="/api/labs")

@router.get("/")
async def all_labs(request: Request):
    labs = await get_all_labs()
    return {"success": True, "data": labs}

@router.get("/:lab_id")
async def single_lab(request: Request):
    lab_id = request.path_params.get("lab_id")
    lab = await get_lab_by_id(lab_id)
    if not lab:
        return err({"success": False, "error": f"Lab {lab_id} not found.", "code": "LAB_NOT_FOUND"}, 404)
    return {"success": True, "data": lab}

@router.post("/reset")
async def reset_all(request: Request):
    try:
        await reset_all_labs()
        return {"success": True, "message": "All labs have been reset successfully"}
    except Exception as e:
        return err({"success": False, "error": str(e), "code": "RESET_FAILED"}, 500)
