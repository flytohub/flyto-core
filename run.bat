@echo off
REM Flyto Core - Workflow Runner (Windows)
REM Usage: run.bat workflow.yaml

cd /d "%~dp0"

REM Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Python is required
    exit /b 1
)

REM Install dependencies if needed
if not exist ".deps_installed" (
    echo Installing dependencies...
    pip install -r requirements.txt
    echo. > .deps_installed
)

REM Run
python run.py %*
