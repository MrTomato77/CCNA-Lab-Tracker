import ctypes
import os
import subprocess  # nosec B404  — shell=False throughout
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path
from loguru import logger

PT_EXE = os.getenv("PACKET_TRACER_EXE", r"C:\Program Files\Cisco Packet Tracer\PacketTracer.exe")

# lab_id → Popen handle. In-memory only; orphaned on restart — a convenience
# for the /close route, not a source of truth.
_pt_processes: dict[str, subprocess.Popen] = {}
_pt_lock = threading.Lock()

# Win32 constants for post-launch maximize.
_SW_MAXIMIZE   = 3
_GW_OWNER      = 4
_MAX_WAIT_SEC  = 60.0
_POLL_INTERVAL = 0.2


def _drop_exited_locked() -> None:
    for tracked_lab_id, process in list(_pt_processes.items()):
        if process.poll() is not None:
            _pt_processes.pop(tracked_lab_id, None)


def _maximize_after_launch(pid: int) -> None:
    """Poll for the PT main window then ShowWindow(maximize) on a daemon thread.

    PT is a Qt app and ignores STARTUPINFO.nCmdShow — ShowWindow on the live
    HWND is the only mechanism that takes effect.
    """
    if sys.platform != "win32":
        return

    user32 = ctypes.windll.user32
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _try_once() -> int:
        hits: list[int] = []

        def cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            owner_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
            if owner_pid.value != pid:
                return True
            # Skip the splash screen (no title) and any owned dialogs
            # (tooltips, log popups) that share PT's PID.
            if user32.GetWindowTextLengthW(hwnd) <= 0:
                return True
            if user32.GetWindow(hwnd, _GW_OWNER) != 0:
                return True
            hits.append(hwnd)
            return False

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        return hits[0] if hits else 0

    deadline = time.monotonic() + _MAX_WAIT_SEC
    while time.monotonic() < deadline:
        hwnd = _try_once()
        if hwnd:
            user32.ShowWindow(hwnd, _SW_MAXIMIZE)
            logger.bind(name="app").info(
                f"maximized PT window for PID {pid} (hwnd 0x{hwnd:x})"
            )
            return
        time.sleep(_POLL_INTERVAL)

    logger.bind(name="app").warning(
        f"PT window for PID {pid} did not appear within {_MAX_WAIT_SEC}s; skipping maximize"
    )


def _spawn_maximize_thread(pid: int) -> None:
    if sys.platform != "win32":
        return
    threading.Thread(
        target=_maximize_after_launch,
        args=(pid,),
        name=f"pt-maximize-{pid}",
        daemon=True,
    ).start()


LABS_DIR = Path(__file__).resolve().parent.parent / "labs"


async def _materialize_pka(lab_id: str, dest: Path) -> bool:
    """Write the lab's .pka bytes from the assets table to *dest*.

    The DB is the source of truth; Packet Tracer needs a real file on disk, so
    we extract on demand into labs/ and launch from there. Returns False if the
    lab has no stored .pka.
    """
    from database.connection import get_db
    db = await get_db()
    async with db.execute(
        "SELECT bytes FROM assets WHERE kind='pka' AND name=?",
        (f"{lab_id}.pka",),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(bytes(row["bytes"]))
    return True


async def launch_pka(lab_id: str, file_path: str | None) -> dict:
    # file_path is now an availability marker (set by the asset sync), not a real
    # path — the bytes live in the DB. None means the lab was never imported.
    if not file_path:
        return {"success": False,
                "error": "This lab hasn't been imported yet.",
                "code": "NO_FILE_IMPORTED"}

    pka = LABS_DIR / f"{lab_id}.pka"
    pt  = Path(PT_EXE)

    if not pka.exists() and not await _materialize_pka(lab_id, pka):
        return {"success": False,
                "error": "This lab's .pka isn't in the database. Re-bundle assets.",
                "code": "PKA_NOT_FOUND"}

    if not pt.exists():
        return {"success": False,
                "error": f"Packet Tracer not found at: {PT_EXE}. Edit PACKET_TRACER_EXE in .env.",
                "code": "PT_NOT_FOUND"}

    try:
        with _pt_lock:
            _drop_exited_locked()
            prior = _pt_processes.pop(lab_id, None)
        if prior and prior.poll() is None:
            logger.bind(name="app").info(
                f"replacing tracked PT for {lab_id} (PID {prior.pid})"
            )
        process = subprocess.Popen([str(pt), str(pka)], shell=False)  # nosec B603
        with _pt_lock:
            _drop_exited_locked()
            _pt_processes[lab_id] = process
        logger.bind(name="app").info(f"Launched {pka.name} with PID {process.pid}")
        _spawn_maximize_thread(process.pid)
        return {"success": True}
    except FileNotFoundError as e:
        logger.bind(name="app").error(f"File not found: {e}")
        return {"success": False, "error": f"File not found: {str(e)}", "code": "FILE_NOT_FOUND"}
    except PermissionError as e:
        logger.bind(name="app").error(f"Permission denied: {e}")
        return {"success": False, "error": "Permission denied launching Packet Tracer.",
                "code": "PT_PERMISSION_ERROR"}
    except Exception:
        logger.bind(name="app").exception("Unexpected Packet Tracer launch error")
        return {"success": False, "error": "An internal error occurred.",
                "code": "PT_UNKNOWN_ERROR"}


def terminate_pt(lab_id: str) -> dict:
    """Kill the tracked PT process without triggering its Save dialog.
    Idempotent — returns success with a code if the process is already gone."""
    with _pt_lock:
        _drop_exited_locked()
        process = _pt_processes.pop(lab_id, None)
    if process is None:
        return {"success": True, "code": "NO_PROCESS"}
    if process.poll() is not None:
        return {"success": True, "code": "ALREADY_EXITED"}
    try:
        process.terminate()  # Windows: TerminateProcess; POSIX: SIGTERM
        logger.bind(name="app").info(f"terminated PT for {lab_id} (PID {process.pid})")
        return {"success": True, "code": "TERMINATED"}
    except Exception:
        logger.bind(name="app").exception("Unexpected Packet Tracer terminate error")
        return {"success": False, "error": "An internal error occurred.",
                "code": "TERMINATE_FAILED"}
