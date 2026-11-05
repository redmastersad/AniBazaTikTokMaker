"""TikTok queue for the Studio window: videos from a folder, from «Готовые клипы» or from a Google Drive
link go to TikTok one by one through the official Content Posting API (tiktok_api.py)."""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid

import tiktok_api as tt

APP_DIR = os.path.dirname(os.path.abspath(__file__))
QUEUE_FILE = os.path.join(APP_DIR, "tiktok_queue.json")
GDRIVE_DIR = os.path.join(APP_DIR, "_tmp", "gdrive")
VIDEO_EXT = (".mp4", ".mov", ".webm")
LIMIT_CODES = {"spam_risk_too_many_posts", "spam_risk_too_many_pending_share", "reached_active_user_cap",
               "spam_risk_user_banned_from_posting", "rate_limit_exceeded"}
NICE_ERRORS = {
    "spam_risk_too_many_posts": "TikTok: лимит постов на сегодня",
    "spam_risk_too_many_pending_share": "TikTok: 5 неопубликованных черновиков за сутки, опубликуй их в приложении",
    "reached_active_user_cap": "TikTok: лимит приложения на сегодня",
    "spam_risk_user_banned_from_posting": "TikTok запретил аккаунту постить",
    "unaudited_client_can_only_post_to_private_accounts": "До проверки приложения: только приватный аккаунт и «только мне»",
    "privacy_level_option_mismatch": "Эта приватность недоступна аккаунту",
    "duration_check_failed": "Видео длиннее, чем разрешает TikTok",
    "file_format_check_failed": "TikTok не принял формат файла",
    "access_token_invalid": "Вход в TikTok устарел, войди заново",
    "scope_not_authorized": "Нет прав: войди в TikTok заново",
    "login_needed": "Вход в TikTok устарел, войди заново",
}

DEFAULT_TT_SETTINGS = {
    "mode": "draft",            # draft → TikTok inbox; post → direct post
    "privacy": "",              # chosen by the user from creator_info options
    "allow_comments": True,
    "caption_tpl": "{название}\n#аниме #anibaza",
    "pause": 20,
}


def _nice(e: Exception) -> str:
    if type(e).__module__.startswith(("requests", "urllib3")):
        return "Нет связи с TikTok (включи VPN?)"
    code = getattr(e, "code", "")
    return NICE_ERRORS.get(code) or (str(e).splitlines()[0][:200] if str(e) else "Ошибка")


def _natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def render_caption(tpl: str, entry: dict) -> str:
    values = {
        "название": entry.get("title", ""),
        "тайтл": entry.get("show", ""),
        "серия": entry.get("episode", ""),
    }
    out = tpl or "{название}"
    for k, v in values.items():
        out = out.replace("{" + k + "}", str(v))
    out = re.sub(r"#(?=\s|$)", "", out)
    lines = [" ".join(l.split()) for l in out.split("\n")]
    return "\n".join(l for l in lines if l).strip()[:2200]


def _clips_index(folder: str) -> dict:
    try:
        with open(os.path.join(folder, "clips.json"), "r", encoding="utf-8") as f:
            return {c["file"]: c for c in json.load(f) if isinstance(c, dict) and "file" in c}
    except Exception:
        return {}


def title_from_name(fn: str) -> str:
    """«20261025_025344_63972dcc_clip_002_Визуальная сцена 12.mp4» → «Визуальная сцена 12»; «001_Успех.mp4» → «Успех»."""
    t = os.path.splitext(fn)[0]
    t = re.sub(r"^\d{8}_\d{6}_[0-9a-f]+_clip_\d+_", "", t)
    t = re.sub(r"^\d{1,4}[_. -]+", "", t)
    t = re.sub(r"\s*\(\d+\)$", "", t)          # «… (1)» from Drive duplicates
    return " ".join(t.replace("_", " ").split()) or os.path.splitext(fn)[0]


def _entry_for(path: str, index: dict | None = None) -> dict:
    fn = os.path.basename(path)
    if index is None:
        index = _clips_index(os.path.dirname(path))
    e = dict(index.get(fn) or {})
    if not e.get("title"):
        e["title"] = title_from_name(fn)
    txt = os.path.splitext(path)[0] + ".txt"
    if os.path.exists(txt):
        try:
            with open(txt, "r", encoding="utf-8-sig") as f:
                e["caption"] = f.read().strip()[:2200]
        except Exception:
            pass
    return e


def ensure_gdown():
    try:
        import gdown  # noqa: F401
        return
    except ImportError:
        pass
    print("Ставлю gdown для Google Диска…")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    py = sys.executable.replace("pythonw.exe", "python.exe")
    r = subprocess.run([py, "-m", "pip", "install", "gdown>=5.2"], capture_output=True, text=True, creationflags=flags)
    if r.returncode != 0:
        raise RuntimeError("не удалось поставить gdown: " + (r.stderr or r.stdout)[-300:])
    import importlib
    importlib.invalidate_caches()


class TikTokQueue:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self.running = False
        self.stop_flag = threading.Event()
        self.note = ""                  # banner text (limit reached, Google Drive progress…)
        self.account: dict | None = None
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                self.items = json.load(f)
            for it in self.items:
                if it["status"] in ("running", "download"):
                    it["status"] = "queued"
        except Exception:
            self.items = []

    # ------------------------------------------------------------ settings / account
    def settings(self) -> dict:
        s = self.app._settings.setdefault("tiktok", {})
        for k, v in DEFAULT_TT_SETTINGS.items():
            s.setdefault(k, v)
        return s

    def keys(self) -> tuple[str, str]:
        return tt.load_keys()

    def account_info(self, refresh: bool = False) -> dict:
        key, secret = self.keys()
        out = {"keys": bool(key and secret), "logged": os.path.exists(tt.TOKEN_FILE)}
        if not out["keys"] or not out["logged"]:
            self.account = None
            return out
        if self.account and not refresh:
            return {**out, **self.account}
        try:
            client = tt.Client(tt.get_token(key, secret, interactive=False))
            info = client.creator_info()
            self.account = {
                "nickname": info.get("creator_nickname", ""),
                "username": info.get("creator_username", ""),
                "avatar": info.get("creator_avatar_url", ""),
                "privacy_options": info.get("privacy_level_options") or [],
                "comment_disabled": bool(info.get("comment_disabled")),
                "max_duration": info.get("max_video_post_duration_sec"),
                "error": "",
            }
        except Exception as e:
            self.account = {"error": _nice(e), "privacy_options": []}
            if getattr(e, "code", "") in ("access_token_invalid", "login_needed", "invalid_grant"):
                out["logged"] = False
        return {**out, **self.account}

    def login(self) -> dict:
        key, secret = self.keys()
        if not (key and secret):
            return {"error": "Сначала вставь Client key и Client secret"}
        try:
            tt.login(key, secret)
        except Exception as e:
            return {"error": _nice(e)}
        return self.account_info(refresh=True)

    # ------------------------------------------------------------ queue
    def _save(self):
        try:
            with open(QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.items[-500:], f, ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"Could not save TikTok queue: {e}")

    def _known(self) -> set:
        live = [it for it in self.items if it["status"] != "error"]
        return {(it["path"], it.get("size")) for it in live} | {it["gdrive_id"] for it in live if it.get("gdrive_id")}

    def _add(self, path: str, entry: dict, source: str, extra: dict | None = None) -> bool:
        size = os.path.getsize(path) if os.path.exists(path) else (extra or {}).get("size")
        known = self._known()
        if (path, size) in known or (extra or {}).get("gdrive_id") in known:
            return False
        tpl = self.settings()["caption_tpl"]
        self.items.append({
            "id": uuid.uuid4().hex[:10], "path": path, "file": os.path.basename(path), "size": size,
            "caption": entry.get("caption") or render_caption(tpl, entry), "source": source,
            "status": "queued", "detail": "", "progress": 0.0, "added": time.time(), **(extra or {}),
        })
        return True

    def add_files(self, paths: list[str], source: str = "folder") -> int:
        n = 0
        with self.lock:
            indexes: dict = {}
            for p in sorted(paths, key=lambda x: _natural(os.path.basename(x))):
                if not p.lower().endswith(VIDEO_EXT) or os.path.basename(p).startswith("temp_"):
                    continue
                d = os.path.dirname(p)
                if d not in indexes:
                    indexes[d] = _clips_index(d)
                n += self._add(p, _entry_for(p, indexes[d]), source)
            self._save()
        return n

    def add_folder(self, folder: str) -> int:
        if not os.path.isdir(folder):
            return 0
        return self.add_files([os.path.join(folder, f) for f in os.listdir(folder)], "folder")

    def add_gdrive(self, url: str) -> dict:
        url = (url or "").strip()
        if "drive.google.com" not in url and "docs.google.com" not in url:
            return {"error": "Это не ссылка на Google Диск"}
        threading.Thread(target=self._gdrive_list, args=(url,), daemon=True).start()
        return {"ok": True}

    def _gdrive_list(self, url: str):
        """Lists the shared Drive folder (or one file) and queues its videos; files download right before upload."""
        self.note = "Google Диск: читаю папку…"
        try:
            ensure_gdown()
            import gdown
            dest = os.path.join(GDRIVE_DIR, uuid.uuid4().hex[:8])
            os.makedirs(dest, exist_ok=True)
            entries = []
            if "/folders/" in url or "folderview" in url:
                files = gdown.download_folder(url=url, output=dest, quiet=True, skip_download=True)
                for f in files or []:
                    if "/" in f.path.replace("\\", "/").strip("/"):
                        continue            # only the folder itself, not its subfolders (Archive etc.)
                    entries.append((f.id, f.local_path))
            else:
                m = re.search(r"(?:/d/|id=)([\w-]{20,})", url)
                if not m:
                    raise RuntimeError("не понял ссылку")
                out = gdown.download(id=m.group(1), output=dest + os.sep, quiet=True)
                if out:
                    entries.append((None, out))
            vids = [(fid, p) for fid, p in entries if p.lower().endswith(VIDEO_EXT)]
            vids.sort(key=lambda x: _natural(os.path.relpath(x[1], dest)))
            with self.lock:
                added = sum(self._add(p, _entry_for(p, {}), "gdrive", {"gdrive_id": fid} if fid else None)
                            for fid, p in vids)
                self._save()
            self.note = f"Google Диск: добавлено {added} из {len(vids)} видео" if vids else \
                "Google Диск: видео не нашёл (папка должна быть открыта «всем, у кого есть ссылка»)"
            print(self.note)
            if vids:
                self.start()
        except Exception as e:
            self.note = f"Google Диск: {str(e).splitlines()[0][:200] if str(e) else 'ошибка'}"
            traceback.print_exc()

    def update(self, item_id, fields):
        with self.lock:
            for it in self.items:
                if it["id"] == item_id and it["status"] not in ("running", "download"):
                    if "caption" in fields:
                        it["caption"] = str(fields["caption"])[:2200]
                    if fields.get("retry"):
                        it.update(status="queued", detail="", progress=0.0)
            self._save()

    def remove(self, item_id):
        with self.lock:
            self.items = [it for it in self.items if not (it["id"] == item_id and it["status"] not in ("running", "download"))]
            self._save()

    def clear_done(self):
        with self.lock:
            self.items = [it for it in self.items if it["status"] != "done"]
            self._save()

    def stop(self):
        self.stop_flag.set()

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
            self.stop_flag.clear()
            self.note = ""
        threading.Thread(target=self._worker, daemon=True).start()

    # ------------------------------------------------------------ worker
    def _download(self, it):
        if os.path.exists(it["path"]):
            return
        if not it.get("gdrive_id"):
            raise RuntimeError("файл не найден")
        import gdown
        it.update(status="download", detail="скачиваю с Google Диска")
        os.makedirs(os.path.dirname(it["path"]), exist_ok=True)
        out = gdown.download(id=it["gdrive_id"], output=it["path"], quiet=True)
        if not out or not os.path.exists(it["path"]):
            raise RuntimeError("Google Диск не отдал файл (лимит скачиваний или нет доступа)")
        it["size"] = os.path.getsize(it["path"])

    def _worker(self):
        try:
            key, secret = self.keys()
            first = True
            while not self.stop_flag.is_set():
                st_ = self.settings()
                if st_["mode"] == "post" and not st_.get("privacy"):
                    self.note = "Выбери, кто увидит видео (справа), и запусти очередь снова"
                    break
                with self.lock:
                    it = next((x for x in self.items if x["status"] == "queued"), None)
                    if it:
                        it.update(status="running", detail="готовлю", progress=0.0)
                if not it:
                    break
                if not first:
                    time.sleep(max(int(self.settings().get("pause", 20)), 11))   # 6 init calls / min / user
                first = False
                s = self.settings()
                try:
                    self._download(it)
                    it.update(status="running", detail="загрузка")
                    client = tt.Client(tt.get_token(key, secret, interactive=False))
                    post_info = None
                    if s["mode"] == "post":
                        acc = self.account or {}
                        post_info = {
                            "title": it["caption"],
                            "privacy_level": s["privacy"],
                            "disable_comment": bool(acc.get("comment_disabled")) or not s.get("allow_comments", True),
                            "disable_duet": True,
                            "disable_stitch": True,
                            "video_cover_timestamp_ms": 1000,
                        }
                    publish_id, url, src = client.init_upload(it["path"], post_info)

                    def prog(done, total, it=it):
                        it["progress"] = done / total
                        it["detail"] = f"загрузка {int(done * 100 / total)}%"
                    client.put_file(it["path"], url, src, prog)
                    it["detail"] = "TikTok обрабатывает"
                    st = client.wait(publish_id)
                    status = st.get("status", "")
                    it.update(status="done", progress=1.0, publish_id=publish_id,
                              detail="в черновиках TikTok" if post_info is None else
                              ("опубликовано" if status == "PUBLISH_COMPLETE" else "TikTok проверяет"))
                    print(f"TikTok: {it['file']} — {it['detail']}")
                    if it.get("source") == "gdrive":
                        try:
                            os.remove(it["path"])
                        except OSError:
                            pass
                except Exception as e:
                    code = getattr(e, "code", "")
                    if code in LIMIT_CODES:
                        it.update(status="queued", detail="", progress=0.0)
                        self.note = _nice(e) + ". Очередь остановлена, запусти позже."
                        print(self.note)
                        break
                    it.update(status="error", detail=_nice(e))
                    traceback.print_exc()
                finally:
                    with self.lock:
                        self._save()
        finally:
            self.running = False
            with self.lock:
                self._save()
            self._cleanup_gdrive()

    def _cleanup_gdrive(self):
        if not os.path.isdir(GDRIVE_DIR):
            return
        busy = {os.path.dirname(it["path"]) for it in self.items if it["status"] in ("queued", "running", "download")}
        for d in os.listdir(GDRIVE_DIR):
            p = os.path.join(GDRIVE_DIR, d)
            if p not in busy and not any(b.startswith(p + os.sep) for b in busy):
                shutil.rmtree(p, ignore_errors=True)

    def snapshot(self):
        with self.lock:
            return {"running": self.running, "note": self.note, "items": copy.deepcopy(self.items),
                    "done_paths": [it["path"] for it in self.items if it["status"] == "done"]}
