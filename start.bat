@echo off
title CCNA Lab Tracker
color 0F
echo.
echo  =====================================================
echo    CCNA Lab Tracker v4.2
echo  =====================================================
echo.

:: Read PORT from .env (falls back to 8080). Must mirror app.py's default.
set "PORT=8080"
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="PORT" set "PORT=%%B"
    )
)

:: Check port not already in use
netstat -aon | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo  [WARN] Port %PORT% is already in use.
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

echo.

:: Open browser after 2s delay
start /b cmd /c "timeout /t 2 >nul && start http://localhost:%PORT%"

python app.py
pause
