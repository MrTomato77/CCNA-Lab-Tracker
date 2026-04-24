import os
from pathlib import Path
from robyn import Robyn, Request
from robyn.logger import logger
from dotenv import load_dotenv
from rich import print as rprint
from database.connection import init_db, close_db
from routers import labs, progress, launcher, stats, importer

load_dotenv()
app = Robyn(__file__)

# Static files — MUST be registered before routers
# Do NOT add any GET "/" route — it will conflict with serve_directory
app.serve_directory(
    route="/",
    directory_path=str(Path(__file__).parent / "public"),
    index_file="index.html",
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
