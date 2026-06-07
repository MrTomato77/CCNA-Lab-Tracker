# dotenv + logging MUST run before any Robyn import — SubRouter.__init__
# calls logging.basicConfig() at import time, bypassing our loguru hijack.
import os
from dotenv import load_dotenv
from core.logging_config import setup_logging

load_dotenv()
setup_logging()

from pathlib import Path
import re
import aiofiles
from robyn import Robyn, Request, Response
from loguru import logger
from database.connection import init_db, close_db
from routers import labs, progress, launcher, stats, importer, quiz

app = Robyn(__file__)

PORT     = int(os.getenv("PORT", 8080))
PUBLIC   = Path(__file__).parent / "public"
DOCS_DIR = (Path(__file__).parent / "docs").resolve()

# Cached once at startup — avoids sync I/O in async handlers. PDFs stream via aiofiles.
# Explicit routes instead of serve_directory("/") because Robyn 0.64.x's serve_directory
# intercepts non-GET methods on every path beneath it, returning 405 before POST routes match.
_STATIC: dict[str, str] = {}
_STATIC_BIN: dict[str, bytes] = {}


def _load_static_recursive(root: Path) -> dict[str, str]:
    """Walk *root* and return {relative_path: text_content} for every .html/.css/.js.

    Paths are POSIX-style relative to *root* (e.g. "nav/nav.css") so they match
    the URL routes Robyn will serve them from. Binary assets (logo.ico) are
    handled separately by ``_STATIC_BIN``.

    Symlinks are skipped to prevent escape via a planted symlink in public/
    that points to files outside the tree.
    """
    exts = {".html", ".css", ".js"}
    out: dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink() and path.suffix in exts:
            rel = path.relative_to(root).as_posix()
            out[rel] = path.read_text(encoding="utf-8")
    return out


_INCLUDE_RE = re.compile(r"<!--INCLUDE:([\w./-]+)-->")


def _build_index(static: dict[str, str]) -> str:
    """Replace ``<!--INCLUDE:relative/path.html-->`` markers in
    ``static['index.html']`` with the matching entry from *static*.

    Single-pass, non-recursive: a partial containing an INCLUDE marker
    leaves the marker as a literal in the output. Unknown markers raise
    KeyError at boot — fail loud, never silently.
    """
    shell = static["index.html"]

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in static:
            raise KeyError(f"INCLUDE marker references unknown partial: {key}")
        return static[key]

    return _INCLUDE_RE.sub(_sub, shell)


_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".js":   "application/javascript; charset=utf-8",
}

_SAFE_STATIC_RE = re.compile(r"^[a-z0-9_-]+(/[a-z0-9_-]+)*\.(html|css|js)$")


def _resolve_static_path(rel: str) -> "str | None":
    """Validate *rel* (POSIX, no leading slash, no '..') and return it, or None."""
    if not _SAFE_STATIC_RE.fullmatch(rel):
        return None
    return rel


def _index_response() -> Response:
    return Response(
        status_code=200,
        headers={"Content-Type": "text/html; charset=utf-8",
                 "Cache-Control": "no-cache"},
        description=_STATIC["index.html"],
    )


@app.get("/")
async def index(request: Request) -> Response:
    return _index_response()


# Client-side routes: the SPA owns these paths (History API, no hash). Serving
# index.html here lets a direct load or refresh of e.g. /quiz boot the app,
# which then renders the matching page. Keep in sync with PAGE_TO_PATH in
# public/core/app-shell.js.
@app.get("/practical")
async def page_practical(request: Request) -> Response:
    return _index_response()

@app.get("/quiz")
async def page_quiz(request: Request) -> Response:
    return _index_response()

# Deep link to a past session review (/quiz/session/<id>). Three segments so it
# never collides with the two-segment static assets under /quiz/ (quiz.js, etc.);
# the SPA reads the id and opens that session on direct load or refresh.
@app.get("/quiz/session/:session_id")
async def page_quiz_session(request: Request) -> Response:
    return _index_response()

@app.get("/analytics")
async def page_analytics(request: Request) -> Response:
    return _index_response()

@app.get("/settings")
async def page_settings(request: Request) -> Response:
    return _index_response()

def _static_response(safe: str) -> Response:
    """Build a 200 Response for a validated *safe* static-file key.

    Caller is responsible for ensuring *safe* is already in ``_STATIC``
    (call ``_resolve_static_path`` first). Reads content-type from
    ``_CONTENT_TYPES``; falls back to ``text/plain`` for unknown
    extensions (defensive — should not occur because the whitelist regex
    only permits .html/.css/.js).
    """
    ext = "." + safe.rsplit(".", 1)[-1]
    # no-cache: browser must revalidate each load, so edits to CSS/JS show up
    # without bumping a ?v= query. Same-origin localhost app; bandwidth is moot.
    return Response(
        status_code=200,
        headers={"Content-Type": _CONTENT_TYPES.get(ext, "text/plain"),
                 "Cache-Control": "no-cache"},
        description=_STATIC[safe],
    )


@app.get("/:path")
async def static_file(request: Request) -> Response:
    """Serve any preloaded static file (single-segment path). Path must match _SAFE_STATIC_RE."""
    rel = request.path_params.get("path", "")
    safe = _resolve_static_path(rel)
    if safe is None or safe not in _STATIC:
        return Response(status_code=404, headers={}, description="Not found")
    return _static_response(safe)


# Robyn 0.64 /:path matches ONE segment only — add a second route for two-segment nested paths.
@app.get("/:dir/:filename")
async def static_file_nested(request: Request) -> Response:
    """Serve nested static files (two-segment paths, e.g. nav/nav.css)."""
    rel = f"{request.path_params.get('dir', '')}/{request.path_params.get('filename', '')}"
    safe = _resolve_static_path(rel)
    if safe is None or safe not in _STATIC:
        return Response(status_code=404, headers={}, description="Not found")
    return _static_response(safe)

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
    raw = _load_static_recursive(PUBLIC)
    _STATIC.update(raw)
    # Stitch the shell — overwrites the raw shell with the fully assembled HTML.
    _STATIC["index.html"] = _build_index(raw)
    _STATIC_BIN["logo.ico"] = (PUBLIC / "logo.ico").read_bytes()
    await init_db()
    # Warn but don't fail — user may browse progress without PT installed.
    if not Path(PT_EXE).exists():
        logger.bind(name="config").warning(
            f"Packet Tracer not found at {PT_EXE} — edit PACKET_TRACER_EXE in .env"
        )
    logger.bind(name="app").info(f"listening on http://localhost:{PORT}")

@app.shutdown_handler
async def shutdown() -> None:
    await close_db()
    logger.bind(name="app").info("server stopped")

if __name__ == "__main__":
    app.start(port=PORT, host="127.0.0.1")
