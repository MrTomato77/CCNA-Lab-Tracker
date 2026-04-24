# Comprehensive Build Prompt — CCNA Lab Tracker (v4.2 — hardened)

## 📜 Changelog from v4.1

Hardening pass driven by a review of v4.1. Every change below is self-contained; the overall structure, file tree, and phase layout are unchanged.

1. **Pinned Robyn version** — `robyn==0.64.4` in `requirements.txt` (was unpinned; API has shifted across versions).
2. **Fixed `update_status` bug** — used per-statement `cur.rowcount` instead of connection-cumulative `db.total_changes`.
3. **Dropped CORS middleware** — same-origin app doesn't need it; removing reduces moving parts and masks fewer real errors.
4. **Zombie timer cleanup on startup** — `DELETE FROM attempts WHERE duration IS NULL` in `init_db()` so a crashed-mid-session row can't resume as a multi-day timer.
5. **Eliminated dashboard N+1** — `GET /api/labs` now returns `open_session_started_at` via correlated subquery; `labCard.init()` no longer fetches per card. Dashboard load: 52 requests → 2.
6. **Live summary refresh** — Alpine store `Alpine.store('app')` so the progress bar updates immediately after status or timer changes.
7. **Packet Tracer path validated on startup** — warning if `PACKET_TRACER_EXE` is missing, instead of silent failure on first click.
8. **`start.bat` installs deps unconditionally** — `pip install -r requirements.txt` is idempotent; covers the "user uninstalled one dep" case.
9. **`status` CHECK constraint in schema** — defense-in-depth even if Pydantic is bypassed.
10. **`$nextTick` instead of `setTimeout(..., 50)`** for chart render — no more race disguised as a fix.
11. **Client-side elapsed cap (8h)** — belt-and-braces with #4: don't auto-resume an implausibly long session.
12. **Critical Rules renumbered and corrected** — rules #5 and #11 rewritten to match the new behavior.

Explicitly out of scope for v4.2 (deferred to a possible v4.3): multi-tab timer locking, migrations, duplicate-launch detection, upload size/MIME validation, CDN offline fallback, test framework.

---

## 🎯 Project Overview

Build a **local web application** called **CCNA Lab Tracker** for tracking study progress across 51 Cisco CCNA labs. The app allows the user to:
- **Import** `.pka` lab files into the app (drag & drop UI or folder scan)
- **Track** lab completion status per lab
- **Time** each study session with a persistent timer
- **Launch** `.pka` files directly into Cisco Packet Tracer via a button
- **Analyze** progress with charts and category breakdowns

Started via `start.bat` — double-click, browser opens, ready to use.

**Single-user. Offline-only. Local Windows machine. No auth. No Docker. No cloud.**

---

## 🖥️ Environment & Constraints

- **OS**: Windows 10/11
- **Python**: 3.11+ must be installed on host machine
- **Packet Tracer exe**: `C:\Program Files\Cisco Packet Tracer\PacketTracer.exe`
- **Port**: `8080`
- **No Docker, no virtualenv required, no cloud services**
- **Lab files**: imported by user at runtime — NOT hardcoded paths
- **SPA routing**: ALL navigation is client-side via Alpine.js `x-show`. Never use `window.location` to navigate between pages — Robyn will 404 on any path other than `/`.

---

## 🧱 Tech Stack

### Backend
| Tool | Version | Role |
|------|---------|------|
| **Python** | 3.11+ | Runtime |
| **Robyn** | latest | Async web framework (Rust runtime) |
| **aiosqlite** | latest | Async SQLite — NEVER use `sqlite3` sync |
| **pydantic** | `>=2.0` | Request validation — v2 syntax ONLY |
| **loguru** | latest | Structured logging |
| **python-dotenv** | latest | Load `.env` config |
| **rich** | latest | Pretty terminal output on startup |
| **aiofiles** | latest | Async file write for browser uploads |

> `shutil.copy2()` is acceptable for folder-scan import (one-time file copy, not hot path).
> `aiofiles` is required for browser upload (writes bytes from async request handler).

### Frontend (CDN only — no build step)
| Tool | CDN URL | Role |
|------|---------|------|
| **Alpine.js v3** | `https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js` | Reactive UI — load with `defer` |
| **Chart.js** | `https://cdn.jsdelivr.net/npm/chart.js` | Analytics bar chart — load BEFORE Alpine |
| **Lucide Icons** | `https://unpkg.com/lucide@latest/dist/umd/lucide.js` | Icon set |
| **JetBrains Mono** | Google Fonts | Monospace font for lab IDs |
| **DM Sans** | Google Fonts | Body text font |

> **CDN load order matters**: Chart.js must be loaded BEFORE Alpine.js `defer` script.
> Chart.js is synchronous and must be available when Alpine `statsPage()` renders.

### Storage
- **SQLite** at `database/labs.db`
- **Lab files** stored in `labs_files/` — normalized filenames: `LAB-01.pka`, `LAB-07.pka`

---

## 📁 Project Structure

```
ccna-lab-tracker/
│
├── start.bat                  # Entry point — double-click to run
├── stop.bat                   # Kill server on port 8080
├── .env                       # Config: Packet Tracer path, port
├── requirements.txt           # Python dependencies
├── README.md                  # Setup + reset instructions
│
├── app.py                     # Robyn entry point
│
├── routers/
│   ├── __init__.py            # Empty — required for Python package import
│   ├── labs.py                # GET /api/labs, GET /api/labs/{lab_id}
│   ├── progress.py            # POST /api/labs/{id}/status, /timer
│   ├── launcher.py            # POST /api/labs/{id}/open
│   ├── stats.py               # GET /api/stats/*
│   └── importer.py            # POST /api/import/upload, /scan  GET /api/import/status
│
├── services/
│   ├── __init__.py            # Empty — required for Python package import
│   ├── lab_service.py         # All DB queries for labs + progress (full implementation)
│   ├── timer_service.py       # Timer session save logic (full implementation)
│   ├── pt_launcher.py         # subprocess.Popen to open Packet Tracer
│   └── file_importer.py       # .pka matching, copy, DB update
│
├── database/
│   ├── __init__.py            # Empty — required for Python package import
│   ├── connection.py          # aiosqlite singleton + init + close
│   ├── schema.sql             # All CREATE TABLE statements
│   └── seed.py                # Seed 51 lab metadata only (no file_path)
│
├── models/
│   ├── __init__.py            # Empty — required for Python package import
│   └── schemas.py             # Pydantic v2 models
│
├── labs_files/                # Created automatically on startup
│   └── LAB-XX.pka             # Normalized filenames — managed by app
│
└── public/                    # Served as static files by Robyn
    ├── index.html             # SPA shell — 3 pages via Alpine x-show
    ├── style.css              # All styles (full skeleton provided below)
    └── app.js                 # All Alpine components (full implementation below)
```

---

## ⚙️ Configuration

### `.env`
```env
# Use forward slashes — backslashes may be parsed as escape sequences by python-dotenv
PACKET_TRACER_EXE=C:/Program Files/Cisco Packet Tracer/PacketTracer.exe
PORT=8080
LOG_LEVEL=INFO
```

> **Windows path warning**: Always use forward slashes `/` in `.env` values, not backslashes `\`.
> `python-dotenv` may interpret `\P`, `\C`, `\N` etc. as escape sequences.
> Forward slashes work correctly on Windows in Python's `Path()` and `subprocess`.

### `requirements.txt`
```
# Robyn is pinned — its API has shifted across versions (request.files shape,
# request.json() sync/async, before_request signature). If 0.64.4 is unavailable
# on your machine, lock to whatever `pip install robyn` resolves, then verify
# app.py still works and adjust handler signatures if needed.
robyn==0.64.4
aiosqlite
pydantic>=2.0
loguru
python-dotenv
rich
aiofiles
```

---

## 🗄️ Database Schema (`database/schema.sql`)

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS labs (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    file_path   TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS progress (
    lab_id      TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'not_started'
                CHECK(status IN ('not_started', 'in_progress', 'done')),
    time_spent  INTEGER NOT NULL DEFAULT 0,
    last_opened TEXT DEFAULT NULL,
    FOREIGN KEY (lab_id) REFERENCES labs(id)
);

CREATE TABLE IF NOT EXISTS attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lab_id      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    duration    INTEGER DEFAULT NULL,
    FOREIGN KEY (lab_id) REFERENCES labs(id)
);
```

**Rules:**
- `labs.file_path IS NULL` → not yet imported
- `attempts.duration IS NULL` → timer session currently running
- Always `PRAGMA foreign_keys=ON` + `PRAGMA journal_mode=WAL` on every connection open
- Always parameterized queries — never f-string SQL

---

## 🔌 Robyn Syntax — Complete Reference

> Robyn is NOT Flask or FastAPI. Use these exact patterns.

### `app.py`
```python
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
```

### SubRouter pattern (all routers follow this)
```python
from robyn import Request, SubRouter
from database.connection import get_db

router = SubRouter(__name__, prefix="/api/labs")

@router.get("/")
async def handler(request: Request):
    # Path params:   request.path_params.get("lab_id")
    # JSON body:     request.json()           → dict
    # Query string:  request.query_params.get("key")
    # Files:         request.files            → see multipart section
    return {"success": True, "data": [...]}

# Return tuple for non-200 status:
# return {"success": False, "error": "...", "code": "..."}, 404
```

### Robyn Multipart Upload — Two Patterns

Robyn's multipart API differs by version. Implement with auto-detection:

```python
@router.post("/upload")
async def upload_files(request: Request):
    files_raw = request.files
    if not files_raw:
        return {"success": False, "error": "No files received.", "code": "NO_FILES"}, 400

    results = []

    # Try both Robyn multipart patterns — detect at runtime
    if isinstance(files_raw, dict):
        # Pattern A: newer Robyn — dict of {field_name: FileData}
        # FileData attributes: .filename (str), .data (bytes)
        items = files_raw.values()
    else:
        # Pattern B: older Robyn — list of FileData
        # FileData attributes: .file_name (str), .file_data (bytes)
        items = files_raw if isinstance(files_raw, list) else [files_raw]

    for file_data in items:
        # Normalize attribute names across both patterns
        filename = getattr(file_data, "filename", None) or getattr(file_data, "file_name", "unknown.pka")
        content  = getattr(file_data, "data",     None) or getattr(file_data, "file_data", b"")
        result = await import_from_bytes(filename, content)
        results.append(result)

    imported = [r for r in results if r["status"] == "imported"]
    return {"success": True, "data": {"results": results, "imported_count": len(imported), "total_count": len(results)}}
```

### Standard response format (ALL endpoints must follow this)
```python
# Success
{"success": True, "data": {...}}     # single
{"success": True, "data": [...]}     # list

# Error — always 3 fields
{"success": False, "error": "Human-readable.", "code": "UPPER_SNAKE_CASE"}, STATUS_CODE

# Error codes used in this app:
# LAB_NOT_FOUND, PKA_NOT_FOUND, PT_NOT_FOUND, PT_PERMISSION_ERROR, PT_UNKNOWN_ERROR,
# NO_FILE_IMPORTED, IMPORT_FAILED, NO_FILES, FOLDER_NOT_FOUND, VALIDATION_ERROR
```

---

## 🗃️ Database Connection (`database/connection.py`)

```python
import aiosqlite
from pathlib import Path

DB_PATH    = Path(__file__).parent / "labs.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_db: aiosqlite.Connection | None = None

async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        raise RuntimeError("DB not initialized. Call init_db() first via startup_handler.")
    return _db

async def init_db():
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row   # access columns as row["name"]
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    # Zombie-session cleanup: if the last run crashed mid-timer, an attempts
    # row with duration IS NULL would "resume" on next load as a multi-day
    # timer and add bogus hours to time_spent. Delete stale open sessions —
    # we can't verify their duration, so don't credit any time.
    await _db.execute("DELETE FROM attempts WHERE duration IS NULL")
    await _db.commit()
    async with _db.execute("SELECT COUNT(*) FROM labs") as cur:
        if (await cur.fetchone())[0] == 0:
            from database.seed import seed_labs
            await seed_labs(_db)

async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None
```

---

## 🌱 Seed (`database/seed.py`)

```python
import aiosqlite
from loguru import logger

LAB_DEFINITIONS = [
    ("LAB-01", "Get Started with Cisco CLI",                     "CLI & Basic"),
    ("LAB-02", "Switching Operation",                            "CLI & Basic"),
    ("LAB-03", "Basic Configuration",                            "CLI & Basic"),
    ("LAB-04", "Password Recovery on Router",                    "CLI & Basic"),
    ("LAB-05", "Backup and Restore Configuration",               "CLI & Basic"),
    ("LAB-06", "Cisco Discovery Protocol (CDP)",                 "Switching & VLAN"),
    ("LAB-07", "VLAN and Trunking",                              "Switching & VLAN"),
    ("LAB-08", "Manual VLAN Pruning",                            "Switching & VLAN"),
    ("LAB-09", "Trunk Native VLAN",                              "Switching & VLAN"),
    ("LAB-10", "Voice VLAN",                                     "Switching & VLAN"),
    ("LAB-11", "Dynamic Trunking Protocol (DTP)",                "Switching & VLAN"),
    ("LAB-12", "Rapid PVST+",                                    "Switching & VLAN"),
    ("LAB-13", "Enhance STP Features with PortFast",             "Switching & VLAN"),
    ("LAB-14", "Enhance STP Features with Rootguard",            "Switching & VLAN"),
    ("LAB-15", "Enhance STP Features with BPDU Guard",           "Switching & VLAN"),
    ("LAB-16", "L2 Loop Test",                                   "Switching & VLAN"),
    ("LAB-17", "Layer 2 EtherChannel",                           "Switching & VLAN"),
    ("LAB-18", "Basic Wireless LAN Controller (WLC)",            "Wireless"),
    ("LAB-19", "Inter-VLAN with Router on a Stick (ROAS)",       "Inter-VLAN & Routing"),
    ("LAB-20", "Inter-VLAN with Switch Virtual Interface (SVI)", "Inter-VLAN & Routing"),
    ("LAB-21", "IPv4 Static and Default Route",                  "Inter-VLAN & Routing"),
    ("LAB-22", "IPv6 Static and Default Route",                  "Inter-VLAN & Routing"),
    ("LAB-23", "OSPFv2 Single Area",                             "Inter-VLAN & Routing"),
    ("LAB-24", "OSPFv2 Multi Area",                              "Inter-VLAN & Routing"),
    ("LAB-25", "OSPFv2 Network Type",                            "Inter-VLAN & Routing"),
    ("LAB-26", "OSPFv2 Summarization",                           "Inter-VLAN & Routing"),
    ("LAB-27", "OSPFv2 Default-information originate",           "Inter-VLAN & Routing"),
    ("LAB-28", "OSPFv2 Authentication",                          "Inter-VLAN & Routing"),
    ("LAB-29", "OSPFv2 Path Optimization",                       "Inter-VLAN & Routing"),
    ("LAB-30", "OSPFv3 for IPv6",                                "Inter-VLAN & Routing"),
    ("LAB-31", "IPv4 HSRP on Router",                            "HSRP & ACL"),
    ("LAB-32", "IPv4 HSRP on Switch",                            "HSRP & ACL"),
    ("LAB-33", "IPv4 Numbered ACL",                              "HSRP & ACL"),
    ("LAB-34", "Add Remark for IPv4 ACL",                        "HSRP & ACL"),
    ("LAB-35", "IPv4 Named ACL",                                 "HSRP & ACL"),
    ("LAB-36", "Implement Static NAT",                           "NAT & DHCP"),
    ("LAB-37", "Implement Dynamic NAT",                          "NAT & DHCP"),
    ("LAB-38", "Implement NAT Overloading (PAT)",                "NAT & DHCP"),
    ("LAB-39", "DHCP Server on Cisco IOS",                       "NAT & DHCP"),
    ("LAB-40", "DHCP Relay on Cisco IOS",                        "NAT & DHCP"),
    ("LAB-41", "DHCP Client on Cisco IOS",                       "NAT & DHCP"),
    ("LAB-42", "Network Time Protocol (NTP)",                    "Management"),
    ("LAB-43", "Syslog",                                         "Management"),
    ("LAB-44", "SNMP",                                           "Management"),
    ("LAB-45", "Netflow",                                        "Management"),
    ("LAB-46", "Enable SSH on Cisco IOS",                        "Management"),
    ("LAB-47", "Site-to-Site VPN with GRE",                      "Security & Advanced"),
    ("LAB-48", "Port Security",                                   "Security & Advanced"),
    ("LAB-49", "DHCP Snooping",                                  "Security & Advanced"),
    ("LAB-50", "Upgrade IOS on Router",                          "Security & Advanced"),
    ("LAB-51", "Network Controller",                             "Security & Advanced"),
]

async def seed_labs(db: aiosqlite.Connection):
    logger.info("Seeding 51 labs (metadata only — file_path stays NULL until import)...")
    for lab_id, name, category in LAB_DEFINITIONS:
        await db.execute(
            "INSERT OR IGNORE INTO labs (id, name, category) VALUES (?,?,?)",
            (lab_id, name, category)
        )
        await db.execute(
            "INSERT OR IGNORE INTO progress (lab_id) VALUES (?)",
            (lab_id,)
        )
    await db.commit()
    logger.success(f"Seeded {len(LAB_DEFINITIONS)} labs.")
```

---

## 🧰 Services — Full Implementations

### `services/lab_service.py`
```python
import aiosqlite
from database.connection import get_db

async def get_all_labs() -> list[dict]:
    db = await get_db()
    # open_session_started_at is NULL unless a timer is currently running.
    # Including it here lets the dashboard render 51 cards from ONE request
    # instead of 51 follow-up GET /api/labs/{id} fetches for attempt history.
    async with db.execute("""
        SELECT l.id, l.name, l.category, l.file_path,
               p.status, p.time_spent, p.last_opened,
               (SELECT started_at FROM attempts a
                WHERE a.lab_id = l.id AND a.duration IS NULL
                ORDER BY a.started_at DESC LIMIT 1) AS open_session_started_at
        FROM labs l
        JOIN progress p ON l.id = p.lab_id
        ORDER BY l.id
    """) as cur:
        return [dict(r) for r in await cur.fetchall()]

async def get_lab_by_id(lab_id: str) -> dict | None:
    db = await get_db()
    async with db.execute("""
        SELECT l.id, l.name, l.category, l.file_path,
               p.status, p.time_spent, p.last_opened
        FROM labs l
        JOIN progress p ON l.id = p.lab_id
        WHERE l.id = ?
    """, (lab_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    result = dict(row)
    # Fetch attempts — order DESC so open session (NULL duration) is first
    async with db.execute("""
        SELECT id, started_at, duration
        FROM attempts WHERE lab_id = ?
        ORDER BY started_at DESC
    """, (lab_id,)) as cur:
        result["attempts"] = [dict(a) for a in await cur.fetchall()]
    return result

async def update_status(lab_id: str, status: str) -> bool:
    db = await get_db()
    # Use per-statement cur.rowcount — db.total_changes is cumulative across
    # the connection's lifetime and will report True for every call after
    # the first successful update anywhere.
    async with db.execute(
        "UPDATE progress SET status=? WHERE lab_id=?",
        (status, lab_id)
    ) as cur:
        changed = cur.rowcount > 0
    await db.commit()
    return changed

async def update_last_opened(lab_id: str, timestamp: str):
    db = await get_db()
    await db.execute(
        "UPDATE progress SET last_opened=? WHERE lab_id=?",
        (timestamp, lab_id)
    )
    await db.commit()

async def get_file_path(lab_id: str) -> str | None:
    db = await get_db()
    async with db.execute("SELECT file_path FROM labs WHERE id=?", (lab_id,)) as cur:
        row = await cur.fetchone()
    return row["file_path"] if row else None
```

### `services/timer_service.py`
```python
import aiosqlite
from database.connection import get_db

async def save_timer_session(lab_id: str, started_at: str, duration: int) -> int:
    """
    duration == 0  → open new session (INSERT with NULL duration)
    duration  > 0  → close most recent open session (UPDATE + accumulate)

    Returns updated total time_spent for this lab.
    """
    db = await get_db()

    if duration == 0:
        # Start: persist open session immediately so timer survives refresh
        await db.execute(
            "INSERT INTO attempts (lab_id, started_at, duration) VALUES (?,?,NULL)",
            (lab_id, started_at)
        )
        await db.commit()
    else:
        # Stop: close the most recent open session for this lab
        await db.execute("""
            UPDATE attempts
            SET duration = ?
            WHERE id = (
                SELECT id FROM attempts
                WHERE lab_id = ? AND duration IS NULL
                ORDER BY started_at DESC
                LIMIT 1
            )
        """, (duration, lab_id))
        # Accumulate into progress.time_spent
        await db.execute(
            "UPDATE progress SET time_spent = time_spent + ? WHERE lab_id = ?",
            (duration, lab_id)
        )
        await db.commit()

    # Return updated total
    async with db.execute(
        "SELECT time_spent FROM progress WHERE lab_id=?", (lab_id,)
    ) as cur:
        row = await cur.fetchone()
    return row["time_spent"] if row else 0
```

### `services/pt_launcher.py`
```python
import os
import subprocess
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

load_dotenv()
PT_EXE = os.getenv("PACKET_TRACER_EXE", r"C:\Program Files\Cisco Packet Tracer\PacketTracer.exe")

async def launch_pka(file_path: str | None) -> dict:
    if not file_path:
        return {"success": False,
                "error": "This lab has not been imported yet. Go to the Import page first.",
                "code": "NO_FILE_IMPORTED"}

    pka = Path(file_path)
    pt  = Path(PT_EXE)

    if not pka.exists():
        return {"success": False,
                "error": f".pka file not found at {file_path}. Please re-import this lab.",
                "code": "PKA_NOT_FOUND"}

    if not pt.exists():
        return {"success": False,
                "error": f"Packet Tracer not found at: {PT_EXE}. Edit PACKET_TRACER_EXE in .env.",
                "code": "PT_NOT_FOUND"}

    try:
        subprocess.Popen([str(pt), str(pka)], shell=False)
        logger.info(f"Launched {pka.name}")
        return {"success": True}
    except PermissionError:
        return {"success": False, "error": "Permission denied launching Packet Tracer.",
                "code": "PT_PERMISSION_ERROR"}
    except Exception as e:
        logger.error(f"Launch error: {e}")
        return {"success": False, "error": str(e), "code": "PT_UNKNOWN_ERROR"}
```

### `services/file_importer.py`
```python
import re
import shutil
import aiofiles
from pathlib import Path
from loguru import logger
from database.connection import get_db

LABS_FILES_DIR = Path(__file__).parent.parent / "labs_files"

def extract_lab_id(filename: str) -> str | None:
    """
    Extract LAB-XX from irregular filenames:
      'LAB-07 VLAN and Trunking.pka'
      'LAB-21-IPv4 Static and Default Route.pka'  (extra dash)
      'LAB-49 DHCP Snooing.pka'                   (typo — still matches)
    Returns 'LAB-07' (zero-padded) or None.
    """
    match = re.search(r'\bLAB[-\s]?(\d{1,2})\b', filename, re.IGNORECASE)
    if match:
        return f"LAB-{int(match.group(1)):02d}"
    return None

def dest_path(lab_id: str) -> Path:
    return LABS_FILES_DIR / f"{lab_id}.pka"

async def _update_db(lab_id: str, path: Path):
    db = await get_db()
    await db.execute("UPDATE labs SET file_path=? WHERE id=?", (str(path), lab_id))
    await db.commit()

async def import_from_bytes(filename: str, content: bytes) -> dict:
    """Browser upload — write bytes async."""
    lab_id = extract_lab_id(filename)
    if not lab_id:
        return {"file": filename, "status": "skipped", "reason": "Cannot extract LAB-XX from filename"}
    dest = dest_path(lab_id)
    try:
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)
        await _update_db(lab_id, dest)
        return {"file": filename, "lab_id": lab_id, "status": "imported", "dest": str(dest)}
    except Exception as e:
        logger.error(f"Upload write failed: {e}")
        return {"file": filename, "lab_id": lab_id, "status": "error", "reason": str(e)}

async def import_single_file(src: Path) -> dict:
    """Folder scan — copy file with shutil (sync, acceptable for one-time copy)."""
    if src.suffix.lower() != ".pka":
        return {"file": src.name, "status": "skipped", "reason": "Not a .pka file"}
    lab_id = extract_lab_id(src.name)
    if not lab_id:
        return {"file": src.name, "status": "skipped", "reason": "Cannot extract LAB-XX from filename"}
    dest = dest_path(lab_id)
    try:
        shutil.copy2(str(src), str(dest))
        await _update_db(lab_id, dest)
        logger.success(f"Imported {src.name} → {dest.name}")
        return {"file": src.name, "lab_id": lab_id, "status": "imported", "dest": str(dest)}
    except Exception as e:
        logger.error(f"Copy failed: {e}")
        return {"file": src.name, "lab_id": lab_id, "status": "error", "reason": str(e)}

async def import_from_folder(folder_path: str) -> list[dict]:
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder_path}")
    pka_files = list(folder.rglob("*.pka"))
    if not pka_files:
        raise ValueError(f"No .pka files found in: {folder_path}")
    return [await import_single_file(f) for f in pka_files]
```

---

## 🔌 Routers — Full Implementations

### `routers/labs.py`
```python
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
```

### `routers/progress.py`
```python
from robyn import Request, SubRouter
from pydantic import ValidationError
from models.schemas import StatusUpdate, TimerSave
from services.lab_service import update_status, get_lab_by_id
from services.timer_service import save_timer_session

router = SubRouter(__name__, prefix="/api/labs")

@router.post("/:lab_id/status")
async def set_status(request: Request):
    lab_id = request.path_params.get("lab_id")
    if not await get_lab_by_id(lab_id):
        return {"success": False, "error": f"Lab {lab_id} not found.", "code": "LAB_NOT_FOUND"}, 404
    try:
        data = StatusUpdate.model_validate(request.json())
    except ValidationError as e:
        return {"success": False, "error": e.errors()[0]["msg"], "code": "VALIDATION_ERROR"}, 422
    await update_status(lab_id, data.status)
    return {"success": True, "data": {"lab_id": lab_id, "status": data.status}}

@router.post("/:lab_id/timer")
async def save_timer(request: Request):
    lab_id = request.path_params.get("lab_id")
    if not await get_lab_by_id(lab_id):
        return {"success": False, "error": f"Lab {lab_id} not found.", "code": "LAB_NOT_FOUND"}, 404
    try:
        data = TimerSave.model_validate(request.json())
    except ValidationError as e:
        return {"success": False, "error": e.errors()[0]["msg"], "code": "VALIDATION_ERROR"}, 422
    total = await save_timer_session(lab_id, data.started_at, data.duration)
    return {"success": True, "data": {"lab_id": lab_id, "time_spent": total}}
```

### `routers/launcher.py`
```python
from datetime import datetime, timezone
from robyn import Request, SubRouter
from services.lab_service import get_file_path, update_last_opened
from services.pt_launcher import launch_pka

router = SubRouter(__name__, prefix="/api/labs")

@router.post("/:lab_id/open")
async def open_lab(request: Request):
    lab_id   = request.path_params.get("lab_id")
    file_path = await get_file_path(lab_id)
    result   = await launch_pka(file_path)
    if result["success"]:
        now = datetime.now(timezone.utc).isoformat()
        await update_last_opened(lab_id, now)
    code = result.get("code", "PT_UNKNOWN_ERROR")
    if not result["success"]:
        status = 400 if code == "NO_FILE_IMPORTED" else 500
        return {"success": False, "error": result["error"], "code": code}, status
    return {"success": True}
```

### `routers/stats.py`
```python
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
```

### `routers/importer.py`
```python
from robyn import Request, SubRouter
from services.file_importer import import_from_folder, import_from_bytes
from database.connection import get_db

router = SubRouter(__name__, prefix="/api/import")

@router.post("/upload")
async def upload_files(request: Request):
    files_raw = request.files
    if not files_raw:
        return {"success": False, "error": "No files received.", "code": "NO_FILES"}, 400

    results = []
    # Auto-detect Robyn multipart version
    if isinstance(files_raw, dict):
        items = files_raw.values()
    else:
        items = files_raw if isinstance(files_raw, (list, tuple)) else [files_raw]

    for file_data in items:
        filename = getattr(file_data, "filename", None) or getattr(file_data, "file_name", "unknown.pka")
        content  = getattr(file_data, "data",     None) or getattr(file_data, "file_data", b"")
        results.append(await import_from_bytes(filename, content))

    imported = [r for r in results if r["status"] == "imported"]
    return {"success": True, "data": {"results": results, "imported_count": len(imported), "total_count": len(results)}}

@router.post("/scan")
async def scan_folder(request: Request):
    body = request.json()
    folder_path = (body.get("folder_path") or "").strip()
    if not folder_path:
        return {"success": False, "error": "folder_path is required.", "code": "VALIDATION_ERROR"}, 422
    try:
        results = await import_from_folder(folder_path)
    except ValueError as e:
        return {"success": False, "error": str(e), "code": "FOLDER_NOT_FOUND"}, 404
    imported = [r for r in results if r["status"] == "imported"]
    return {"success": True, "data": {"results": results, "imported_count": len(imported), "total_count": len(results)}}

@router.get("/status")
async def import_status(request: Request):
    db = await get_db()
    async with db.execute("SELECT id, name, category, file_path FROM labs ORDER BY id") as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    imported = [r for r in rows if r["file_path"] is not None]
    missing  = [r for r in rows if r["file_path"] is None]
    return {"success": True, "data": {"imported": imported, "missing": missing,
                                       "imported_count": len(imported), "total": len(rows)}}
```

---

## 📐 Pydantic v2 Models (`models/schemas.py`)

```python
from pydantic import BaseModel, field_validator
from typing import Literal

class StatusUpdate(BaseModel):
    status: Literal["not_started", "in_progress", "done"]

class TimerSave(BaseModel):
    started_at: str
    duration: int

    @field_validator("duration")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("duration must be >= 0")
        return v

class FolderScan(BaseModel):
    folder_path: str
```

---

## 🎨 CSS Skeleton (`public/style.css`)

```css
/* ── Variables ─────────────────────────────────────── */
:root {
  --bg:             #fafafa;
  --surface:        #ffffff;
  --border:         #e5e7eb;
  --text:           #111827;
  --text-muted:     #6b7280;
  --accent:         #049fd4;
  --accent-hover:   #0387b3;
  --done:           #10b981;
  --done-bg:        #ecfdf5;
  --progress:       #f59e0b;
  --progress-bg:    #fffbeb;
  --not-started:    #9ca3af;
  --font-mono:      'JetBrains Mono', monospace;
  --font-body:      'DM Sans', sans-serif;
  --radius:         6px;
}

/* ── Reset ─────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: var(--font-body); background: var(--bg); color: var(--text); }

/* ── Nav ────────────────────────────────────────────── */
nav { display: flex; align-items: center; gap: 8px; padding: 12px 24px;
      border-bottom: 1px solid var(--border); background: var(--surface); }
.app-title { font-family: var(--font-mono); font-weight: 600;
             font-size: 14px; margin-right: auto; }
nav button { padding: 6px 14px; border: 1px solid var(--border); border-radius: var(--radius);
             background: transparent; cursor: pointer; font-size: 13px; color: var(--text-muted); }
nav button.active { border-color: var(--accent); color: var(--accent); background: #e8f7fc; }

/* ── Page wrapper ───────────────────────────────────── */
.page { max-width: 1200px; margin: 0 auto; padding: 24px; }

/* ── Summary bar ────────────────────────────────────── */
.summary-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.progress-track { flex: 1; height: 8px; background: var(--border); border-radius: 99px; overflow: hidden; }
.progress-fill  { height: 100%; background: var(--accent); border-radius: 99px; transition: width .4s; }

/* ── Filter tabs ────────────────────────────────────── */
.filter-tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.filter-tabs button { padding: 5px 12px; border-radius: 99px; border: 1px solid var(--border);
                      background: transparent; cursor: pointer; font-size: 12px; }
.filter-tabs button.active { background: var(--accent); color: #fff; border-color: var(--accent); }

/* ── Search ─────────────────────────────────────────── */
.search-input { width: 100%; max-width: 360px; padding: 8px 12px; margin-bottom: 20px;
                border: 1px solid var(--border); border-radius: var(--radius);
                font-size: 13px; background: var(--surface); }

/* ── Cards grid ─────────────────────────────────────── */
.cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }

/* ── Lab card ───────────────────────────────────────── */
.lab-card { background: var(--surface); border: 1px solid var(--border);
            border-left: 4px solid var(--not-started);
            border-radius: var(--radius); padding: 16px; display: flex;
            flex-direction: column; gap: 8px; }
.lab-card--in_progress { border-left-color: var(--progress); background: var(--progress-bg); }
.lab-card--done        { border-left-color: var(--done);     background: var(--done-bg); }
.lab-card--no-file     { opacity: 0.7; }

.card-header { display: flex; justify-content: space-between; align-items: center; }
.lab-id   { font-family: var(--font-mono); font-size: 11px; font-weight: 600; color: var(--accent); }
.lab-name { font-size: 13px; font-weight: 500; line-height: 1.4; }
.lab-category { font-size: 11px; color: var(--text-muted); }

/* ── Badges ─────────────────────────────────────────── */
.badge { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 99px; }
.badge--not_started { background: #f3f4f6; color: var(--text-muted); }
.badge--in_progress { background: #fef3c7; color: #92400e; }
.badge--done        { background: #d1fae5; color: #065f46; }
.badge--not-imported { background: #fee2e2; color: #991b1b; }

/* ── Timer ──────────────────────────────────────────── */
.timer-section { display: flex; align-items: center; gap: 8px; }
.timer-display { font-family: var(--font-mono); font-size: 18px; font-weight: 600;
                 color: var(--text); min-width: 80px; }
.timer-btns { display: flex; gap: 4px; }
.btn-icon { padding: 4px 8px; border: 1px solid var(--border); border-radius: var(--radius);
            background: transparent; cursor: pointer; font-size: 12px; }
.btn-icon:hover    { background: var(--bg); }
.btn-stop          { border-color: var(--progress); color: var(--progress); }
.timer-meta        { font-size: 11px; color: var(--text-muted); }

/* ── Status select ──────────────────────────────────── */
.status-select { padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--radius);
                 font-size: 12px; background: var(--surface); cursor: pointer; width: 100%; }

/* ── Launch button ──────────────────────────────────── */
.btn-launch { padding: 8px; border: 1px solid var(--accent); border-radius: var(--radius);
              background: transparent; color: var(--accent); cursor: pointer;
              font-size: 12px; font-weight: 600; width: 100%; }
.btn-launch:hover    { background: var(--accent); color: #fff; }
.btn-launch:disabled { border-color: var(--border); color: var(--text-muted); cursor: not-allowed; }

/* ── Toast ──────────────────────────────────────────── */
.toast { font-size: 11px; padding: 6px 10px; background: #111; color: #fff;
         border-radius: var(--radius); margin-top: 4px; }

/* ── Loading spinner ────────────────────────────────── */
.loading { text-align: center; padding: 48px; color: var(--text-muted); font-size: 13px; }

/* ── Import page ────────────────────────────────────── */
.import-section { background: var(--surface); border: 1px solid var(--border);
                  border-radius: var(--radius); padding: 20px; margin-bottom: 20px; }
.import-section h3 { font-size: 14px; margin-bottom: 12px; }
.dropzone { border: 2px dashed var(--border); border-radius: var(--radius);
            padding: 40px; text-align: center; color: var(--text-muted); transition: .2s; }
.dropzone.dragging { border-color: var(--accent); background: #e8f7fc; }
.dropzone p { margin-bottom: 8px; font-size: 13px; }
.btn-upload { display: inline-block; padding: 8px 16px; border: 1px solid var(--accent);
              border-radius: var(--radius); color: var(--accent); cursor: pointer; font-size: 13px; }
#fileInput { display: none; }

.folder-input-row { display: flex; gap: 8px; }
.folder-input { flex: 1; padding: 8px 12px; border: 1px solid var(--border);
                border-radius: var(--radius); font-size: 13px; }
.btn-scan { padding: 8px 16px; background: var(--accent); color: #fff; border: none;
            border-radius: var(--radius); cursor: pointer; font-size: 13px; }
.btn-scan:disabled { opacity: 0.5; cursor: not-allowed; }

.import-results { margin-top: 16px; }
.import-results h3 { font-size: 14px; margin-bottom: 8px; }
.result-row { display: flex; gap: 10px; align-items: center; padding: 6px 0;
              border-bottom: 1px solid var(--border); font-size: 12px; }
.result-detail { color: var(--text-muted); margin-left: auto; }
.result--error  { color: #dc2626; }
.result--skipped { color: var(--text-muted); }

.missing-row { display: flex; align-items: center; gap: 10px; padding: 6px 0;
               border-bottom: 1px solid var(--border); font-size: 12px; }

.btn-primary { display: inline-block; margin-top: 12px; padding: 8px 16px;
               background: var(--accent); color: #fff; border: none;
               border-radius: var(--radius); cursor: pointer; font-size: 13px; }

/* ── Stats page ─────────────────────────────────────── */
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
.stat-card  { background: var(--surface); border: 1px solid var(--border);
              border-radius: var(--radius); padding: 20px; text-align: center; }
.stat-num   { font-family: var(--font-mono); font-size: 28px; font-weight: 600;
              color: var(--accent); margin-bottom: 4px; }
.category-bars { margin-top: 24px; }
.cat-row    { display: flex; align-items: center; gap: 12px; margin-bottom: 10px;
              font-size: 12px; }
.cat-row span:first-child { width: 180px; flex-shrink: 0; color: var(--text-muted); }
.cat-track  { flex: 1; height: 8px; background: var(--border); border-radius: 99px; overflow: hidden; }
.cat-fill   { height: 100%; background: var(--done); border-radius: 99px; transition: width .4s; }
.cat-row span:last-child { width: 40px; text-align: right; color: var(--text-muted); }
```

---

## 🖥️ Frontend — `public/index.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CCNA Lab Tracker</title>
  <link rel="icon" href="data:,">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="style.css">
  <!-- Chart.js MUST load before Alpine (synchronous) -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>
  <!-- Alpine MUST be last, with defer -->
  <script src="https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js" defer></script>
  <script src="app.js" defer></script>
</head>
<body x-data="appShell()" x-init="init()">

  <nav>
    <span class="app-title">CCNA Lab Tracker</span>
    <button @click="page='dashboard'" :class="{active: page==='dashboard'}">Dashboard</button>
    <button @click="page='import'"    :class="{active: page==='import'}">Import Labs</button>
    <button @click="page='stats'"     :class="{active: page==='stats'}">Analytics</button>
  </nav>

  <!-- DASHBOARD -->
  <div class="page" x-show="page==='dashboard'">
    <div x-show="loading" class="loading">Loading labs...</div>
    <template x-if="!loading">
      <div>
        <div class="summary-bar">
          <span x-text="`${summary.done} / ${summary.total} Completed`" style="font-size:14px;font-weight:600"></span>
          <div class="progress-track"><div class="progress-fill" :style="`width:${summary.completion_percent}%`"></div></div>
          <span x-text="`${summary.completion_percent}%`" style="font-size:13px;color:var(--text-muted)"></span>
          <span x-text="`⏱ ${formatTotalTime(summary.total_time_spent)}`" style="font-size:12px;color:var(--text-muted)"></span>
        </div>
        <div class="filter-tabs">
          <button @click="filterCat=''" :class="{active:filterCat===''}">All (51)</button>
          <template x-for="cat in categories" :key="cat">
            <button @click="filterCat=cat" :class="{active:filterCat===cat}" x-text="cat"></button>
          </template>
        </div>
        <input type="text" x-model="search" placeholder="Search by name or ID..." class="search-input">
        <div class="cards-grid">
          <template x-for="lab in filteredLabs" :key="lab.id">
            <div x-data="labCard(lab)" x-init="init()" :class="cardClass()">
              <div class="card-header">
                <span class="lab-id" x-text="lab.id"></span>
                <span :class="badgeClass()" x-text="statusLabel()"></span>
              </div>
              <div class="lab-name" x-text="lab.name"></div>
              <div class="lab-category" x-text="lab.category"></div>
              <div class="timer-section">
                <span class="timer-display" x-text="formatTime(elapsed)"></span>
                <div class="timer-btns">
                  <button @click="startTimer()" x-show="!running" class="btn-icon" title="Start">▶</button>
                  <button @click="stopTimer()"  x-show="running"  class="btn-icon btn-stop" title="Stop">⏹</button>
                  <button @click="resetTimer()"                    class="btn-icon" title="Reset">↺</button>
                </div>
              </div>
              <div class="timer-meta">Total: <span x-text="formatTime(lab.time_spent)"></span></div>
              <select x-model="lab.status" @change="updateStatus()" class="status-select">
                <option value="not_started">Not Started</option>
                <option value="in_progress">In Progress</option>
                <option value="done">Done</option>
              </select>
              <button @click="launch()" class="btn-launch"
                :disabled="!lab.file_path"
                :title="lab.file_path ? 'Open in Packet Tracer' : 'Import this lab first'"
                x-text="lab.file_path ? '▶ Launch in Packet Tracer' : '⚠ Not Imported — Go to Import'">
              </button>
              <div x-show="toast" x-text="toastMsg" class="toast" x-transition></div>
            </div>
          </template>
        </div>
      </div>
    </template>
  </div>

  <!-- IMPORT PAGE -->
  <div class="page" x-show="page==='import'" x-data="importPage()" x-init="loadStatus()">
    <h2 style="font-size:18px;margin-bottom:20px">Import Lab Files</h2>
    <div class="import-section">
      <h3>Method 1 — Upload Files (drag & drop or browse)</h3>
      <div class="dropzone"
        @dragover.prevent="dragging=true"
        @dragleave.prevent="dragging=false"
        @drop.prevent="handleDrop($event)"
        :class="{dragging}">
        <p>Drag & drop .pka files here</p>
        <p>or</p>
        <input type="file" id="fileInput" multiple accept=".pka" @change="handleFileInput($event)">
        <label for="fileInput" class="btn-upload">Browse Files</label>
      </div>
    </div>
    <div class="import-section">
      <h3>Method 2 — Scan Folder</h3>
      <div class="folder-input-row">
        <input type="text" x-model="folderPath" class="folder-input"
               placeholder="e.g. D:\CCNA Network Labs Professional\Labs">
        <button @click="scanFolder()" :disabled="scanning" class="btn-scan">
          <span x-show="!scanning">Scan Folder</span>
          <span x-show="scanning">Scanning...</span>
        </button>
      </div>
    </div>
    <template x-if="results.length > 0">
      <div class="import-results">
        <h3 x-text="`Results — ${importedCount} / ${results.length} imported`"></h3>
        <template x-for="r in results" :key="r.file">
          <div class="result-row" :class="`result--${r.status}`">
            <span x-text="r.status==='imported'?'✅':r.status==='skipped'?'⚠️':'❌'"></span>
            <span x-text="r.file"></span>
            <span class="result-detail" x-text="r.lab_id ?? r.reason"></span>
          </div>
        </template>
        <button @click="window.dispatchEvent(new CustomEvent('refresh-labs')); page='dashboard'" class="btn-primary">
          Go to Dashboard
        </button>
      </div>
    </template>
    <div class="import-section" style="margin-top:20px">
      <h3 x-text="`Current Status — ${status.imported_count} / ${status.total} imported`"></h3>
      <template x-for="lab in status.missing" :key="lab.id">
        <div class="missing-row">
          <span class="lab-id" x-text="lab.id"></span>
          <span x-text="lab.name" style="flex:1;font-size:12px"></span>
          <span class="badge badge--not-imported">Missing</span>
        </div>
      </template>
    </div>
  </div>

  <!-- ANALYTICS PAGE -->
  <div class="page" x-show="page==='stats'" x-data="statsPage()" x-init="load()">
    <h2 style="font-size:18px;margin-bottom:20px">Analytics</h2>
    <div x-show="loading" class="loading">Loading analytics...</div>
    <template x-if="!loading">
      <div>
        <div class="stats-grid">
          <div class="stat-card"><div class="stat-num" x-text="summary.done"></div><div>Done</div></div>
          <div class="stat-card"><div class="stat-num" x-text="summary.in_progress"></div><div>In Progress</div></div>
          <div class="stat-card"><div class="stat-num" x-text="summary.not_started"></div><div>Not Started</div></div>
          <div class="stat-card"><div class="stat-num" x-text="formatTime(summary.total_time_spent)"></div><div>Total Time</div></div>
        </div>
        <canvas id="timeChart" height="80"></canvas>
        <div class="category-bars" style="margin-top:24px">
          <template x-for="cat in byCategory" :key="cat.category">
            <div class="cat-row">
              <span x-text="cat.category"></span>
              <div class="cat-track">
                <div class="cat-fill" :style="`width:${cat.total>0?(cat.done/cat.total)*100:0}%`"></div>
              </div>
              <span x-text="`${cat.done}/${cat.total}`"></span>
            </div>
          </template>
        </div>
      </div>
    </template>
  </div>

</body>
</html>
```

---

## 📜 `public/app.js` — All Alpine Components

```javascript
// Alpine store — single source of truth for summary so any component can
// trigger a refresh after a mutation (status change, timer stop) and the
// dashboard progress bar / analytics page pick it up immediately.
document.addEventListener("alpine:init", () => {
  Alpine.store("app", {
    summary: { done:0, in_progress:0, not_started:0, total:51,
               completion_percent:0, total_time_spent:0 },
    async refreshSummary() {
      try {
        const res  = await fetch("/api/stats/summary");
        const json = await res.json();
        if (json.success) this.summary = json.data;
      } catch (e) { console.error("Summary refresh failed:", e); }
    }
  });
});

// ── App Shell ─────────────────────────────────────────────────────────────
function appShell() {
  return {
    page: "dashboard",
    loading: true,
    labs: [],
    filterCat: "",
    search: "",
    categories: [
      "CLI & Basic", "Switching & VLAN", "Wireless",
      "Inter-VLAN & Routing", "HSRP & ACL", "NAT & DHCP",
      "Management", "Security & Advanced"
    ],

    // Convenience getter so existing `x-text="summary.done"` bindings still work
    get summary() { return this.$store.app.summary; },

    async init() {
      await this.fetchLabs();
      window.addEventListener("refresh-labs", () => this.fetchLabs());
    },

    async fetchLabs() {
      this.loading = true;
      try {
        const labsRes = await fetch("/api/labs");
        this.labs = (await labsRes.json()).data;
        await this.$store.app.refreshSummary();
      } catch (e) {
        console.error("Failed to load labs:", e);
      } finally {
        this.loading = false;
      }
    },

    get filteredLabs() {
      const cat = this.filterCat;
      const q   = this.search.toLowerCase();
      return this.labs.filter(lab =>
        (!cat || lab.category === cat) &&
        (!q   || lab.name.toLowerCase().includes(q) || lab.id.toLowerCase().includes(q))
      );
    },

    formatTotalTime(s = 0) {
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return h > 0 ? `${h}h ${m}m` : `${m}m`;
    }
  }
}

// ── Lab Card ──────────────────────────────────────────────────────────────
function labCard(initialLab) {
  return {
    lab: { ...initialLab },
    running: false,
    elapsed: 0,
    sessionStart: null,
    interval: null,
    toast: false,
    toastMsg: "",

    init() {
      // Resume an open timer session if one exists. The open session's
      // started_at is delivered inline with GET /api/labs (no per-card
      // fetch) via the open_session_started_at column.
      if (!this.lab.open_session_started_at) return;
      const started = new Date(this.lab.open_session_started_at);
      const elapsed = Math.floor((Date.now() - started.getTime()) / 1000);
      // 8-hour cap: if resumed elapsed is implausibly large (laptop sleep,
      // clock drift, zombie row that slipped past startup cleanup), treat
      // the session as abandoned rather than crediting bogus time.
      const EIGHT_HOURS = 8 * 3600;
      if (elapsed < 0 || elapsed > EIGHT_HOURS) return;
      this.sessionStart = started;
      this.elapsed = elapsed;
      this.running = true;
      this.interval = setInterval(() => this.elapsed++, 1000);
    },

    async startTimer() {
      if (this.running) return;
      this.sessionStart = new Date();
      this.elapsed = 0;
      this.running = true;
      // Persist open session immediately (duration=0 = signal for open)
      await fetch(`/api/labs/${this.lab.id}/timer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ started_at: this.sessionStart.toISOString(), duration: 0 })
      });
      // Mirror the server state locally so a page refresh right now resumes
      // via the 8-hour-capped logic in init(), not a stale list payload.
      this.lab.open_session_started_at = this.sessionStart.toISOString();
      this.interval = setInterval(() => this.elapsed++, 1000);
    },

    async stopTimer() {
      if (!this.running) return;
      clearInterval(this.interval);
      this.running = false;
      const duration = this.elapsed;
      try {
        const res  = await fetch(`/api/labs/${this.lab.id}/timer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ started_at: this.sessionStart.toISOString(), duration })
        });
        const json = await res.json();
        if (json.success) {
          this.lab.time_spent = json.data.time_spent;
          // Keep the dashboard progress bar / total-time counter live
          await Alpine.store("app").refreshSummary();
        }
      } catch (e) { console.error("Timer save failed:", e); }
      this.elapsed = 0;
      this.sessionStart = null;
      this.lab.open_session_started_at = null;
    },

    resetTimer() {
      clearInterval(this.interval);
      this.running = false;
      this.elapsed = 0;
      this.sessionStart = null;
    },

    async updateStatus() {
      try {
        await fetch(`/api/labs/${this.lab.id}/status`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: this.lab.status })
        });
        // Summary reflects done/in_progress/not_started counts — refresh
        // so the progress bar updates the moment the user picks a status.
        await Alpine.store("app").refreshSummary();
      } catch (e) { console.error("Status update failed:", e); }
    },

    async launch() {
      if (!this.lab.file_path) {
        this.showToast("⚠ Import this lab first. Go to Import page.");
        return;
      }
      try {
        const res  = await fetch(`/api/labs/${this.lab.id}/open`, { method: "POST" });
        const json = await res.json();
        this.showToast(json.success ? "✓ Opening in Packet Tracer..." : `✗ ${json.error}`);
      } catch (e) { this.showToast("✗ Network error"); }
    },

    showToast(msg) {
      this.toastMsg = msg;
      this.toast = true;
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => this.toast = false, 3500);
    },

    formatTime(s = 0) {
      const h   = Math.floor(s / 3600);
      const m   = Math.floor((s % 3600) / 60);
      const sec = s % 60;
      return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
    },

    statusLabel() {
      return { not_started:"Not Started", in_progress:"In Progress", done:"Done" }[this.lab.status] ?? "";
    },
    badgeClass() { return `badge badge--${this.lab.status}`; },
    cardClass()  {
      const base = `lab-card lab-card--${this.lab.status}`;
      return this.lab.file_path ? base : base + " lab-card--no-file";
    }
  }
}

// ── Import Page ────────────────────────────────────────────────────────────
function importPage() {
  return {
    dragging: false,
    folderPath: "",
    scanning: false,
    results: [],
    importedCount: 0,
    status: { imported_count: 0, total: 51, missing: [], imported: [] },

    async loadStatus() {
      try {
        const res  = await fetch("/api/import/status");
        const json = await res.json();
        if (json.success) this.status = json.data;
      } catch (e) { console.error("Status load failed:", e); }
    },

    async handleDrop(e) {
      this.dragging = false;
      const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith(".pka"));
      await this.uploadFiles(files);
    },

    async handleFileInput(e) {
      await this.uploadFiles(Array.from(e.target.files));
    },

    async uploadFiles(files) {
      if (!files.length) return;
      const fd = new FormData();
      files.forEach((f, i) => fd.append(`file_${i}`, f));
      try {
        const res  = await fetch("/api/import/upload", { method: "POST", body: fd });
        const json = await res.json();
        if (json.success) {
          this.results       = json.data.results;
          this.importedCount = json.data.imported_count;
          await this.loadStatus();
        }
      } catch (e) { console.error("Upload failed:", e); }
    },

    async scanFolder() {
      if (!this.folderPath.trim()) return;
      this.scanning = true;
      try {
        const res  = await fetch("/api/import/scan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ folder_path: this.folderPath.trim() })
        });
        const json = await res.json();
        if (json.success) {
          this.results       = json.data.results;
          this.importedCount = json.data.imported_count;
          await this.loadStatus();
        } else {
          alert(`Error: ${json.error}`);
        }
      } catch (e) { alert("Network error during scan."); }
      finally     { this.scanning = false; }
    }
  }
}

// ── Stats Page ─────────────────────────────────────────────────────────────
function statsPage() {
  return {
    loading: true,
    byCategory: [],
    chart: null,

    // Read summary from the shared store — gets live updates when the user
    // changes status or stops a timer on the dashboard without leaving the page.
    get summary() { return this.$store.app.summary; },

    async load() {
      this.loading = true;
      try {
        const [, catRes, slowRes] = await Promise.all([
          this.$store.app.refreshSummary(),
          fetch("/api/stats/by-category"),
          fetch("/api/stats/slowest")
        ]);
        this.byCategory = (await catRes.json()).data;
        const slowest   = (await slowRes.json()).data;
        this.loading    = false;
        // x-if unmounts the chart container while loading=true, so we must
        // wait for the next DOM tick before grabbing the canvas element.
        // $nextTick is the correct tool; the setTimeout(50) hack in v4.1
        // was a race disguised as a fix.
        await this.$nextTick();
        this.renderChart(slowest);
      } catch (e) {
        console.error("Stats load failed:", e);
        this.loading = false;
      }
    },

    renderChart(data) {
      const el = document.getElementById("timeChart");
      if (!el) return;
      if (this.chart) this.chart.destroy();
      this.chart = new Chart(el.getContext("2d"), {
        type: "bar",
        data: {
          labels: data.map(d => d.id),
          datasets: [{
            label: "Time Spent (minutes)",
            data: data.map(d => Math.round(d.time_spent / 60)),
            backgroundColor: "#049fd4",
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { stepSize: 10 } } }
        }
      });
    },

    formatTime(s = 0) {
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return h > 0 ? `${h}h ${m}m` : `${m}m`;
    }
  }
}
```

---

## 📜 Batch Files

### `start.bat`
```bat
@echo off
title CCNA Lab Tracker
color 0F
echo.
echo  ====================================
echo    CCNA Lab Tracker  v1.0
echo  ====================================
echo.

:: Check port 8080 not already in use
netstat -aon | findstr ":8080 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo  [WARN] Port 8080 is already in use.
    echo  Run stop.bat first, then try again.
    echo.
    pause & exit /b 1
)

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo  Install Python 3.11+ from https://python.org
    echo  Tick "Add Python to PATH" during install.
    echo.
    pause & exit /b 1
)

:: Install/verify deps every run. pip is idempotent and fast when everything
:: is already satisfied. The v4.1 approach (pip show robyn) only checked one
:: package — if the user uninstalled aiosqlite or aiofiles manually, start.bat
:: skipped install and python crashed with ModuleNotFoundError.
echo  [INFO] Verifying dependencies...
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [ERROR] pip install failed. Check your internet connection.
    pause & exit /b 1
)

echo  [INFO] Server starting at http://localhost:8080
echo  [INFO] Press Ctrl+C to stop.
echo.

:: Open browser after 2s delay
start /b cmd /c "timeout /t 2 >nul && start http://localhost:8080"

python app.py
pause
```

### `stop.bat`
```bat
@echo off
title Stop CCNA Lab Tracker
echo  Stopping server on port 8080...
for /f "tokens=5" %%a in (
    'netstat -aon ^| findstr ":8080 " ^| findstr "LISTENING"'
) do set PID=%%a
if not defined PID (
    echo  [INFO] No process found on port 8080.
) else (
    taskkill /PID %PID% /F >nul 2>&1
    echo  [OK] Stopped (PID: %PID%).
)
pause
```

---

## 📖 `README.md`

```markdown
# CCNA Lab Tracker

Local web app for tracking your CCNA Packet Tracer lab progress.

## Quick Start
1. Double-click `start.bat`
2. Browser opens at http://localhost:8080
3. Click **Import Labs** tab
4. Either drag & drop your .pka files, or paste folder path and click Scan
5. Return to Dashboard and start studying!

## Requirements
- Windows 10/11
- Python 3.11+ — https://python.org (tick "Add Python to PATH")
- Cisco Packet Tracer installed at default path

## Custom Packet Tracer Path
Edit `.env` and change:
```
PACKET_TRACER_EXE=C:\Your\Custom\Path\PacketTracer.exe
```

## Reset All Data
1. Stop the server (`stop.bat`)
2. Delete `database/labs.db`
3. Delete all files inside `labs_files/`
4. Run `start.bat` — re-seeds automatically

## Backup
To back up progress: copy `database/labs.db` somewhere safe.
To restore: replace `database/labs.db` with your backup.
```

---

## ⚠️ Critical Rules — Never Violate

1. **NEVER `import sqlite3`** — only `aiosqlite`. Sync DB blocks Robyn's event loop entirely.

2. **NEVER f-string SQL** — always `db.execute("... WHERE id=?", (value,))`.

3. **ALWAYS `dict(row)` before JSON return** — `aiosqlite.Row` is not JSON-serializable.

4. **`@app.shutdown_handler` must call `await close_db()`** — without this, DB connection leaks on every restart.

5. **No CORS middleware — this is same-origin.** Browser and server both live at `http://localhost:8080`, so `Access-Control-Allow-*` headers are noise and can mask real 4xx/5xx bugs during debugging. Do NOT add a CORS `after_request` handler. (v4.1 claimed this was required; that was wrong.)

6. **Pydantic v2 ONLY**: `model_validate()` not `parse_obj()`, `model_dump()` not `dict()`, `field_validator` not `validator`.

7. **`serve_directory` conflicts with manual `GET /`** — never add a route at `/` after calling `serve_directory`.

8. **SPA only — no hard navigation** — all page changes via Alpine `page=` variable only. `window.location.href` to any path other than `/` will 404.

9. **Timer `duration=0` = open session, `duration>0` = close session** — `timer_service.save_timer_session()` handles both; call it from the router, never inline the SQL.

10. **Launch button dual guard** — disabled in HTML (`:disabled="!lab.file_path"`) AND returns error in backend (`if not file_path: return error`). Both must exist.

11. **Chart.js render with `await this.$nextTick()`** — after flipping `loading=false`, wait one Alpine tick so `x-if` has mounted the `<canvas>`, then call `renderChart`. (v4.1 used `setTimeout(..., 50)` to dodge a perceived `$nextTick` issue; it was a race disguised as a fix and broke on slow machines. `$nextTick` is the correct primitive.)

12. **Multipart auto-detect** — implement both Robyn multipart patterns with `getattr` fallback. Never assume `.filename` vs `.file_name`.

13. **`labs_files/` created on startup** — `Path("labs_files").mkdir(exist_ok=True)` in `startup_handler`. Never assume it exists.

14. **`<link rel="icon" href="data:,">` in `<head>`** — prevents 404 spam in Robyn logs from browser favicon requests.

15. **Empty `__init__.py` required in every subfolder** — `routers/`, `services/`, `database/`, `models/` must each have an empty `__init__.py` or Python cannot import them as packages. This will cause `ModuleNotFoundError` immediately on startup.

16. **Alpine CDN must use `@3` not `@3.x.x`** — `@3.x.x` is not a valid semver tag on jsDelivr and will fail to load. Use `https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js`.

17. **`.env` paths use forward slashes** — always write Windows paths with `/` not `\` in `.env`. `python-dotenv` treats backslash as escape character. Example: `C:/Program Files/Cisco Packet Tracer/PacketTracer.exe`.

18. **`refresh-labs` event uses `window.dispatchEvent`** — Alpine's `$dispatch` only bubbles on the DOM element, not `window`. Use `window.dispatchEvent(new CustomEvent('refresh-labs'))` in HTML and `window.addEventListener('refresh-labs', ...)` in `appShell.init()`.

---

## ✅ Build Order

> Complete and test each phase before starting the next. Never skip a checkpoint.

### Phase 1 — Foundation
- [ ] Full folder structure created exactly as specified
- [ ] `.env`, `requirements.txt`, `README.md`
- [ ] Empty `__init__.py` in **each** of: `routers/`, `services/`, `database/`, `models/`
- [ ] `database/schema.sql`
- [ ] `database/connection.py` — `init_db()`, `get_db()`, `close_db()`
- [ ] `database/seed.py` — 51 labs, metadata only, `INSERT OR IGNORE`
- [ ] `models/schemas.py` — Pydantic v2
- [ ] `app.py` — `serve_directory`, startup/shutdown hooks (with PT_EXE path warning), register all 5 routers. **No CORS middleware** (same-origin).
- [ ] **✅ Test**: `python app.py` → DB created, 51 rows seeded, all `file_path=NULL`, server running

### Phase 2 — Core API
- [ ] `services/lab_service.py` — full implementation as specified
- [ ] `routers/labs.py`
- [ ] `services/timer_service.py` — full implementation with SQL as specified
- [ ] `routers/progress.py`
- [ ] `services/pt_launcher.py`
- [ ] `routers/launcher.py`
- [ ] `routers/stats.py` — full SQL as specified
- [ ] **✅ Test**: `curl http://localhost:8080/api/labs` → 51 labs, all `file_path: null`
- [ ] **✅ Test**: `curl http://localhost:8080/api/stats/summary` → correct counts

### Phase 3 — Import System
- [ ] `services/file_importer.py` — `extract_lab_id`, `import_from_bytes`, `import_single_file`, `import_from_folder`
- [ ] `routers/importer.py` — both multipart patterns, `/upload`, `/scan`, `/status`
- [ ] **✅ Test**: POST to `/api/import/scan` with folder path → files in `labs_files/`, DB updated
- [ ] **✅ Test**: POST multipart to `/api/import/upload` → single file imported correctly

### Phase 4 — Frontend
- [ ] `public/style.css` — full skeleton as specified (all CSS classes must exist)
- [ ] `public/index.html` — CDN order (Chart.js first, Alpine last with defer)
- [ ] `public/app.js` — `appShell`, `labCard`, `importPage`, `statsPage`
- [ ] **✅ Test checklist**:
  - [ ] All 51 cards render with correct status badges
  - [ ] Filter by category works
  - [ ] Search by name/ID works
  - [ ] Timer starts, counts, persists after browser refresh, stops and saves
  - [ ] Status dropdown updates and persists
  - [ ] Launch button disabled for unimported labs
  - [ ] Import drag & drop produces results list
  - [ ] Import folder scan produces results list
  - [ ] Launch button enabled after import, opens Packet Tracer
  - [ ] Analytics chart renders (no blank canvas)
  - [ ] Category bars render with correct widths

### Phase 5 — Batch Scripts
- [ ] `start.bat` — port check, Python check, pip check, browser open, run server
- [ ] `stop.bat` — netstat + taskkill
- [ ] **✅ Test**: cold double-click start.bat → browser opens → import → track → stop.bat kills server

---

*This prompt is fully self-contained. An AI assistant with zero prior context should be able to build the complete, working application from this document alone.*
