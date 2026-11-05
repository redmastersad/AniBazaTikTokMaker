@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo venv not found. Run install.bat first.
    pause
    exit /b
)
"venv\Scripts\python.exe" tiktok_folder_upload.py %*
pause
