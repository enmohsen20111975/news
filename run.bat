@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

echo Checking Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found on PATH
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Checking dependencies...
.venv\Scripts\python.exe -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing dependencies...
    .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
    .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
) else (
    echo Dependencies already installed
)

if not exist ".env" (
    echo .env not found -- copying from .env.example
    copy .env.example .env >nul
    echo Open .env and configure settings, then run again
    pause
    exit /b 1
)

echo Checking Ollama...
curl.exe -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo Ollama is not responding -- start Ollama and try again
    pause
    exit /b 1
)

echo Starting dashboard on http://localhost:8001 ...
start "NewsAgent Dashboard" /b .venv\Scripts\python.exe -m uvicorn ui.dashboard:app --host 0.0.0.0 --port 8001

timeout /t 3 /nobreak >nul

echo Starting News Agent...
.venv\Scripts\python.exe main.py %*
exit /b %errorlevel%
