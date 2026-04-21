@echo off
echo [Ink2Interface] Stopping all services...

:: Kill Python backend
taskkill /f /fi "WINDOWTITLE eq Ink2Interface Backend*" >nul 2>&1
taskkill /f /im python.exe /fi "WINDOWTITLE eq Ink2Interface*" >nul 2>&1

:: Kill Node frontend
taskkill /f /fi "WINDOWTITLE eq Ink2Interface Frontend*" >nul 2>&1

:: Docker mode
docker compose down >nul 2>&1

echo [OK] All services stopped.
pause
