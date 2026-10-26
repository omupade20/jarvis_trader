@echo off
title JARVIS Neural Swing Sentinel
cd /d %~dp0
echo.
echo ============================================================
echo   JARVIS NEURAL SWING SENTINEL // STARTING...
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

echo [1/3] Clearing previous port 5000 bindings...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo [2/3] Checking dependencies...
pip install fastapi uvicorn python-dotenv requests yfinance edge-tts jinja2 python-multipart pandas numpy -q --disable-pip-version-check

echo [3/3] Starting server on http://localhost:5000
echo.
echo ============================================================
echo   Open your browser: http://localhost:5000
echo   Press CTRL+C to stop JARVIS
echo ============================================================
echo.

python app.py

pause
