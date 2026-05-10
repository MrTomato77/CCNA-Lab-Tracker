import os
import subprocess
import sys
from pathlib import Path
from loguru import logger

# `load_dotenv()` is called once in app.py before this module is imported.
PT_EXE = os.getenv("PACKET_TRACER_EXE", r"C:\Program Files\Cisco Packet Tracer\PacketTracer.exe")

# lab_id -> Popen handle. Kept in-memory only; on server restart the PT
# instances become orphaned and the user closes them manually. The dict
# is a convenience for the /close route, not a source of truth.
_pt_processes: dict[str, subprocess.Popen] = {}


def _maximized_startupinfo():
    """Windows: ask the shell to open the new window maximized.
    On non-Windows this returns None and Popen ignores the arg."""
    if sys.platform != "win32":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags    |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 3   # SW_SHOWMAXIMIZED
    return si


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
        process = subprocess.Popen(
            [str(pt), str(pka)],
            shell=False,
            startupinfo=_maximized_startupinfo(),
        )
        _pt_processes[lab_id] = process
        logger.bind(name="app").info(f"Launched {pka.name} with PID {process.pid}")
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
