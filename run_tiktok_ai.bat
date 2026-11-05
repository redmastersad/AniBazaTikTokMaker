@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo venv not found. Run install.bat first.
    pause
    exit /b
)
if not exist "_tmp" mkdir "_tmp"
"venv\Scripts\python.exe" -c "import webview" >nul 2>&1
if errorlevel 1 (
    echo Installing the window component pywebview...
    "venv\Scripts\python.exe" -m pip install "pywebview>=5.3"
    "venv\Scripts\python.exe" -c "import webview" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo pywebview did not install, the error is above. Send a screenshot of this window.
        echo The app will now open in a separate Edge window instead.
        pause
    )
)
start "" "venv\Scripts\pythonw.exe" app.py
