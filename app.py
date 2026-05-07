import os
from pathlib import Path
from robyn import Robyn, Request, Response
from robyn.logger import logger
from robyn.responses import serve_html
from dotenv import load_dotenv
from rich import print as rprint
from database.connection import init_db, close_db
from routers import labs, progress, launcher, stats, importer

load_dotenv()
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

# Register routers
app.include_router(labs.router)
app.include_router(progress.router)
app.include_router(launcher.router)
app.include_router(stats.router)
app.include_router(importer.router)

# NOTE: No CORS middleware — this is a same-origin app (browser and server
# both live at http://localhost:8080). Adding CORS headers here is noise and
# can mask real 4xx/5xx failures during debugging.

@app.startup_handler
async def startup():
    from services.pt_launcher import PT_EXE
    labs_dir = Path(__file__).parent / "labs_files"
    labs_dir.mkdir(exist_ok=True)
    await init_db()
    # Warn (don't fail) if Packet Tracer isn't where .env says — user may
    # want to browse progress even without PT installed on this machine.
    if not Path(PT_EXE).exists():
        rprint(f"[yellow]⚠  Packet Tracer not found at {PT_EXE} — edit PACKET_TRACER_EXE in .env[/yellow]")
    rprint("[green]✓[/green] CCNA Lab Tracker ready at [bold]http://localhost:8080[/bold]")

@app.shutdown_handler
async def shutdown():
    await close_db()
    rprint("[yellow]Server stopped.[/yellow]")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.start(port=port, host="127.0.0.1")
