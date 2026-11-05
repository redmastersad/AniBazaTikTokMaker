"""TikTok Content Posting API client (official API, no browser robot).

Login: TikTok Login Kit for Desktop (OAuth 2 + PKCE, redirect to http://127.0.0.1:<port>/callback/).
Upload: FILE_UPLOAD in chunks, either to the creator's TikTok inbox (draft, scope video.upload)
or as a direct post (scope video.publish).

Docs: https://developers.tiktok.com/doc/content-posting-api-get-started
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import secrets
import socketserver
import threading
import time
import urllib.parse
import webbrowser

import requests

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "tiktok_config.json")   # client_key / client_secret
TOKEN_FILE = os.path.join(APP_DIR, "tiktok_token.json")     # access / refresh token

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"
SCOPES = "user.info.basic,video.upload,video.publish"
REDIRECT_PORT = 3455
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback/"

MB = 1024 * 1024
MIN_CHUNK = 5 * MB
CHUNK = 10 * MB          # 5..64 MB allowed; the last chunk takes the remainder (up to 128 MB)

PRIVACY_NAMES = {
    "PUBLIC_TO_EVERYONE": "всем",
    "MUTUAL_FOLLOW_FRIENDS": "друзьям",
    "FOLLOWER_OF_CREATOR": "подписчикам",
    "SELF_ONLY": "только мне",
}


class TikTokError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


# ---------------------------------------------------------------- config / token files

def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_json(path: str, data: dict) -> None:
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_keys() -> tuple[str, str]:
    """client_key / client_secret from .env (TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET) or tiktok_config.json."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(APP_DIR, ".env"))
    except ImportError:
        pass
    cfg = _read_json(CONFIG_FILE)
    key = os.getenv("TIKTOK_CLIENT_KEY") or cfg.get("client_key", "")
    secret = os.getenv("TIKTOK_CLIENT_SECRET") or cfg.get("client_secret", "")
    return key.strip(), secret.strip()


def save_keys(key: str, secret: str) -> None:
    cfg = _read_json(CONFIG_FILE)
    cfg.update(client_key=key.strip(), client_secret=secret.strip())
    _write_json(CONFIG_FILE, cfg)


# ---------------------------------------------------------------- OAuth

def _wait_for_code(state: str, timeout: int = 300) -> str:
    result: dict = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if not self.path.startswith("/callback"):
                self.send_response(404)
                self.end_headers()
                return
            if q.get("state", [""])[0] != state:
                result["error"] = "state_mismatch"
            elif "error" in q:
                result["error"] = q["error"][0] + ": " + q.get("error_description", [""])[0]
            else:
                result["code"] = q.get("code", [""])[0]
            ok = "code" in result
            body = ("<h2>Готово, вход в TikTok выполнен. Окно можно закрыть.</h2>" if ok else
                    f"<h2>Ошибка входа: {result.get('error')}</h2>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<html><body style='font-family:sans-serif'>{body}</body></html>".encode())
            done.set()

        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", REDIRECT_PORT), Handler) as srv:
        srv.timeout = 1
        end = time.time() + timeout
        while not done.is_set() and time.time() < end:
            srv.handle_request()
    if "code" not in result:
        raise TikTokError("login_failed", result.get("error", "время ожидания вышло"))
    return result["code"]


def login(key: str, secret: str) -> dict:
    """Opens the browser for TikTok login and stores the token. Returns the token dict."""
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = hashlib.sha256(verifier.encode()).hexdigest()   # TikTok desktop wants HEX, not base64url
    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_key": key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    print("Открываю браузер для входа в TikTok…\nЕсли не открылся, скопируй ссылку:\n" + url + "\n")
    webbrowser.open(url)
    code = _wait_for_code(state)
    r = requests.post(f"{API}/oauth/token/", data={
        "client_key": key,
        "client_secret": secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }, timeout=30)
    return _store_token(r)


def _store_token(r: requests.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        raise TikTokError(f"http_{r.status_code}", r.text[:300])
    if "access_token" not in data:
        raise TikTokError(data.get("error", f"http_{r.status_code}"), data.get("error_description", ""))
    now = time.time()
    tok = {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "open_id": data.get("open_id", ""),
        "scope": data.get("scope", ""),
        "expires_at": now + int(data.get("expires_in", 86400)) - 120,
        "refresh_expires_at": now + int(data.get("refresh_expires_in", 365 * 86400)) - 120,
    }
    _write_json(TOKEN_FILE, tok)
    return tok


def get_token(key: str, secret: str, force_login: bool = False, interactive: bool = True) -> dict:
    """Saved token, refreshed if expired; logs in again (interactive) when the refresh token is dead."""
    tok = {} if force_login else _read_json(TOKEN_FILE)
    if tok and time.time() < tok.get("expires_at", 0):
        return tok
    if tok and time.time() < tok.get("refresh_expires_at", 0):
        r = requests.post(f"{API}/oauth/token/", data={
            "client_key": key,
            "client_secret": secret,
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
        }, timeout=30)
        try:
            return _store_token(r)
        except TikTokError as e:
            print(f"Токен не обновился ({e}), нужен новый вход.")
    if not interactive:
        raise TikTokError("login_needed", "войди в TikTok заново")
    return login(key, secret)


def logout() -> None:
    try:
        os.remove(TOKEN_FILE)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------- API calls

class Client:
    def __init__(self, token: dict):
        self.token = token

    def _post(self, path: str, body: dict | None = None) -> dict:
        for attempt in range(4):
            r = requests.post(f"{API}{path}", json=body or {}, timeout=60, headers={
                "Authorization": f"Bearer {self.token['access_token']}",
                "Content-Type": "application/json; charset=UTF-8",
            })
            if r.status_code == 429:          # 6 init requests per minute per user
                time.sleep(20 * (attempt + 1))
                continue
            try:
                data = r.json()
            except ValueError:
                raise TikTokError(f"http_{r.status_code}", r.text[:300])
            err = data.get("error") or {}
            if err.get("code") not in (None, "", "ok"):
                raise TikTokError(err.get("code"), err.get("message", ""))
            return data.get("data") or {}
        raise TikTokError("rate_limit_exceeded", "TikTok просит подождать")

    def creator_info(self) -> dict:
        return self._post("/post/publish/creator_info/query/")

    @staticmethod
    def _source_info(size: int) -> dict:
        # Up to 64 MB TikTok wants ONE chunk equal to the whole file (chunk_size == video_size):
        # a single chunk bigger than chunk_size is rejected with «The chunk size is invalid».
        if size <= 64_000_000:
            return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
        count = size // CHUNK            # ≥ 6 here; the last chunk takes the remainder (< 2 × CHUNK)
        return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": CHUNK, "total_chunk_count": count}

    def init_upload(self, path: str, post_info: dict | None) -> tuple[str, str, dict]:
        """post_info=None → draft into the TikTok inbox; otherwise a direct post."""
        src = self._source_info(os.path.getsize(path))
        if post_info is None:
            data = self._post("/post/publish/inbox/video/init/", {"source_info": src})
        else:
            data = self._post("/post/publish/video/init/", {"post_info": post_info, "source_info": src})
        return data["publish_id"], data["upload_url"], src

    @staticmethod
    def put_file(path: str, upload_url: str, src: dict, progress=None) -> None:
        size, chunk, count = src["video_size"], src["chunk_size"], src["total_chunk_count"]
        ctype = {".mov": "video/quicktime", ".webm": "video/webm"}.get(os.path.splitext(path)[1].lower(), "video/mp4")
        with open(path, "rb") as f:
            for i in range(count):
                first = i * chunk
                last = size - 1 if i == count - 1 else first + chunk - 1
                f.seek(first)
                blob = f.read(last - first + 1)
                for attempt in range(4):
                    try:
                        r = requests.put(upload_url, data=blob, timeout=300, headers={
                            "Content-Type": ctype,
                            "Content-Length": str(len(blob)),
                            "Content-Range": f"bytes {first}-{last}/{size}",
                        })
                        if r.status_code in (200, 201, 206):
                            break
                        if r.status_code < 500:
                            raise TikTokError(f"upload_http_{r.status_code}", r.text[:300])
                    except requests.RequestException as e:
                        if attempt == 3:
                            raise TikTokError("upload_network", str(e))
                    time.sleep(3 * (attempt + 1))
                else:
                    raise TikTokError("upload_failed", f"кусок {i + 1}/{count}")
                if progress:
                    progress(last + 1, size)

    def status(self, publish_id: str) -> dict:
        return self._post("/post/publish/status/fetch/", {"publish_id": publish_id})

    def wait(self, publish_id: str, timeout: int = 600) -> dict:
        """Waits until TikTok has the video (inbox) or posted it. Returns the last status."""
        end = time.time() + timeout
        st: dict = {}
        while time.time() < end:
            st = self.status(publish_id)
            s = st.get("status")
            if s in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
                return st
            if s == "FAILED":
                raise TikTokError(st.get("fail_reason") or "FAILED", "TikTok не принял видео")
            time.sleep(5)
        return st
