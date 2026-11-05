# AniBaza TikTok AI Video Generator

**EXCLUSIVELY DEVELOPED FOR ANIBAZA**

A fully automated local AI pipeline for creating short vertical videos (TikTok, YouTube Shorts, Reels) from long video files, tailored specifically for the AniBaza team workflows.

Provide a long video, and the system will output a collection of vertical 9:16 videos featuring integrated subtitles, background blur, and optimal cropping.

## Fonts
Subtitle fonts are bundled in `Assets/Fonts` (Montserrat Black, Russo One, Rubik Mono One, Unbounded, all under the SIL Open Font License) and are embedded into the clips by FFmpeg, so nothing has to be installed in Windows. Custom `.ttf`/`.otf` fonts can be added from the app.

## Features
* **AniBaza Custom AI Director:** Utilizes `Llama 3.1` (Ollama) to identify the most engaging, significant, or dramatic moments within the footage.
* **Full Autonomy:** Operates locally without requiring API keys, subscriptions, or recurring costs.
* **High-Precision Transcription:** Employs `faster-whisper (large-v3)` on the GPU for accurate speech-to-text conversion.
* **Smart Jump Cuts:** Automatically cuts out silences > 2.0s without breaking dialogues.
* **Cinematic Subtitles:** Hardcodes modern TikTok-style karaoke subtitles (`Montserrat Black` font) directly onto the video stream.
* **Vertical Format (9:16):** Automatically blurs the background and centers the original video.
* **Watermarks and Logos:** Supports overlaying a custom PNG logo onto the final output.
* **Telegram Bot Integration:** Includes the source code for a Telegram bot, allowing remote processing.

## System Requirements
- **OS:** Windows 10/11
- **GPU:** NVIDIA Graphics Card (6 GB VRAM minimum recommended for CUDA). 
- **Dependencies:** **Python 3.9+** and **FFmpeg** must be installed on the system.

## Installation (Windows)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/redmastersad/AniBazaTikTokMaker.git
   cd AniBazaTikTokMaker
   ```

2. **Install prerequisite software:**
   - Download and install [Ollama](https://ollama.com/) (required for the AI Director module).
   - Ensure `FFmpeg` is installed and added to the system `PATH`.

3. **Automated Setup:**
   Execute the `install.bat` file. 
   This script creates a virtual environment, downloads the necessary neural network models, installs CUDA dependencies, and configures the environment.

## Usage

**Method 1 (TikTok Studio window):**
Launch `run_tiktok_ai.bat`. The window has six sections:
- **Новая нарезка** — drop episodes (or pick files), choose what the AI should look for, clip length, how many clips per episode, music, silence cutting, anti-copyright filters, the Ollama model and the output folder.
- **Стиль и шрифты** — live 9:16 preview. Drag the subtitles, the AI title and the logo with the mouse (or arrow keys), pick a font or upload your own, change size, letter spacing, case, colours, outline, shadow, animation and words per screen. TikTok/Shorts button zones are shown. Styles can be saved as presets.
- **Обработка** — progress of transcription, AI search and montage, the moments found by the AI, pause/cancel and a log.
- **Готовые клипы** — all generated clips with AI titles and scores; select the best ones to delete or publish.
- **Публикация** — YouTube Shorts upload queue (Chrome robot) with title/description templates (`{название}`, `{тайтл}`, `{серия}`) and visibility.
- **Настройки** — Whisper model, silence threshold, custom music/logos/fonts.

The previous simple window is still available via `run_old_gui.bat`.

**Method 3 (TikTok upload from a folder, official API):**
`run_tiktok_upload.bat` uploads every `.mp4/.mov/.webm` from a folder to TikTok through the Content Posting API (no browser robot). Drag the folder onto the .bat or type its path. Uploaded videos move to the `Залито в TikTok` subfolder, so the next run only takes new ones; a log is kept in `tiktok_upload_log.txt`.
- Mode 1 sends videos to TikTok drafts (finish them in the TikTok app); mode 2 posts directly with the chosen privacy.
- Caption: `<video>.txt` next to the video, else the AI title from `clips.json`, else the file name, through a template with `{название}`, `{тайтл}`, `{серия}` and hashtags.
- One-time setup at https://developers.tiktok.com: create an app with platform **Desktop**, add the products **Login Kit** and **Content Posting API** (turn on Direct Post), scopes `user.info.basic`, `video.upload`, `video.publish`, redirect URI `http://127.0.0.1:3455/callback/`, add your TikTok account as a test user in Sandbox. Enter the Client key and Client secret on the first run (saved to `tiktok_config.json`) or put them into `.env` as `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET`.
- Until TikTok audits the app, direct posts are private («только мне») and the account must be private; after the audit public posting works. TikTok also caps posts per account per day (about 15).
- `--relogin` signs in again, `--logout` forgets the TikTok login, `--pause N` sets the pause between videos.

**Method 2 (Telegram Bot):**
1. Obtain a bot token from `@BotFather` on Telegram.
2. Open `bot.py` and assign the token to the `TOKEN` variable: `TOKEN = "YOUR_BOT_TOKEN"`.
3. Launch `run_bot.bat`.
4. Send video files directly to the bot via Telegram chat.

---
*Created exclusively for the **AniBaza** project.*
