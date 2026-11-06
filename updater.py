"""Auto-update: pulls the latest version of the app from GitHub (main branch) before start.

run_tiktok_ai.bat runs `python updater.py` first. Only files that are in the repository get replaced;
user data (venv, settings, presets, clips, logins, own fonts/logos/music) is never touched.
A git checkout (developer copy) is never updated. ANIBAZA_NO_UPDATE=1 turns it off.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import urllib.request
import zipfile

REPO = "redmastersad/AniBazaTikTokMaker"
BRANCH = "main"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(APP_DIR, "version.txt")
UA = {"User-Agent": "AniBaza-TikTok-Studio-updater"}

# never written by the updater even if the repository has them
SKIP_PREFIXES = ("venv/", "env/", "output/", "_tmp/", "_webview/", "youtube_profile/", ".git/")
SKIP_FILES = {"settings.json", "presets.json", "uploads.json", ".env", "version.txt",
              "tiktok_config.json", "tiktok_token.json", "tiktok_queue.json", "channel_name.txt"}


def local_version() -> str:
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def remote_version(timeout: float = 6.0) -> str:
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}",
                                 headers={**UA, "Accept": "application/vnd.github.sha"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        sha = r.read().decode("ascii", "ignore").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError(f"unexpected answer: {sha[:60]}")
    return sha


def update_available() -> tuple[bool, str, str]:
    """(available, local, remote) — for the app's «есть обновление» badge. Never raises."""
    loc = local_version()
    if os.path.isdir(os.path.join(APP_DIR, ".git")):
        return False, loc or "git", ""
    try:
        rem = remote_version()
    except Exception:
        return False, loc, ""
    return rem != loc, loc, rem


def _keep_bot_token(new: bytes, old: bytes) -> bytes:
    """bot.py holds the Telegram token in the file itself: carry the user's TOKEN line over."""
    m = re.search(rb'^TOKEN = .*$', old, re.M)
    if not m or b"YOUR_BOT_TOKEN" in m.group(0):
        return new
    return re.sub(rb'^TOKEN = .*$', lambda _: m.group(0), new, count=1, flags=re.M)


def apply_update(sha: str) -> list[str]:
    url = f"https://codeload.github.com/{REPO}/zip/{sha}"
    print("Скачиваю обновление...")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        data = r.read()
    changed = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            parts = info.filename.split("/", 1)
            if len(parts) < 2 or not parts[1]:
                continue
            rel = parts[1]
            if rel in SKIP_FILES or rel.startswith(SKIP_PREFIXES) or ".." in rel.split("/"):
                continue
            dst = os.path.join(APP_DIR, *rel.split("/"))
            new = z.read(info)
            old = None
            if os.path.isfile(dst):
                with open(dst, "rb") as f:
                    old = f.read()
            if rel == "bot.py" and old is not None:
                new = _keep_bot_token(new, old)
            if old is not None and hashlib.sha1(old).digest() == hashlib.sha1(new).digest():
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tmp = dst + ".upd"
            with open(tmp, "wb") as f:
                f.write(new)
            os.replace(tmp, dst)
            changed.append(rel)
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(sha)
    return changed


def main() -> int:
    if os.environ.get("ANIBAZA_NO_UPDATE") or os.path.isdir(os.path.join(APP_DIR, ".git")):
        return 0
    print("Проверяю обновления...")
    try:
        sha = remote_version()
    except Exception as e:
        print(f"Не удалось проверить обновления ({e}), запускаю как есть.")
        return 0
    if sha == local_version():
        print("Версия свежая.")
        return 0
    req_before = _read(os.path.join(APP_DIR, "requirements.txt"))
    try:
        changed = apply_update(sha)
    except Exception as e:
        print(f"Обновление не удалось ({e}), запускаю старую версию.")
        return 0
    print(f"Обновлено файлов: {len(changed)}" + (": " + ", ".join(changed[:12]) if changed else ""))
    if _read(os.path.join(APP_DIR, "requirements.txt")) != req_before:
        print("Ставлю новые библиотеки...")
        subprocess.call([sys.executable, "-m", "pip", "install", "-r", os.path.join(APP_DIR, "requirements.txt")])
    try:
        with open(os.path.join(APP_DIR, "_tmp", "updated.json"), "w", encoding="utf-8") as f:
            json.dump({"version": sha, "files": changed}, f)
    except OSError:
        pass
    return 0


def _read(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return b""


if __name__ == "__main__":
    sys.exit(main())
