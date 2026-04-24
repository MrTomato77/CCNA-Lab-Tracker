from robyn import Request, SubRouter
from services.lab_service import get_all_labs, get_lab_by_id

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
        return {"success": False, "error": f"Lab {lab_id} not found.", "code": "LAB_NOT_FOUND"}, 404
    return {"success": True, "data": lab}
