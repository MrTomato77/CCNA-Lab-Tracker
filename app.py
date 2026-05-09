# Import order matters here. Each `from routers import …` line imports a module
# that creates a `SubRouter(...)` at module level. SubRouter inherits from
# Robyn, so its __init__ calls `logging.basicConfig(...)` and emits
# "SERVER IS RUNNING IN VERBOSE/DEBUG MODE" through `robyn.logger`. If
# `setup_logging()` runs after the router imports, those emits happen first
# and bypass our hijack — the console keeps the raw `INFO:robyn.logger:…`
# lines we're trying to silence. So: dotenv + logging setup BEFORE anything
# robyn-touching gets imported.
import os
from dotenv import load_dotenv
from core.logging_config import setup_logging

load_dotenv()
setup_logging()

from pathlib import Path
import aiofiles
from robyn import Robyn, Request, Response
from loguru import logger
from database.connection import init_db, close_db
from routers import labs, progress, launcher, stats, importer

app = Robyn(__file__)

PUBLIC   = Path(__file__).parent / "public"
DOCS_DIR = (Path(__file__).parent / "docs").resolve()

# SPA shell + static assets — read once at startup (see startup_handler) so
# the hot path doesn't run blocking sync I/O inside an async handler. PDFs
# are too many and too large to cache, so they go through aiofiles below.
_STATIC: dict[str, str] = {}

# Static assets are served via explicit routes instead of serve_directory("/").
# In Robyn 0.64.x, serve_directory mounted at "/" intercepts non-GET methods
# on every URL beneath it (including /api/...) and returns 405 Method Not
# Allowed before any registered POST route can match. Three explicit GET
# routes for the SPA shell + two static assets sidesteps that entirely.
@app.get("/")
async def index(request: Request):
    return Response(
        status_code=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
        description=_STATIC["index.html"],
    )

@app.get("/style.css")
async def style_css(request: Request):
    return Response(
        status_code=200,
        headers={"Content-Type": "text/css; charset=utf-8"},
        description=_STATIC["style.css"],
    )

@app.get("/app.js")
async def app_js(request: Request):
    return Response(
        status_code=200,
        headers={"Content-Type": "application/javascript; charset=utf-8"},
        description=_STATIC["app.js"],
    )

@app.get("/docs/:filename")
async def lab_docs(request: Request):
    # filename arrives as e.g. "LAB-07.pdf". Resolve the candidate path and
    # confirm it stays inside DOCS_DIR — defeats `..`, encoded variants, and
    # symlink farms that the old slash-reject couldn't catch.
    filename = request.path_params.get("filename", "")
    if not filename.endswith(".pdf"):
        return Response(status_code=404, headers={"Content-Type": "text/plain"}, description="Not found")
    try:
        pdf = (DOCS_DIR / filename).resolve()
    except (OSError, ValueError):
        return Response(status_code=404, headers={"Content-Type": "text/plain"}, description="Not found")
    if not pdf.is_relative_to(DOCS_DIR) or not pdf.is_file():
        return Response(status_code=404, headers={"Content-Type": "text/plain"}, description="Not found")
    async with aiofiles.open(pdf, "rb") as f:
        data = await f.read()
    return Response(
        status_code=200,
        headers={"Content-Type": "application/pdf"},
        description=data,
    )

# Register routers
app.include_router(labs.router)
app.include_router(progress.router)
app.include_router(launcher.router)
app.include_router(stats.router)
app.include_router(importer.router)

# NOTE: No CORS middleware — this is a same-origin app (browser and server
# both live at http://localhost:8080). Adding CORS headers here is noise and
# can mask real 4xx/5xx failures during debugging.

# Robyn 0.64 runs before_request and after_request in separate asyncio tasks,
# so ContextVar / id(request) / id(task) state set in `before` is gone by
# `after`. Without a way to correlate the two, we can't compute duration or
# attach the response status to the request line. So: log only on
# before_request — method + path is the high-value 80% of an access log.
@app.before_request()
async def _log_request(request: Request):
    method = getattr(request, "method", "?")
    path   = getattr(request, "url", None) or getattr(request, "path", "?")
    if hasattr(path, "path"):  # Robyn URL object → string
        path = path.path
    logger.bind(name="http").info(f"{method} {path}")
    return request

@app.startup_handler
async def startup():
    from services.pt_launcher import PT_EXE
    labs_dir = Path(__file__).parent / "labs"
    labs_dir.mkdir(exist_ok=True)
    # Cache the SPA shell + static assets once. They're served on every
    # page load and don't change at runtime, so reading them in async
    # handlers would block the event loop for no benefit.
    for name in ("index.html", "style.css", "app.js"):
        _STATIC[name] = (PUBLIC / name).read_text(encoding="utf-8")
    await init_db()
    # Warn (don't fail) if Packet Tracer isn't where .env says — user may
    # want to browse progress even without PT installed on this machine.
    if not Path(PT_EXE).exists():
        logger.bind(name="config").warning(
            f"Packet Tracer not found at {PT_EXE} — edit PACKET_TRACER_EXE in .env"
        )
    logger.bind(name="app").info("listening on http://localhost:8080")

@app.shutdown_handler
async def shutdown():
    await close_db()
    logger.bind(name="app").info("server stopped")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.start(port=port, host="127.0.0.1")
