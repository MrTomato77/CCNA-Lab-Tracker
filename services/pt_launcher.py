import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path
from loguru import logger

# `load_dotenv()` is called once in app.py before this module is imported.
PT_EXE = os.getenv("PACKET_TRACER_EXE", r"C:\Program Files\Cisco Packet Tracer\PacketTracer.exe")

# lab_id -> Popen handle. Kept in-memory only; on server restart the PT
# instances become orphaned and the user closes them manually. The dict
# is a convenience for the /close route, not a source of truth.
_pt_processes: dict[str, subprocess.Popen] = {}


# Win32 constants for the post-launch maximize. PT is a Qt app and Qt
# ignores STARTUPINFO.wShowWindow / nCmdShow — the only mechanism that
# actually takes effect is calling ShowWindow on the live HWND once the
# main window is visible.
_SW_MAXIMIZE   = 3
_GW_OWNER      = 4
_MAX_WAIT_SEC  = 60.0
_POLL_INTERVAL = 0.2


def _maximize_after_launch(pid: int) -> None:
    """Poll top-level windows for one owned by `pid`, then ShowWindow it
    maximized. Runs on a daemon thread so launch_pka can return.

    Why this and not STARTUPINFO: PT is a Qt app and Qt ignores the
    nCmdShow hint passed via STARTUPINFO. Setting the window state
    after the window exists is the only mechanism that takes effect.
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
            return False  # stop enumerating

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


async def launch_pka(lab_id: str, file_path: str | None) -> dict:
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
        # Replace any prior tracked instance for this lab — relaunching
        # without stopping should not leak the old handle.
        prior = _pt_processes.pop(lab_id, None)
        if prior and prior.poll() is None:
            logger.bind(name="app").info(
                f"replacing tracked PT for {lab_id} (PID {prior.pid})"
            )
        process = subprocess.Popen([str(pt), str(pka)], shell=False)
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
    except Exception as e:
        logger.bind(name="app").error(f"Launch error: {e}")
        return {"success": False, "error": str(e), "code": "PT_UNKNOWN_ERROR"}


def terminate_pt(lab_id: str) -> dict:
    """Kill the tracked PT process for this lab without giving PT a chance
    to show its 'Save changes?' dialog. Idempotent: if the process already
    exited or was never tracked, returns success with a code so the
    caller can log/ignore."""
    process = _pt_processes.pop(lab_id, None)
    if process is None:
        return {"success": True, "code": "NO_PROCESS"}
    if process.poll() is not None:
        return {"success": True, "code": "ALREADY_EXITED"}
    try:
        # On Windows, terminate() = TerminateProcess (no save dialog).
        # On POSIX, terminate() = SIGTERM. Both bypass PT's UI prompt.
        process.terminate()
        logger.bind(name="app").info(f"terminated PT for {lab_id} (PID {process.pid})")
        return {"success": True, "code": "TERMINATED"}
    except Exception as e:
        logger.bind(name="app").error(f"PT terminate failed: {e}")
        return {"success": False, "error": str(e), "code": "TERMINATE_FAILED"}
