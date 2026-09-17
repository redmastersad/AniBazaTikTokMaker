@echo off
cd /d "%~dp0"
call .\venv\Scripts\activate.bat
python youtube_uploader_gui.py
