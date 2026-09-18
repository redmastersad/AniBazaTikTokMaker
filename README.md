# TikTok AI Video Generator

A fully automated local AI pipeline for creating short vertical videos (TikTok, YouTube Shorts, Reels) from long video files.

Provide a long video, and the system will output a collection of vertical 9:16 videos featuring integrated subtitles, background blur, and optimal cropping.

## Features
* **Full Autonomy:** Operates locally without requiring API keys, subscriptions, or recurring costs.
* **AI Director:** Utilizes `Llama 3.1` (Ollama) to identify the most engaging, significant, or dramatic moments within the footage.
* **High-Precision Transcription:** Employs `faster-whisper (large-v3)` on the GPU for accurate speech-to-text conversion (including silence filtering).
* **Cinematic Subtitles:** Hardcodes modern subtitles (Segoe UI Black font, black outline) directly onto the video stream.
* **Vertical Format (9:16):** Automatically blurs the background and centers the original video, scaling it appropriately.
* **Watermarks and Logos:** Supports overlaying a custom PNG logo onto the final output.
* **Telegram Bot Integration:** Includes the source code for a Telegram bot, allowing users to send videos from mobile devices for remote processing on the host machine.

## System Requirements
- **OS:** Windows 10/11
- **GPU:** NVIDIA Graphics Card (6 GB VRAM minimum recommended for CUDA). The software will fallback to the CPU if no suitable GPU is detected, resulting in significantly increased processing times.
- **Dependencies:** **Python 3.9+** and **FFmpeg** must be installed on the system.

## Installation (Windows)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/tiktok-ai-generator.git
   cd tiktok-ai-generator
   ```

2. **Install prerequisite software:**
   - Download and install [Ollama](https://ollama.com/) (required for the AI Director module).
   - Ensure `FFmpeg` is installed and added to the system `PATH` environment variable.

3. **Automated Setup:**
   Execute the `install.bat` file. 
   This script creates a virtual environment, downloads the necessary neural network models, installs CUDA dependencies, and configures the environment.

## Usage

**Method 1 (Desktop GUI):**
Launch `run_tiktok_ai.bat`.
The application window will open. Select the source video file (e.g., a podcast or recording), specify the output directory, and optionally select a PNG logo. Initiate the process and wait for completion.

**Method 2 (Telegram Bot):**
1. Obtain a bot token from `@BotFather` on Telegram.
2. Open `bot.py` and assign the token to the `TOKEN` variable: `TOKEN = "YOUR_BOT_TOKEN"`.
3. Launch `run_bot.bat`.
4. Send video files directly to the bot via Telegram chat.

## Technical Stack
- `faster-whisper` + `Silero VAD`
- `Ollama` (`Llama 3.1 8B`)
- `ffmpeg-python`
- `customtkinter` (UI)
