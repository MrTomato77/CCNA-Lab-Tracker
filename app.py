# dotenv + logging MUST run before any Robyn import — SubRouter.__init__
# calls logging.basicConfig() at import time, bypassing our loguru hijack.
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
from routers import labs, progress, launcher, stats, importer, quiz

app = Robyn(__file__)

PUBLIC   = Path(__file__).parent / "public"
DOCS_DIR = (Path(__file__).parent / "docs").resolve()

# Cached once at startup — avoids sync I/O in async handlers. PDFs stream via aiofiles.
# Explicit routes instead of serve_directory("/") because Robyn 0.64.x's serve_directory
# intercepts non-GET methods on every path beneath it, returning 405 before POST routes match.
_STATIC: dict[str, str] = {}
_STATIC_BIN: dict[str, bytes] = {}
@app.get("/")
async def index(request: Request) -> Response:
    return Response(
        status_code=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
        description=_STATIC["index.html"],
    )

@app.get("/style.css")
async def style_css(request: Request) -> Response:
    return Response(
        status_code=200,
        headers={"Content-Type": "text/css; charset=utf-8"},
        description=_STATIC["style.css"],
    )

@app.get("/app.js")
async def app_js(request: Request) -> Response:
    return Response(
        status_code=200,
        headers={"Content-Type": "application/javascript; charset=utf-8"},
        description=_STATIC["app.js"],
    )

@app.get("/logo.ico")
async def logo_ico(request: Request) -> Response:
    return Response(
        status_code=200,
        headers={"Content-Type": "image/x-icon",
                 "Cache-Control": "public, max-age=86400"},
        description=_STATIC_BIN["logo.ico"],
    )

@app.get("/favicon.ico")
async def favicon_ico(request: Request) -> Response:
    # Browsers request /favicon.ico regardless of the HTML <link> — alias to keep logs clean.
    return await logo_ico(request)

def is_safe_doc_path(filename: str) -> bool:
    """Return True when filename resolves to a PDF inside DOCS_DIR."""
    if not filename.endswith(".pdf"):
        return False
    try:
        pdf = (DOCS_DIR / filename).resolve()
    except (OSError, ValueError):
        return False
    return pdf.is_relative_to(DOCS_DIR)

@app.get("/docs/:filename")
async def lab_docs(request: Request) -> Response:
    filename = request.path_params.get("filename", "")
    if not is_safe_doc_path(filename):
        return Response(status_code=404, headers={"Content-Type": "text/plain"}, description="Not found")
    pdf = (DOCS_DIR / filename).resolve()
    if not pdf.is_file():
        return Response(status_code=404, headers={"Content-Type": "text/plain"}, description="Not found")
    async with aiofiles.open(pdf, "rb") as f:
        data = await f.read()
    return Response(
        status_code=200,
        headers={"Content-Type": "application/pdf"},
        description=data,
    )

app.include_router(labs.router)
app.include_router(progress.router)
app.include_router(launcher.router)
app.include_router(stats.router)
app.include_router(importer.router)
app.include_router(quiz.router)

# No CORS — same-origin app (browser + server both at localhost:8080).
# Log only in before_request: Robyn 0.64 runs before/after in separate tasks
# so state set in `before` is gone by `after`, making duration logging impossible.
@app.before_request()
async def _log_request(request: Request) -> Request:
    method = request.method
    path   = request.url
    if hasattr(path, "path"):  # Robyn URL object → string
        path = path.path
    logger.bind(name="http").info(f"{method} {path}")
    return request

@app.startup_handler
async def startup() -> None:
    from services.pt_launcher import PT_EXE
    labs_dir = Path(__file__).parent / "labs"
    labs_dir.mkdir(exist_ok=True)
    for name in ("index.html", "style.css", "app.js"):
        _STATIC[name] = (PUBLIC / name).read_text(encoding="utf-8")
    _STATIC_BIN["logo.ico"] = (PUBLIC / "logo.ico").read_bytes()
    await init_db()
    # Warn but don't fail — user may browse progress without PT installed.
    if not Path(PT_EXE).exists():
        logger.bind(name="config").warning(
            f"Packet Tracer not found at {PT_EXE} — edit PACKET_TRACER_EXE in .env"
        )
    logger.bind(name="app").info("listening on http://localhost:8080")

@app.shutdown_handler
async def shutdown() -> None:
    await close_db()
    logger.bind(name="app").info("server stopped")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.start(port=port, host="127.0.0.1")
