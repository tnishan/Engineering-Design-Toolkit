@echo off
setlocal

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo Starting Engineering Design Toolkit...
echo.

REM --- Backend (FastAPI / uvicorn on port 8010) ---
start "Beam Toolkit - Backend" cmd /k "cd /d "%ROOT%\backend" && .venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8010 --reload"

REM --- Frontend (Vite dev server on port 5173) ---
start "Beam Toolkit - Frontend" cmd /k "cd /d "%ROOT%\frontend" && npm run dev"

echo Waiting for the servers to come up...
timeout /t 6 /nobreak >nul

start "" "http://localhost:5173"

endlocal
