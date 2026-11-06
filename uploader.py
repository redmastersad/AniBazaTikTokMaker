"""YouTube Shorts upload robot (Playwright + the user's Chrome profile in ./youtube_profile)."""
from __future__ import annotations

import os
import time

from style import APP_DIR

USER_DATA_DIR = os.path.join(APP_DIR, "youtube_profile")
CHANNEL_FILE = os.path.join(APP_DIR, "channel_name.txt")


def _launch(p, headless: bool):
    args = ["--disable-blink-features=AutomationControlled"]
    if headless:
        args += ["--headless=new", "--window-size=1920,1080", "--mute-audio"]
    return p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR, headless=False, channel="chrome", args=args,
        chromium_sandbox=True)  # without it Playwright adds --no-sandbox and Chrome shows a warning bar


def channel_name() -> str | None:
    try:
        with open(CHANNEL_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def login() -> str:
    """Opens Chrome so the user signs in to YouTube Studio once. Returns the channel name."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _launch(p, headless=False)
        try:
            page = browser.pages[0]
            page.goto("https://studio.youtube.com/")
            page.wait_for_url("**/studio.youtube.com/channel/**", timeout=0)
            try:
                page.wait_for_selector("#channel-name", timeout=15000)
                name = page.locator("#channel-name").first.inner_text().strip()
            except Exception:
                name = "Вход выполнен"
        finally:
            browser.close()
    with open(CHANNEL_FILE, "w", encoding="utf-8") as f:
        f.write(name)
    return name


def upload(video_path: str, title: str, description: str, visibility: str = "PUBLIC", on_status=None):
    """Uploads one video as a Short. visibility: PUBLIC | UNLISTED | PRIVATE. Raises on failure."""
    from playwright.sync_api import sync_playwright
    status = on_status or (lambda s: None)
    title = title[:100]
    description = description[:4900]
    with sync_playwright() as p:
        browser = _launch(p, headless=True)
        try:
            page = browser.pages[0]
            status("Открываю YouTube Studio")
            page.goto("https://studio.youtube.com/")
            page.wait_for_url("**/studio.youtube.com/channel/**", timeout=30000)

            page.wait_for_selector("#create-icon", state="visible", timeout=30000)
            page.click("#create-icon")
            page.wait_for_selector("tp-yt-paper-item#text-item-0", state="visible", timeout=15000)
            page.click("tp-yt-paper-item#text-item-0")

            status("Загружаю файл")
            page.wait_for_selector("input[type='file']", state="attached", timeout=15000)
            page.set_input_files("input[type='file']", video_path)

            page.wait_for_selector("div#title-textarea", state="visible", timeout=60000)
            time.sleep(3)
            status("Заполняю название и описание")
            page.locator("div#title-textarea #textbox").first.fill("")
            page.locator("div#title-textarea #textbox").first.type(title, delay=10)
            page.locator("div#description-textarea #textbox").first.fill("")
            page.locator("div#description-textarea #textbox").first.type(description, delay=10)

            page.locator("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']").first.click()
            for _ in range(3):
                page.locator("#next-button").first.click()
                time.sleep(2)

            status("Публикую")
            page.locator(f"tp-yt-paper-radio-button[name='{visibility}']").first.click()
            time.sleep(1)
            page.locator("#done-button").first.click()
            page.wait_for_selector("ytcp-video-share-dialog", state="visible", timeout=180000)
            link = None
            try:
                link = page.locator("ytcp-video-share-dialog a.ytcp-video-info").first.get_attribute("href", timeout=3000)
            except Exception:
                pass
        finally:
            browser.close()
    return link
