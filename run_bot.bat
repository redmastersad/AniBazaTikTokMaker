@echo off
cd /d "%~dp0"
call .\venv\Scripts\activate.bat
echo Open bot.py and replace YOUR_BOT_TOKEN with your actual token
echo Starting bot...
python bot.py
pause
