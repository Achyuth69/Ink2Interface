@echo off
setlocal EnableDelayedExpansion
title Ink2Interface Setup

echo.
echo  ██╗███╗   ██╗██╗  ██╗██████╗ ██╗███╗   ██╗████████╗███████╗██████╗ ███████╗ █████╗  ██████╗███████╗
echo  ██║████╗  ██║██║ ██╔╝╚════██╗██║████╗  ██║╚══██╔══╝██╔════╝██╔══██╗██╔════╝██╔══██╗██╔════╝██╔════╝
echo  ██║██╔██╗ ██║█████╔╝  █████╔╝██║██╔██╗ ██║   ██║   █████╗  ██████╔╝█████╗  ███████║██║     █████╗
echo  ██║██║╚██╗██║██╔═██╗ ██╔═══╝ ██║██║╚██╗██║   ██║   ██╔══╝  ██╔══██╗██╔══╝  ██╔══██║██║     ██╔══╝
echo  ██║██║ ╚████║██║  ██╗███████╗██║██║ ╚████║   ██║   ███████╗██║  ██║██║     ██║  ██║╚██████╗███████╗
echo  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝
echo.
echo  Screenshot to Frontend Code Generator
echo  ========================================
echo.

:: ── Check prerequisites ───────────────────────────────────────────────────────
echo [1/5] Checking prerequisites...

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install from https://python.org
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER%

node --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Node.js not found. Install from https://nodejs.org
    pause & exit /b 1
)
for /f %%v in ('node --version') do set NODEVER=%%v
echo  [OK] Node.js %NODEVER%

:: ── Setup .env ────────────────────────────────────────────────────────────────
echo.
echo [2/5] Configuring environment...

if not exist "backend\.env" (
    copy "backend\.env.example" "backend\.env" >nul
    echo  [OK] Created backend\.env from template
    echo.
    echo  *** ACTION REQUIRED ***
    echo  Open backend\.env and set your GROQ_API_KEY
    echo  Get a free key at: https://console.groq.com
    echo.
    set /p GROQ_KEY="  Paste your Groq API key now (or press Enter to set it later): "
    if not "!GROQ_KEY!"=="" (
        powershell -Command "(Get-Content 'backend\.env') -replace 'GROQ_API_KEY=gsk_\.\.\.', 'GROQ_API_KEY=!GROQ_KEY!' | Set-Content 'backend\.env'"
        echo  [OK] GROQ_API_KEY saved
    )
) else (
    echo  [OK] backend\.env already exists
)

:: ── Install backend deps ──────────────────────────────────────────────────────
echo.
echo [3/5] Installing backend dependencies...
pip install -r backend\requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] pip install failed
    pause & exit /b 1
)
echo  [OK] Backend dependencies installed

:: ── Install frontend deps ─────────────────────────────────────────────────────
echo.
echo [4/5] Installing frontend dependencies...
cd frontend
npm install --silent
if errorlevel 1 (
    echo  [ERROR] npm install failed
    cd ..
    pause & exit /b 1
)
cd ..
echo  [OK] Frontend dependencies installed

:: ── Build frontend ────────────────────────────────────────────────────────────
echo.
echo [5/5] Building frontend for production...
cd frontend
npm run build
if errorlevel 1 (
    echo  [ERROR] Frontend build failed
    cd ..
    pause & exit /b 1
)
cd ..
echo  [OK] Frontend built to frontend\dist\

:: ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo  ========================================
echo   Setup complete!
echo  ========================================
echo.
echo  To start the app:
echo.
echo    start.bat          ^<-- starts both backend + frontend
echo    start.bat --docker ^<-- starts with Docker (production)
echo.
echo  Or manually:
echo    Terminal 1:  cd backend ^&^& python main.py
echo    Terminal 2:  cd frontend ^&^& npm run dev
echo.
echo  App will be at: http://localhost:3000
echo.
pause
