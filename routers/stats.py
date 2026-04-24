from robyn import Request, SubRouter
from database.connection import get_db

router = SubRouter(__name__, prefix="/api/stats")

@router.get("/summary")
async def summary(request: Request):
    db = await get_db()
    async with db.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN p.status='done'         THEN 1 ELSE 0 END) AS done,
            SUM(CASE WHEN p.status='in_progress'  THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN p.status='not_started'  THEN 1 ELSE 0 END) AS not_started,
            SUM(p.time_spent) AS total_time_spent,
            SUM(CASE WHEN l.file_path IS NOT NULL THEN 1 ELSE 0 END) AS imported
        FROM progress p
        JOIN labs l ON p.lab_id = l.id
    """) as cur:
        row = dict(await cur.fetchone())
    total = row["total"] or 1
    row["completion_percent"] = round((row["done"] / total) * 100, 1)
    return {"success": True, "data": row}

@router.get("/by-category")
async def by_category(request: Request):
    db = await get_db()
    async with db.execute("""
        SELECT
            l.category,
            COUNT(*) AS total,
            SUM(CASE WHEN p.status='done'        THEN 1 ELSE 0 END) AS done,
            SUM(CASE WHEN p.status='in_progress' THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN p.status='not_started' THEN 1 ELSE 0 END) AS not_started
        FROM labs l
        JOIN progress p ON l.id = p.lab_id
        GROUP BY l.category
        ORDER BY l.category
    """) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    return {"success": True, "data": rows}

@router.get("/slowest")
async def slowest(request: Request):
    db = await get_db()
    async with db.execute("""
        SELECT l.id, l.name, p.time_spent
        FROM labs l
        JOIN progress p ON l.id = p.lab_id
        WHERE p.time_spent > 0
        ORDER BY p.time_spent DESC
        LIMIT 5
    """) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    return {"success": True, "data": rows}
