@echo off
setlocal

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo =======================================================
echo Starting Engineering Design Toolkit
echo =======================================================
echo.

REM Determine Python executable
if exist "%ROOT%\backend\.venv\Scripts\python.exe" (
    set "PYTHON=%ROOT%\backend\.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

REM Build frontend dist if not already built so FastAPI can serve the full website
if not exist "%ROOT%\frontend\dist\index.html" (
    echo Building frontend static website...
    cd /d "%ROOT%\frontend" && call npm run build
    cd /d "%ROOT%"
)

REM --- Launch Backend (FastAPI serving API & Web App on port 8010) ---
echo Launching Web Server (http://localhost:8010)...
start /B "Web Application" cmd /c "cd /d "%ROOT%\backend" && "%PYTHON%" -m uvicorn api.main:app --host 127.0.0.1 --port 8010 --reload"

echo.
echo Waiting for web server to initialize...
timeout /t 3 /nobreak >nul

echo Opening website at http://localhost:8010...
start "" "http://localhost:8010"

echo.
echo =======================================================
echo  Web Application running at: http://localhost:8010
echo  Press Ctrl+C or close this window to stop the server.
echo =======================================================
echo.

pause >nul
endlocal
