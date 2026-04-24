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
PACKET_TRACER_EXE=C:/Your/Custom/Path/PacketTracer.exe
```

Note: Use forward slashes `/` not backslashes `\`.

## Reset All Data

1. Stop the server (`stop.bat`)
2. Delete `database/labs.db`
3. Delete all files inside `labs_files/`
4. Run `start.bat` — re-seeds automatically

## Backup

To back up progress: copy `database/labs.db` somewhere safe.
To restore: replace `database/labs.db` with your backup.
