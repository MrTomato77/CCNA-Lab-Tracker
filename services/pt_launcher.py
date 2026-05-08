import os
import subprocess
from pathlib import Path
from loguru import logger

# `load_dotenv()` is called once in app.py before this module is imported.
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
        # Try to launch Packet Tracer
        process = subprocess.Popen([str(pt), str(pka)], shell=False)
        logger.info(f"Launched {pka.name} with PID {process.pid}")
        return {"success": True}
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return {"success": False, "error": f"File not found: {str(e)}", "code": "FILE_NOT_FOUND"}
    except PermissionError as e:
        logger.error(f"Permission denied: {e}")
        return {"success": False, "error": "Permission denied launching Packet Tracer.",
                "code": "PT_PERMISSION_ERROR"}
    except Exception as e:
        logger.error(f"Launch error: {e}")
        return {"success": False, "error": str(e), "code": "PT_UNKNOWN_ERROR"}
