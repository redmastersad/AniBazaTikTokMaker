import os
import sys
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS_FILE = "client_secret.json"
TOKEN_FILE = "token.json"

class YouTubeUploaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Загрузчик YouTube Shorts")
        self.geometry("600x550")
        
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        self.creds = None
        self.youtube = None

        # Title
        self.title_label = ctk.CTkLabel(self, text="Загрузка видео на YouTube", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Auth Frame
        self.auth_frame = ctk.CTkFrame(self)
        self.auth_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        
        self.auth_status_label = ctk.CTkLabel(self.auth_frame, text="Аккаунт: Не авторизован ❌")
        self.auth_status_label.grid(row=0, column=0, padx=10, pady=10)
        
        self.auth_btn = ctk.CTkButton(self.auth_frame, text="Войти в Google", command=self.authenticate)
        self.auth_btn.grid(row=0, column=1, padx=10, pady=10)

        # File Selection Frame
        self.file_frame = ctk.CTkFrame(self)
        self.file_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.file_frame.grid_columnconfigure(0, weight=1)

        self.file_path_var = ctk.StringVar()
        self.file_entry = ctk.CTkEntry(self.file_frame, textvariable=self.file_path_var, state="disabled", placeholder_text="Выберите видео...")
        self.file_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        self.browse_btn = ctk.CTkButton(self.file_frame, text="Обзор", command=self.browse_file)
        self.browse_btn.grid(row=0, column=1, padx=(5, 10), pady=10)

        # Meta Info Frame
        self.meta_frame = ctk.CTkFrame(self)
        self.meta_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.meta_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.meta_frame, text="Название видео (обязательно):").grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        self.title_var = ctk.StringVar(value="#shorts Эпичный момент из аниме!")
        self.title_entry = ctk.CTkEntry(self.meta_frame, textvariable=self.title_var)
        self.title_entry.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(self.meta_frame, text="Описание:").grid(row=2, column=0, padx=10, pady=(10, 0), sticky="w")
        self.desc_textbox = ctk.CTkTextbox(self.meta_frame, height=80)
        self.desc_textbox.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.desc_textbox.insert("0.0", "Невероятный момент! Обязательно посмотрите до конца. #аниме #shorts #нарезки")

        # Upload Button
        self.status_label = ctk.CTkLabel(self, text="Ожидание действий...")
        self.status_label.grid(row=4, column=0, padx=20, pady=5)

        self.upload_btn = ctk.CTkButton(self, text="Загрузить на YouTube 🚀", command=self.start_upload, height=40, state="disabled")
        self.upload_btn.grid(row=5, column=0, padx=20, pady=20, sticky="ew")

        # Check existing token on startup
        self.check_auth()

    def check_auth(self):
        if os.path.exists(TOKEN_FILE):
            try:
                self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                self.youtube = build("youtube", "v3", credentials=self.creds)
                self.auth_status_label.configure(text="Аккаунт: Авторизован ✅")
                self.auth_btn.configure(text="Сменить аккаунт")
                self.upload_btn.configure(state="normal")
            except Exception as e:
                print(f"Auth error: {e}")
                self.creds = None

    def authenticate(self):
        if not os.path.exists(CLIENT_SECRETS_FILE):
            msg = (
                "Файл client_secret.json не найден!\n\n"
                "Чтобы получить его:\n"
                "1. Зайдите в Google Cloud Console.\n"
                "2. Создайте проект и включите 'YouTube Data API v3'.\n"
                "3. Настройте Экран согласия OAuth (OAuth consent screen).\n"
                "4. Создайте учетные данные 'OAuth client ID' (тип 'Desktop App').\n"
                "5. Скачайте JSON-файл, переименуйте его в 'client_secret.json' и положите в папку с программой."
            )
            messagebox.showerror("Ошибка авторизации", msg)
            return

        try:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            self.creds = flow.run_local_server(port=0)
            
            with open(TOKEN_FILE, "w") as token:
                token.write(self.creds.to_json())
                
            self.youtube = build("youtube", "v3", credentials=self.creds)
            self.auth_status_label.configure(text="Аккаунт: Авторизован ✅")
            self.auth_btn.configure(text="Сменить аккаунт")
            self.upload_btn.configure(state="normal")
            messagebox.showinfo("Успех", "Вы успешно авторизовались!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось авторизоваться:\n{e}")

    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Выберите видео",
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv")]
        )
        if filename:
            self.file_path_var.set(filename)

    def start_upload(self):
        video_path = self.file_path_var.get()
        title = self.title_var.get()
        description = self.desc_textbox.get("0.0", "end").strip()

        if not video_path:
            messagebox.showerror("Ошибка", "Выберите видео для загрузки!")
            return
        if not title:
            messagebox.showerror("Ошибка", "Название видео обязательно!")
            return
        if not self.youtube:
            messagebox.showerror("Ошибка", "Сначала авторизуйтесь в Google!")
            return

        self.upload_btn.configure(state="disabled", text="Идет загрузка... Пожалуйста, подождите.")
        self.status_label.configure(text="Загрузка началась. Это может занять несколько минут.")
        
        threading.Thread(target=self.upload_thread, args=(video_path, title, description), daemon=True).start()

    def upload_thread(self, video_path, title, description):
        try:
            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": ["shorts", "anime", "tiktok"],
                    "categoryId": "24" # Entertainment
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

            request = self.youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    self.status_label.configure(text=f"Загружено: {progress}%...")

            self.status_label.configure(text="Загрузка завершена! ✅")
            messagebox.showinfo("Успех", f"Видео успешно загружено на YouTube!\n\nID видео: {response['id']}")
            
        except HttpError as e:
            err_msg = f"HTTP Error {e.resp.status}:\n{e.content.decode('utf-8')}"
            self.status_label.configure(text="Ошибка загрузки.")
            messagebox.showerror("Ошибка YouTube API", err_msg)
        except Exception as e:
            self.status_label.configure(text="Ошибка загрузки.")
            messagebox.showerror("Ошибка", f"Произошла ошибка:\n{e}")
        finally:
            self.upload_btn.configure(state="normal", text="Загрузить на YouTube 🚀")

if __name__ == "__main__":
    app = YouTubeUploaderApp()
    app.mainloop()
