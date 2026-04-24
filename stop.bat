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
