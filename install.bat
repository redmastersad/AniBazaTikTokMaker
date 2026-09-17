@echo off
echo =======================================
echo Установка TikTok AI Generator
echo =======================================

echo 1. Проверяем наличие Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не установлен! Скачайте его с python.org и при установке поставьте галочку "Add Python to PATH".
    pause
    exit /b
)

echo 2. Создаем виртуальное окружение...
python -m venv venv

echo 3. Устанавливаем библиотеки (это может занять 5-10 минут)...
call .\venv\Scripts\activate.bat
pip install -r requirements.txt

echo 4. Скачиваем Ollama...
echo Убедитесь, что у вас скачан и установлен Ollama с сайта ollama.com!
echo Если Ollama уже установлена, программа скачает нужную нейросеть (Llama 3.1) при первом запуске.
ollama pull llama3.1

echo.
echo =======================================
echo ГОТОВО! 
echo Теперь вы можете запускать программу через файл: run_tiktok_ai.bat (или Ярлык на рабочем столе)
echo =======================================
pause
