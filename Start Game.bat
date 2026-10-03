@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo The project virtual environment was not found.
    echo Run setup with: python -m venv .venv ^&^& .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "main_game.py"
if errorlevel 1 (
    echo.
    echo The game stopped because of a startup error. Check the message above.
    pause
)

endlocal
