import os
import telebot
from telebot.types import Message
from main import process_video

# Замените 'YOUR_BOT_TOKEN' на токен от BotFather
TOKEN = "YOUR_BOT_TOKEN"
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start_cmd(message: Message):
    bot.reply_to(
        message, 
        "Привет! Я ИИ-генератор TikTok. Отправь мне видео (как документ или видеофайл), "
        "а я найду в нем интересные моменты, добавлю крутые субтитры и пришлю готовые ролики 9:16!"
    )

@bot.message_handler(content_types=['video', 'document'])
def handle_video(message: Message):
    try:
        if message.content_type == 'video':
            file_id = message.video.file_id
            file_name = getattr(message.video, 'file_name', f'video_{message.message_id}.mp4')
            file_size = message.video.file_size
        else:
            file_id = message.document.file_id
            file_name = getattr(message.document, 'file_name', f'document_{message.message_id}.mp4')
            file_size = message.document.file_size

        # Telegram bot API без локального сервера ограничивает файлы до 20 МБ
        if file_size and file_size > 20 * 1024 * 1024:
            bot.reply_to(message, "❌ Видео слишком большое! Ограничение Telegram — 20 МБ.")
            return

        msg = bot.reply_to(message, "📥 Скачиваю видео...")
        
        # Получаем файл от Telegram
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Создаем папку для пользователя
        user_dir = os.path.join("bot_sessions", str(message.chat.id))
        os.makedirs(user_dir, exist_ok=True)
        
        input_path = os.path.join(user_dir, file_name)
        output_dir = os.path.join(user_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        with open(input_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.edit_message_text(
            "🤖 Начинаю ИИ-анализ и нарезку! (Это может занять 5-10 минут в зависимости от мощности компьютера)", 
            chat_id=message.chat.id, 
            message_id=msg.message_id
        )

        # Запускаем нашу логику из main.py
        generated_files = process_video(input_path, output_dir)

        if not generated_files:
            bot.edit_message_text(
                "😔 ИИ не смог найти ничего интересного в этом видео. Возможно, там мало диалогов.",
                chat_id=message.chat.id, 
                message_id=msg.message_id
            )
        else:
            bot.edit_message_text(
                f"✅ Найдено {len(generated_files)} вирусных моментов! Отправляю...",
                chat_id=message.chat.id, 
                message_id=msg.message_id
            )
            
            # Отправляем готовые файлы пользователю
            for fpath in generated_files:
                if os.path.exists(fpath):
                    with open(fpath, 'rb') as video_file:
                        bot.send_video(message.chat.id, video_file)

        # Очистка исходного файла (опционально)
        if os.path.exists(input_path):
            os.remove(input_path)

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Произошла ошибка: {str(e)}")

if __name__ == "__main__":
    print("🤖 Бот запущен! Ожидаю сообщений...")
    bot.infinity_polling()
