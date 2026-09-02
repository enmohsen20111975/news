@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

echo 🔧 Checking Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python not found on PATH
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo 📁 Creating virtual environment...
    python -m venv .venv
)

echo 📦 Installing dependencies...
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

if not exist ".env" (
    echo ⚠️  .env not found — copying from .env.example
    copy .env.example .env >nul
    echo ✏️  Open .env and configure settings, then run again
    pause
    exit /b 1
)

echo 🤖 Checking Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️  Ollama is not responding — start Ollama and try again
    pause
    exit /b 1
)

echo ✅ All set!
echo 🚀 Starting News Agent...
.venv\Scripts\python.exe main.py %*
exit /b %errorlevel%
