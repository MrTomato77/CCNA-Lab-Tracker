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
from robyn import Robyn, Request, Response
from robyn.responses import serve_html
from loguru import logger
from database.connection import init_db, close_db
from routers import labs, progress, launcher, stats, importer

app = Robyn(__file__)

PUBLIC = Path(__file__).parent / "public"

# Static assets are served via explicit routes instead of serve_directory("/").
# In Robyn 0.64.x, serve_directory mounted at "/" intercepts non-GET methods
# on every URL beneath it (including /api/...) and returns 405 Method Not
# Allowed before any registered POST route can match. Three explicit GET
# routes for the SPA shell + two static assets sidesteps that entirely.
@app.get("/")
async def index(request: Request):
    return serve_html(str(PUBLIC / "index.html"))

@app.get("/style.css")
async def style_css(request: Request):
    return Response(
        status_code=200,
        headers={"Content-Type": "text/css; charset=utf-8"},
        description=(PUBLIC / "style.css").read_text(encoding="utf-8"),
    )

@app.get("/app.js")
async def app_js(request: Request):
    return Response(
        status_code=200,
        headers={"Content-Type": "application/javascript; charset=utf-8"},
        description=(PUBLIC / "app.js").read_text(encoding="utf-8"),
    )

DOCS_DIR = Path(__file__).parent / "docs"

@app.get("/docs/:filename")
async def lab_docs(request: Request):
    # filename arrives as e.g. "LAB-07.pdf"; reject anything else to keep
    # this route from doubling as a generic file-server.
    filename = request.path_params.get("filename", "")
    if not filename.endswith(".pdf") or "/" in filename or "\\" in filename:
        return Response(status_code=404, headers={"Content-Type": "text/plain"}, description="Not found")
    pdf = DOCS_DIR / filename
    if not pdf.exists():
        return Response(status_code=404, headers={"Content-Type": "text/plain"}, description="Not found")
    return Response(
        status_code=200,
        headers={"Content-Type": "application/pdf"},
        description=pdf.read_bytes(),
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
