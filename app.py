"""AniBaza TikTok Studio — desktop app (pywebview window + HTML UI in ./ui)."""
from __future__ import annotations

import base64
import collections
import copy
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)  # ffmpeg filter paths are relative to the app folder

SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
UPLOADS_FILE = os.path.join(APP_DIR, "uploads.json")
MUSIC_DIR = os.path.join(APP_DIR, "Assets", "Music")
LOG_FILE = os.path.join(APP_DIR, "app.log")


# ------------------------------------------------------------------ logging
class LogTee:
    """Keeps the last lines for the in-app journal, mirrors them to app.log and the console (if any)."""

    def __init__(self, original):
        self.original = original
        self.lines = collections.deque(maxlen=400)
        self.seq = 0
        self.lock = threading.Lock()
        self._partial = ""
        try:
            self.file = open(LOG_FILE, "a", encoding="utf-8")
        except Exception:
            self.file = None

    def write(self, msg):
        if self.original is not None:
            try:
                self.original.write(msg)
            except Exception:
                pass
        if self.file:
            try:
                self.file.write(msg)
                self.file.flush()
            except Exception:
                pass
        with self.lock:
            text = self._partial + msg
            parts = text.split("\n")
            self._partial = parts.pop()
            for p in parts:
                p = p.rstrip("\r")
                if p.strip():
                    self.seq += 1
                    self.lines.append((self.seq, time.strftime("%H:%M:%S"), p.strip()))

    def flush(self):
        if self.original is not None:
            try:
                self.original.flush()
            except Exception:
                pass

    def since(self, seq):
        with self.lock:
            return [{"seq": s, "t": t, "text": x} for s, t, x in self.lines if s > seq]


LOG = LogTee(sys.stdout)
sys.stdout = LOG
sys.stderr = LOG

import webview  # noqa: E402

import style as style_mod  # noqa: E402
from analyzer import CATEGORIES, DEFAULT_CATEGORIES  # noqa: E402
from main import (DEFAULT_OPTIONS, parse_episode_name, process_video,  # noqa: E402
                  read_clips_index, write_clips_index)
from video_editor import Cancelled, grab_frame, probe_duration  # noqa: E402

VIDEO_EXT = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v")
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")

DEFAULT_SETTINGS = {
    "out_dir": os.path.join(APP_DIR, "output"),
    "ollama_model": "llama3.1",
    "whisper_model": "large-v3",
    "categories": list(DEFAULT_CATEGORIES),
    "clip_min": 25,
    "clip_max": 60,
    "max_clips": 6,
    "remove_silence": True,
    "silence_gap": 2.0,
    "music": "",
    "music_volume": -16.0,
    "mirror": True,
    "filters": True,
    "preset": "АниБаза",
    "style": copy.deepcopy(style_mod.DEFAULT_STYLE),
    "upload": {
        "title_tpl": "{название}",
        "desc_tpl": "Озвучка AniBaza. Смотри полностью на anibaza.com\n{тайтл}, {серия} серия\n#аниме #shorts",
        "visibility": "PUBLIC",
    },
}


def _open_path(path):
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _data_uri(path, mime):
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def load_settings() -> dict:
    s = copy.deepcopy(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    # settings from the old customtkinter window
    if "out_path" in data and "out_dir" not in data:
        data["out_dir"] = data.pop("out_path")
    if "ai_model" in data and "ollama_model" not in data:
        data["ollama_model"] = data.pop("ai_model")
    if data.get("music") == "None":
        data["music"] = ""
    old_logo = data.pop("logo", None)
    for k in ("ui_lang",):
        data.pop(k, None)
    for k, v in data.items():
        if k == "style":
            s["style"] = style_mod.normalize_style(v)
        elif k == "upload" and isinstance(v, dict):
            s["upload"].update(v)
        elif k in s:
            s[k] = v
    if old_logo and old_logo != "None" and "style" not in data:
        s["style"]["logo"]["file"] = old_logo
    if not s.get("out_dir"):
        s["out_dir"] = DEFAULT_SETTINGS["out_dir"]
    return s


def save_settings_file(s: dict):
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)


# ------------------------------------------------------------------ system status
class SystemStatus:
    def __init__(self):
        self.data = {"gpu": None, "ollama": {"ok": False, "models": []}}
        self.lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            gpu = None
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip().splitlines()
                if out:
                    name, used, total, util = [x.strip() for x in out[0].split(",")]
                    gpu = {"name": name.replace("NVIDIA GeForce ", ""), "used": float(used) / 1024,
                           "total": float(total) / 1024, "util": int(float(util))}
            except Exception:
                pass
            ollama = {"ok": False, "models": []}
            try:
                import httpx
                r = httpx.get("http://localhost:11434/api/tags", timeout=2)
                ollama = {"ok": True, "models": sorted(m["name"].removesuffix(":latest") for m in r.json().get("models", []))}
            except Exception:
                pass
            with self.lock:
                self.data = {"gpu": gpu, "ollama": ollama}
            time.sleep(4)

    def get(self):
        with self.lock:
            return copy.deepcopy(self.data)


# ------------------------------------------------------------------ processing queue
STEP_WEIGHTS = (0.45, 0.10, 0.45)


class Jobs:
    def __init__(self, app):
        self.app = app
        self.items: list[dict] = []
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.pause = threading.Event()
        self.running = False
        self.current = None

    def add(self, paths):
        added = []
        with self.lock:
            known = {j["path"] for j in self.items if j["status"] in ("queued", "running")}
            for p in paths:
                if not p or not os.path.isfile(p) or not p.lower().endswith(VIDEO_EXT) or p in known:
                    continue
                show, ep = parse_episode_name(p)
                job = {
                    "id": uuid.uuid4().hex[:10], "path": p, "file": os.path.basename(p),
                    "show": show, "episode": ep, "size": os.path.getsize(p), "duration": 0,
                    "thumb": None, "status": "queued", "step": -1, "step_progress": 0.0,
                    "percent": 0.0, "moments": [], "clip_index": -1, "words": 0, "error": "",
                    "started": None, "finished": None, "clips": 0,
                }
                self.items.append(job)
                added.append(job)
        for job in added:
            threading.Thread(target=self._probe, args=(job,), daemon=True).start()
        return len(added)

    def _probe(self, job):
        job["duration"] = probe_duration(job["path"])
        os.makedirs(os.path.join(APP_DIR, "_tmp"), exist_ok=True)
        jpg = os.path.join(APP_DIR, "_tmp", f"thumb_{job['id']}.jpg")
        if grab_frame(job["path"], jpg, height=360):
            job["thumb"] = _data_uri(jpg, "image/jpeg")
            try:
                os.remove(jpg)
            except OSError:
                pass

    def remove(self, job_id):
        with self.lock:
            self.items = [j for j in self.items if not (j["id"] == job_id and j["status"] != "running")]

    def clear_finished(self):
        with self.lock:
            self.items = [j for j in self.items if j["status"] in ("queued", "running")]

    def start(self):
        with self.lock:
            if self.running:
                return False
            if not any(j["status"] == "queued" for j in self.items):
                return False
            self.running = True
            self.cancel.clear()
            self.pause.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        return True

    def _worker(self):
        try:
            while True:
                with self.lock:
                    job = next((j for j in self.items if j["status"] == "queued"), None)
                if job is None or self.cancel.is_set():
                    break
                self._run(job)
        finally:
            with self.lock:
                self.running = False
                self.current = None
                if self.cancel.is_set():
                    for j in self.items:
                        if j["status"] == "queued":
                            j["status"] = "cancelled"

    def _run(self, job):
        s = self.app._settings
        job.update(status="running", started=time.time(), step=0, error="")
        self.current = job

        def on_event(kind, data):
            if kind == "step":
                job["step"] = data["step"]
                job["step_progress"] = data["progress"]
                if "words" in data:
                    job["words"] = data["words"]
                step = min(data["step"], 2)
                job["percent"] = sum(STEP_WEIGHTS[:step]) + STEP_WEIGHTS[step] * data["progress"]
            elif kind == "moments":
                job["moments"] = [{
                    "title": m["title"], "start": m["start"], "end": m["end"], "why": m.get("explanation", ""),
                    "category": m.get("category", ""), "score": m.get("score", 3), "status": "queued", "progress": 0,
                } for m in data["moments"]]
            elif kind == "clip_start":
                job["clip_index"] = data["index"]
                if data["index"] < len(job["moments"]):
                    job["moments"][data["index"]]["status"] = "run"
            elif kind == "clip_progress":
                if data["index"] < len(job["moments"]):
                    job["moments"][data["index"]]["progress"] = data["progress"]
            elif kind == "clip_done":
                if data["index"] < len(job["moments"]):
                    job["moments"][data["index"]]["status"] = "done"
                job["clips"] += 1

        music = s.get("music") or ""
        music_path = None
        if music:
            music_path = music if os.path.isabs(music) else os.path.join(MUSIC_DIR, music)
            if not os.path.exists(music_path):
                music_path = None
        options = {k: s.get(k, v) for k, v in DEFAULT_OPTIONS.items()}
        try:
            process_video(job["path"], s["out_dir"], music_path=music_path, remove_silence=bool(s["remove_silence"]),
                          ai_model=s["ollama_model"], style=s["style"], options=options, on_event=on_event,
                          cancel=self.cancel, pause=self.pause)
            job["status"] = "done" if job["clips"] else "empty"
            job["percent"] = 1.0
        except Cancelled:
            job["status"] = "cancelled"
            print("Обработка отменена")
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)[:400]
            traceback.print_exc()
        finally:
            job["finished"] = time.time()

    def snapshot(self):
        with self.lock:
            items = copy.deepcopy(self.items)
        now = time.time()
        for j in items:
            if j["status"] == "running" and j["started"] and j["percent"] > 0.03:
                elapsed = now - j["started"]
                j["eta"] = elapsed / j["percent"] - elapsed
        return {"running": self.running, "paused": self.pause.is_set(), "jobs": items}


# ------------------------------------------------------------------ upload queue
class Uploads:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self.running = False
        try:
            with open(UPLOADS_FILE, "r", encoding="utf-8") as f:
                self.items = json.load(f)
            for it in self.items:
                if it["status"] == "running":
                    it["status"] = "queued"
        except Exception:
            self.items = []

    def _save(self):
        try:
            with open(UPLOADS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.items[-300:], f, ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"Could not save uploads: {e}")

    @staticmethod
    def render(tpl: str, entry: dict) -> str:
        values = {
            "название": entry.get("title", ""),
            "тайтл": entry.get("show", ""),
            "серия": entry.get("episode", ""),
        }
        out = tpl or ""
        for k, v in values.items():
            out = out.replace("{" + k + "}", str(v))
        return out.strip()

    def enqueue(self, files):
        s = self.app._settings
        index = {c["file"]: c for c in read_clips_index(s["out_dir"])}
        with self.lock:
            for fn in files:
                entry = index.get(fn, {"file": fn, "title": os.path.splitext(fn)[0]})
                self.items.append({
                    "id": uuid.uuid4().hex[:10],
                    "path": os.path.join(s["out_dir"], fn), "file": fn,
                    "title": self.render(s["upload"]["title_tpl"], entry)[:100],
                    "description": self.render(s["upload"]["desc_tpl"], entry),
                    "visibility": s["upload"].get("visibility", "PUBLIC"),
                    "status": "queued", "detail": "", "link": None, "added": time.time(),
                })
            self._save()

    def update(self, item_id, fields):
        with self.lock:
            for it in self.items:
                if it["id"] == item_id and it["status"] != "running":
                    for k in ("title", "description", "visibility"):
                        if k in fields:
                            it[k] = fields[k]
                    if fields.get("retry"):
                        it["status"], it["detail"] = "queued", ""
            self._save()

    def remove(self, item_id):
        with self.lock:
            self.items = [it for it in self.items if not (it["id"] == item_id and it["status"] != "running")]
            self._save()

    def clear_done(self):
        with self.lock:
            self.items = [it for it in self.items if it["status"] != "done"]
            self._save()

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        import uploader
        try:
            while True:
                with self.lock:
                    it = next((x for x in self.items if x["status"] == "queued"), None)
                    if it:
                        it["status"] = "running"
                if not it:
                    break
                try:
                    def status(text, it=it):
                        it["detail"] = text
                    link = uploader.upload(it["path"], it["title"], it["description"], it["visibility"], status)
                    it.update(status="done", detail="", link=link)
                except Exception as e:
                    it.update(status="error", detail=str(e).splitlines()[0][:200] if str(e) else "Ошибка")
                    traceback.print_exc()
                with self.lock:
                    self._save()
        finally:
            self.running = False

    def snapshot(self):
        with self.lock:
            return {"running": self.running, "items": copy.deepcopy(self.items)}


# ------------------------------------------------------------------ JS API
class Api:
    def __init__(self):
        self._settings = load_settings()
        self._sys = SystemStatus()
        self._jobs = Jobs(self)
        self._uploads = Uploads(self)
        self._window = None
        self._thumb_cache = {}
        self._thumb_lock = threading.Lock()

    # --- boot
    def init(self):
        return {
            "settings": self._settings,
            "presets": style_mod.load_presets(),
            "builtin_presets": list(style_mod.BUILTIN_PRESETS.keys()),
            "fonts": style_mod.list_fonts(),
            "logos": self._logos(),
            "music": self._music(),
            "categories": [{"id": k, "label": v[0]} for k, v in CATEGORIES.items()],
            "channel": self._channel(),
        }

    def _logos(self):
        os.makedirs(style_mod.LOGOS_DIR, exist_ok=True)
        return [f for f in sorted(os.listdir(style_mod.LOGOS_DIR)) if f.lower().endswith(".png")]

    def _music(self):
        os.makedirs(MUSIC_DIR, exist_ok=True)
        return [f for f in sorted(os.listdir(MUSIC_DIR)) if f.lower().endswith(AUDIO_EXT)]

    def _channel(self):
        import uploader
        return uploader.channel_name()

    def font_data(self, file):
        path = os.path.join(style_mod.FONTS_DIR, os.path.basename(file))
        mime = "font/otf" if path.lower().endswith(".otf") else "font/ttf"
        return _data_uri(path, mime) if os.path.exists(path) else None

    def logo_data(self, name):
        path = style_mod.resolve_logo({"logo": {"visible": True, "file": name}})
        return _data_uri(path, "image/png") if path else None

    def system(self):
        return self._sys.get()

    # --- settings & presets
    def save_settings(self, settings):
        merged = copy.deepcopy(self._settings)
        for k, v in (settings or {}).items():
            if k == "style":
                merged["style"] = style_mod.normalize_style(v)
            elif k == "upload" and isinstance(v, dict):
                merged["upload"].update(v)
            elif k in DEFAULT_SETTINGS:
                merged[k] = v
        self._settings = merged
        save_settings_file(merged)
        return True

    def save_preset(self, name, style):
        name = (name or "").strip()[:40]
        if not name:
            return {"error": "Пустое имя"}
        if name in style_mod.BUILTIN_PRESETS:
            return {"error": "Это имя занято встроенным пресетом"}
        style_mod.save_user_preset(name, style)
        return {"presets": style_mod.load_presets()}

    def delete_preset(self, name):
        if name in style_mod.BUILTIN_PRESETS:
            return {"error": "Встроенный пресет нельзя удалить"}
        style_mod.delete_user_preset(name)
        return {"presets": style_mod.load_presets()}

    # --- dialogs
    def _dialog(self, kind, types=(), multiple=False):
        kind = {"open": getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG,
                "folder": getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG}[kind]
        w = self._window
        res = w.create_file_dialog(kind, allow_multiple=multiple, file_types=types)
        if not res:
            return []
        return list(res) if isinstance(res, (list, tuple)) else [res]

    def pick_videos(self):
        paths = self._dialog("open", ("Видео (*.mp4;*.mkv;*.mov;*.avi;*.webm)", "Все файлы (*.*)"), True)
        return self._jobs.add(paths)

    def add_paths(self, paths):
        return self._jobs.add(paths or [])

    def pick_out_dir(self):
        res = self._dialog("folder")
        if res:
            self.save_settings({"out_dir": res[0]})
            return res[0]
        return None

    def pick_logo(self):
        res = self._dialog("open", ("PNG (*.png)",))
        if not res:
            return None
        dst = os.path.join(style_mod.LOGOS_DIR, os.path.basename(res[0]))
        if os.path.abspath(dst) != os.path.abspath(res[0]):
            shutil.copyfile(res[0], dst)
        return {"logos": self._logos(), "name": os.path.basename(dst)}

    def pick_music(self):
        res = self._dialog("open", ("Аудио (*.mp3;*.wav;*.m4a;*.aac;*.ogg;*.flac)",))
        if not res:
            return None
        dst = os.path.join(MUSIC_DIR, os.path.basename(res[0]))
        if os.path.abspath(dst) != os.path.abspath(res[0]):
            shutil.copyfile(res[0], dst)
        return {"music": self._music(), "name": os.path.basename(dst)}

    def pick_font(self):
        res = self._dialog("open", ("Шрифты (*.ttf;*.otf)",))
        if not res:
            return None
        try:
            info = style_mod.import_font(res[0])
        except Exception as e:
            return {"error": str(e)}
        return {"fonts": style_mod.list_fonts(), "name": info["name"]}

    def system_fonts(self):
        return style_mod.list_system_fonts()

    def add_system_font(self, path):
        allowed = [os.path.abspath(f["path"]) for f in style_mod.list_system_fonts()]
        if os.path.abspath(path or "") not in allowed:
            return {"error": "Шрифт не найден"}
        try:
            info = style_mod.import_font(path)
        except Exception as e:
            return {"error": str(e)}
        return {"fonts": style_mod.list_fonts(), "name": info["name"]}

    # --- processing
    def queue_remove(self, job_id):
        self._jobs.remove(job_id)

    def queue_clear_finished(self):
        self._jobs.clear_finished()

    def start(self, settings=None):
        if settings:
            self.save_settings(settings)
        os.makedirs(self._settings["out_dir"], exist_ok=True)
        return self._jobs.start()

    def pause(self):
        self._jobs.pause.set()
        print("Пауза: остановлюсь после текущего шага")

    def resume(self):
        self._jobs.pause.clear()
        print("Продолжаю")

    def cancel(self):
        self._jobs.cancel.set()
        self._jobs.pause.clear()

    def progress(self, log_since=0):
        snap = self._jobs.snapshot()
        snap["log"] = LOG.since(int(log_since or 0))
        snap["uploads"] = self._uploads.snapshot()
        return snap

    # --- clips
    def _thumb(self, out_dir, fn):
        with self._thumb_lock:
            return self._thumb_locked(out_dir, fn)

    def _thumb_locked(self, out_dir, fn):
        path = os.path.join(out_dir, fn)
        key = (path, os.path.getmtime(path))
        if key in self._thumb_cache:
            return self._thumb_cache[key]
        tdir = os.path.join(out_dir, ".thumbs")
        os.makedirs(tdir, exist_ok=True)
        jpg = os.path.join(tdir, os.path.splitext(fn)[0] + ".jpg")
        if not os.path.exists(jpg) or os.path.getmtime(jpg) < os.path.getmtime(path):
            grab_frame(path, jpg, at=None, height=480)
        uri = _data_uri(jpg, "image/jpeg") if os.path.exists(jpg) else None
        self._thumb_cache[key] = uri
        return uri

    def clips(self):
        out_dir = self._settings["out_dir"]
        items = [c for c in read_clips_index(out_dir) if os.path.exists(os.path.join(out_dir, c["file"]))]
        known = {c["file"] for c in items}
        if os.path.isdir(out_dir):  # clips made by the old version have no metadata
            for fn in os.listdir(out_dir):
                if fn.lower().endswith(".mp4") and fn not in known and not fn.startswith("temp_"):
                    p = os.path.join(out_dir, fn)
                    items.append({"file": fn, "title": os.path.splitext(fn)[0], "score": 0, "category": "",
                                  "duration": probe_duration(p), "source": "", "show": "", "episode": "",
                                  "created": os.path.getmtime(p)})
        items.sort(key=lambda c: -c.get("created", 0))
        uploaded = {u["file"]: u["status"] for u in self._uploads.items}
        for c in items:
            c["thumb"] = self._thumb(out_dir, c["file"])
            c["upload"] = uploaded.get(c["file"])
        return {"out_dir": out_dir, "items": items}

    def open_clip(self, fn):
        _open_path(os.path.join(self._settings["out_dir"], os.path.basename(fn)))

    def open_folder(self):
        os.makedirs(self._settings["out_dir"], exist_ok=True)
        _open_path(self._settings["out_dir"])

    def delete_clips(self, files):
        out_dir = self._settings["out_dir"]
        files = {os.path.basename(f) for f in files or []}
        for fn in files:
            for p in (os.path.join(out_dir, fn), os.path.join(out_dir, ".thumbs", os.path.splitext(fn)[0] + ".jpg")):
                try:
                    os.remove(p)
                except OSError:
                    pass
        index = [c for c in read_clips_index(out_dir) if c["file"] not in files]
        write_clips_index(out_dir, index)
        return True

    # --- uploads
    def yt_login(self):
        import uploader
        try:
            return {"channel": uploader.login()}
        except Exception as e:
            return {"error": str(e)}

    def upload_enqueue(self, files, start=True):
        self._uploads.enqueue(files or [])
        if start:
            self._uploads.start()
        return True

    def upload_start(self):
        self._uploads.start()

    def upload_update(self, item_id, fields):
        self._uploads.update(item_id, fields or {})
        if (fields or {}).get("retry"):
            self._uploads.start()

    def upload_remove(self, item_id):
        self._uploads.remove(item_id)

    def upload_clear_done(self):
        self._uploads.clear_done()


def _bind_drop(window, api):
    """Drag & drop of video files from Explorer onto the window."""
    try:
        from webview.dom import DOMEventHandler

        def on_drop(e):
            files = (e.get("dataTransfer") or {}).get("files") or []
            paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
            if paths:
                api._jobs.add(paths)

        window.dom.document.events.dragover += DOMEventHandler(lambda e: None, True, True)
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
    except Exception as e:
        print(f"Drag & drop unavailable: {e}")


def main():
    api = Api()
    window = webview.create_window(
        "AniBaza TikTok Studio", url=os.path.join(APP_DIR, "ui", "index.html"), js_api=api,
        width=1380, height=880, min_size=(1120, 720), background_color="#0b0b10")
    api._window = window
    webview.start(_bind_drop, (window, api), http_server=True, private_mode=False,
                  storage_path=os.path.join(APP_DIR, "_webview"))


if __name__ == "__main__":
    main()
