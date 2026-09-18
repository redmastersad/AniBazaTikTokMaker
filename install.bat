@echo off
cd /d "%~dp0"
echo Installing TikTok AI Generator

echo 1. Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed! Download it from python.org and check "Add Python to PATH" during installation.
    pause
    exit /b
)

echo 2. Creating virtual environment...
python -m venv venv
call .\venv\Scripts\activate.bat

echo 3. Installing dependencies (this may take 5-10 minutes)...
pip install -r requirements.txt

echo 4. Setting up Ollama...
echo Make sure you have Ollama downloaded and installed from ollama.com!
echo If Ollama is already installed, the program will download the necessary model (Llama 3.1) on first run.

echo.
echo DONE!
echo You can now launch the program via: run_tiktok_ai.bat (or the Desktop Shortcut)
pause
