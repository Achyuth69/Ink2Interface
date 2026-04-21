@echo off
setlocal EnableDelayedExpansion
title Ink2Interface

:: ── Docker mode ───────────────────────────────────────────────────────────────
if "%1"=="--docker" (
    echo [Ink2Interface] Starting with Docker...
    docker --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Docker not found. Install from https://docker.com
        pause & exit /b 1
    )
    docker compose up --build -d
    echo.
    echo  App running at http://localhost:80
    echo  API running at http://localhost:8080
    echo.
    echo  Logs: docker compose logs -f
    echo  Stop: docker compose down
    pause
    exit /b 0
)

:: ── Dev mode ──────────────────────────────────────────────────────────────────
echo.
echo  Starting Ink2Interface (dev mode)...
echo  Backend  ^-^> http://localhost:8080
echo  Frontend ^-^> http://localhost:5173
echo.

:: Check .env
if not exist "backend\.env" (
    echo [ERROR] backend\.env not found. Run setup.bat first.
    pause & exit /b 1
)

:: Start backend in new window
start "Ink2Interface Backend" cmd /k "cd /d %~dp0backend && python main.py"

:: Wait 3s for backend to start
timeout /t 3 /nobreak >nul

:: Start frontend in new window
start "Ink2Interface Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo  Both servers started in separate windows.
echo  Open http://localhost:5173 in your browser.
echo.
pause
