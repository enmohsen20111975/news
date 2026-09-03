@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

:loop
.venv\Scripts\python.exe collectors/scrappers/investing_scraper.py
timeout /t 3600 >nul
goto loop
