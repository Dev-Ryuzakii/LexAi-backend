@echo off
REM Local development start-up on Windows: venv, migrations, dev server.
cd /d "%~dp0"

if not exist venv (
    python -m venv venv
    venv\Scripts\pip install -r requirements-dev.txt
)
call venv\Scripts\activate.bat

if not exist data mkdir data
if not exist logs mkdir logs
alembic upgrade head || exit /b 1
python src\app_api.py
