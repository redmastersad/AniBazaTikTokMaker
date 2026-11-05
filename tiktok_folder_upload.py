"""Uploads every video from a folder to TikTok through the official Content Posting API.

    python tiktok_folder_upload.py [ПАПКА] [--draft | --post] [--pause СЕК] [--relogin] [--logout]

* --draft  (default): videos land in TikTok drafts/inbox; finish and publish them in the TikTok app.
* --post            : direct post with the chosen privacy (an unaudited app can only post «только мне»).

Uploaded files are moved to the «Залито в TikTok» subfolder, so a re-run only takes new ones.
Caption: <video>.txt next to the video if present, else the AI title from clips.json, else the file
name; plus the «подпись» template saved in tiktok_config.json ({название}, {тайтл}, {серия}).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time

import tiktok_api as tt

VIDEO_EXT = (".mp4", ".mov", ".webm")
DONE_DIR = "Залито в TikTok"
LOG_NAME = "tiktok_upload_log.txt"
STOP_CODES = {"spam_risk_too_many_posts", "spam_risk_too_many_pending_share", "reached_active_user_cap",
              "spam_risk_user_banned_from_posting", "unaudited_client_can_only_post_to_private_accounts"}


def ask(prompt: str, default: str = "") -> str:
    try:
        v = input(prompt).strip().strip('"')
    except EOFError:
        v = ""
    return v or default


def yes(prompt: str) -> bool:
    return ask(prompt + " (д/н): ").lower() in ("д", "да", "y", "yes", "l")


def setup_keys() -> tuple[str, str]:
    key, secret = tt.load_keys()
    if key and secret:
        return key, secret
    print("Нужны ключи приложения TikTok (developers.tiktok.com → твоё приложение → App details).")
    print(f"Redirect URI в Login Kit должен быть: {tt.REDIRECT_URI}\n")
    key = ask("Client key: ")
    secret = ask("Client secret: ")
    if not key or not secret:
        sys.exit("Без ключей залить нельзя.")
    tt.save_keys(key, secret)
    print("Ключи сохранены в tiktok_config.json\n")
    return key, secret


def caption_for(path: str, index: dict, tpl: str) -> str:
    txt = os.path.splitext(path)[0] + ".txt"
    if os.path.exists(txt):
        with open(txt, "r", encoding="utf-8-sig") as f:
            return f.read().strip()[:2200]
    fn = os.path.basename(path)
    entry = index.get(fn) or {}
    values = {
        "название": entry.get("title") or os.path.splitext(fn)[0].replace("_", " "),
        "тайтл": entry.get("show", ""),
        "серия": entry.get("episode", ""),
    }
    out = tpl or "{название}"
    for k, v in values.items():
        out = out.replace("{" + k + "}", str(v))
    out = re.sub(r"#(?=\s|$)", "", out)          # «#{тайтл}» with an empty value
    return " ".join(out.split())[:2200]


def read_index(folder: str) -> dict:
    try:
        with open(os.path.join(folder, "clips.json"), "r", encoding="utf-8") as f:
            return {c["file"]: c for c in json.load(f) if isinstance(c, dict) and "file" in c}
    except Exception:
        return {}


def pick_privacy(options: list[str]) -> str:
    print("Кто увидит видео? (выбери номер)")
    for i, o in enumerate(options, 1):
        print(f"  {i}. {tt.PRIVACY_NAMES.get(o, o)}")
    while True:
        v = ask("> ")
        if v.isdigit() and 1 <= int(v) <= len(options):
            return options[int(v) - 1]


def log(folder: str, line: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(line)
    with open(os.path.join(folder, LOG_NAME), "a", encoding="utf-8") as f:
        f.write(f"{stamp}  {line}\n")


def progress(done: int, total: int) -> None:
    print(f"\r    загрузка {done * 100 // total:3d}%  ({done / 1048576:.1f} / {total / 1048576:.1f} МБ)", end="", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Залить видео из папки в TikTok по API")
    p.add_argument("folder", nargs="?")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--draft", action="store_true", help="в черновики TikTok (по умолчанию спрошу)")
    mode.add_argument("--post", action="store_true", help="сразу опубликовать")
    p.add_argument("--pause", type=int, default=15, help="пауза между видео, сек")
    p.add_argument("--relogin", action="store_true", help="войти в TikTok заново")
    p.add_argument("--logout", action="store_true", help="забыть вход в TikTok")
    args = p.parse_args()

    if args.logout:
        tt.logout()
        print("Вход в TikTok забыт.")
        return

    key, secret = setup_keys()
    token = tt.get_token(key, secret, force_login=args.relogin)
    client = tt.Client(token)

    cfg = tt._read_json(tt.CONFIG_FILE)
    folder = args.folder or ask(
        f"Папка с видео (перетащи сюда, Enter = {cfg.get('last_folder') or 'нет'}): ", cfg.get("last_folder", ""))
    folder = os.path.abspath(folder.strip('"')) if folder else ""
    if not os.path.isdir(folder):
        sys.exit(f"Папка не найдена: {folder}")

    files = sorted((os.path.join(folder, f) for f in os.listdir(folder)
                    if f.lower().endswith(VIDEO_EXT) and not f.startswith("temp_")),
                   key=os.path.getmtime)
    if not files:
        print("В папке нет новых видео (.mp4/.mov/.webm).")
        return

    try:
        info = client.creator_info()
    except tt.TikTokError as e:
        if e.code in ("access_token_invalid", "scope_not_authorized"):
            token = tt.get_token(key, secret, force_login=True)
            client = tt.Client(token)
            info = client.creator_info()
        else:
            raise
    print(f"\nАккаунт TikTok: {info.get('creator_nickname')} (@{info.get('creator_username')})")
    print(f"Видео в папке: {len(files)}. Максимальная длина ролика: {info.get('max_video_post_duration_sec')} с.\n")

    if args.post:
        direct = True
    elif args.draft:
        direct = False
    else:
        print("Как заливать?\n  1. В черновики TikTok (опубликуешь сам из приложения: звук, обложка)\n"
              "  2. Сразу опубликовать")
        direct = ask("> ", "1") == "2"

    post_info = None
    if direct:
        privacy = pick_privacy(info.get("privacy_level_options") or ["SELF_ONLY"])
        allow = yes("Разрешить комментарии?")
        post_info = {
            "privacy_level": privacy,
            "disable_comment": bool(info.get("comment_disabled")) or not allow,
            "disable_duet": True,
            "disable_stitch": True,
            "video_cover_timestamp_ms": 1000,
        }
        print("Публикуя, ты соглашаешься с TikTok Music Usage Confirmation "
              "(https://www.tiktok.com/legal/page/global/music-usage-confirmation/en).")

    tpl = cfg.get("caption_tpl")
    if tpl is None:
        tpl = ask("Шаблон подписи ({название}, {тайтл}, {серия}, хэштеги). Enter = {название}: ", "{название}")
    cfg.update(last_folder=folder, caption_tpl=tpl)
    tt._write_json(tt.CONFIG_FILE, cfg)

    index = read_index(folder)
    done_dir = os.path.join(folder, DONE_DIR)
    os.makedirs(done_dir, exist_ok=True)
    ok = 0
    for n, path in enumerate(files, 1):
        fn = os.path.basename(path)
        print(f"\n[{n}/{len(files)}] {fn}")
        try:
            token = tt.get_token(key, secret)          # refresh if the 24 h token ran out mid-run
            client.token = token
            info_post = None
            if post_info is not None:
                info_post = dict(post_info, title=caption_for(path, index, tpl))
                print(f"    подпись: {info_post['title']}")
            publish_id, url, src = client.init_upload(path, info_post)
            client.put_file(path, url, src, progress)
            print()
            st = client.wait(publish_id)
            status = st.get("status", "?")
        except tt.TikTokError as e:
            print()
            log(folder, f"ОШИБКА {fn}: {e}")
            if e.code in STOP_CODES:
                print("\nTikTok ограничил заливку на сегодня/для этого аккаунта. Остальное зальётся при следующем запуске.")
                break
            continue
        except KeyboardInterrupt:
            print("\nОстановлено.")
            break
        shutil.move(path, os.path.join(done_dir, fn))
        txt = os.path.splitext(path)[0] + ".txt"
        if os.path.exists(txt):
            shutil.move(txt, os.path.join(done_dir, os.path.basename(txt)))
        where = "в черновиках TikTok" if post_info is None else (
            "опубликовано" if status == "PUBLISH_COMPLETE" else f"обрабатывается ({status})")
        log(folder, f"OK {fn}: {where}")
        ok += 1
        if n < len(files):
            time.sleep(max(args.pause, 0))

    print(f"\nГотово: {ok} из {len(files)}. Залитые лежат в «{DONE_DIR}».")
    if post_info is None and ok:
        print("Открой TikTok на телефоне → уведомления/черновики и опубликуй.")


if __name__ == "__main__":
    try:
        main()
    except tt.TikTokError as e:
        print(f"\nОшибка TikTok: {e}")
    except KeyboardInterrupt:
        print("\nОстановлено.")
