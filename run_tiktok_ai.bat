@echo off
cd /d "%~dp0"
call .\venv\Scripts\activate.bat
python -c "import webview" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing the new window component pywebview...
    pip install "pywebview>=5.3"
)
start "" pythonw app.py
