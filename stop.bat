@echo off
title Stop CCNA Lab Tracker

:: Read PORT from .env (falls back to 8080). Must mirror app.py's default.
set "PORT=8080"
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="PORT" set "PORT=%%B"
    )
)

echo  Stopping server on port %PORT%...
for /f "tokens=5" %%a in (
    'netstat -aon ^| findstr ":%PORT% " ^| findstr "LISTENING"'
) do set PID=%%a
if not defined PID (
    echo  [INFO] No process found on port %PORT%.
) else (
    taskkill /PID %PID% /F >nul 2>&1
    echo  [OK] Stopped (PID: %PID%).
)
pause
