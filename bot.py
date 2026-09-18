import os
import telebot
from telebot.types import Message
from main import process_video

# Replace 'YOUR_BOT_TOKEN' with the token from BotFather
TOKEN = "YOUR_BOT_TOKEN"
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start_cmd(message: Message):
    bot.reply_to(
        message, 
        "Hello. I am the AI TikTok Generator. Send me a video (as a document or video file), "
        "and I will analyze it for interesting moments, add subtitles, and return vertical 9:16 videos."
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

        # Telegram bot API limits files to 20 MB without a local server
        if file_size and file_size > 20 * 1024 * 1024:
            bot.reply_to(message, "Video is too large. Telegram API limit is 20 MB.")
            return

        msg = bot.reply_to(message, "Downloading video...")
        
        # Get file from Telegram
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Create user directory
        user_dir = os.path.join("bot_sessions", str(message.chat.id))
        os.makedirs(user_dir, exist_ok=True)
        
        input_path = os.path.join(user_dir, file_name)
        output_dir = os.path.join(user_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        with open(input_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.edit_message_text(
            "Starting AI analysis and processing. (This may take 5-10 minutes depending on hardware performance)", 
            chat_id=message.chat.id, 
            message_id=msg.message_id
        )

        # Run main logic
        generated_files = process_video(input_path, output_dir)

        if not generated_files:
            bot.edit_message_text(
                "The AI could not identify highly engaging moments in this video. It may lack sufficient dialogue.",
                chat_id=message.chat.id, 
                message_id=msg.message_id
            )
        else:
            bot.edit_message_text(
                f"Found {len(generated_files)} viral moments. Sending files...",
                chat_id=message.chat.id, 
                message_id=msg.message_id
            )
            
            # Send generated files to the user
            for fpath in generated_files:
                if os.path.exists(fpath):
                    with open(fpath, 'rb') as video_file:
                        bot.send_video(message.chat.id, video_file)

        # Cleanup original file (optional)
        if os.path.exists(input_path):
            os.remove(input_path)

    except Exception as e:
        bot.send_message(message.chat.id, f"An error occurred: {str(e)}")

if __name__ == "__main__":
    print("Bot started. Waiting for messages...")
    bot.infinity_polling()
