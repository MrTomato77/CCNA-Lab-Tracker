from robyn import Request, SubRouter
from core.responses import ok
from services import stats_service

router = SubRouter(__name__, prefix="/api/stats")


@router.get("/summary")
async def summary(request: Request) -> dict:
    return ok(await stats_service.summary())


@router.get("/by-category")
async def by_category(request: Request) -> dict:
    return ok(await stats_service.by_category())


@router.get("/slowest")
async def slowest(request: Request) -> dict:
    return ok(await stats_service.slowest())
