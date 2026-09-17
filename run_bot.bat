@echo off
cd /d "%~dp0"
call .\venv\Scripts\activate.bat
echo Откройте файл bot.py и вставьте свой токен вместо YOUR_BOT_TOKEN
echo Запуск бота...
python bot.py
pause
