import os
import sys
import threading
import time
import queue
import customtkinter as ctk
from tkinter import filedialog, messagebox
from playwright.sync_api import sync_playwright

USER_DATA_DIR = os.path.join(os.getcwd(), "youtube_profile")

class YouTubeUploaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Загрузчик YouTube Shorts (Бот-браузер)")
        self.geometry("600x550")
        
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        # Title
        self.title_label = ctk.CTkLabel(self, text="Загрузка видео на YouTube", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Auth Frame
        self.auth_frame = ctk.CTkFrame(self)
        self.auth_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        
        self.auth_status_label = ctk.CTkLabel(self.auth_frame, text="Вам нужно один раз зайти в аккаунт через браузер 👇")
        self.auth_status_label.grid(row=0, column=0, padx=10, pady=10)
        
        self.auth_btn = ctk.CTkButton(self.auth_frame, text="Войти в YouTube", command=self.open_login_browser)
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

        ctk.CTkLabel(self.meta_frame, text="Название видео:").grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")
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

        self.upload_btn = ctk.CTkButton(self, text="Запустить робота-загрузчика 🚀", command=self.start_upload, height=40)
        self.upload_btn.grid(row=5, column=0, padx=20, pady=20, sticky="ew")

        self.upload_queue = queue.Queue()
        # Запускаем фонового воркера для очереди
        threading.Thread(target=self.queue_worker, daemon=True).start()

    def check_auth(self):
        if os.path.exists("channel_name.txt"):
            with open("channel_name.txt", "r", encoding="utf-8") as f:
                channel = f.read().strip()
            self.auth_status_label.configure(text=f"Аккаунт: {channel} ✅")

    def open_login_browser(self):
        self.auth_btn.configure(state="disabled", text="Браузер открыт...")
        threading.Thread(target=self._login_thread, daemon=True).start()

    def _login_thread(self):
        try:
            self.status_label.configure(text="Войдите в аккаунт в открывшемся браузере...")
            print("[Логин] Запуск браузера для авторизации...")
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=False,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"]
                )
                page = browser.pages[0]
                page.goto("https://studio.youtube.com/")
                
                print("[Логин] Ожидание дэшборда канала...")
                page.wait_for_url("**/studio.youtube.com/channel/**", timeout=0)
                time.sleep(3) 
                
                try:
                    # Пытаемся вытащить имя канала из текста под аватаркой
                    channel_name = page.locator("#channel-name, ytcp-channel-name-text").first.inner_text().strip()
                except:
                    channel_name = "Ваш Канал"
                
                with open("channel_name.txt", "w", encoding="utf-8") as f:
                    f.write(channel_name)
                    
                browser.close()
                print(f"[Логин] Успех! Канал: {channel_name}")
                self.auth_status_label.configure(text=f"Аккаунт: {channel_name} ✅")
                self.status_label.configure(text="Авторизация сохранена! ✅")
        except Exception as e:
            print(f"[Логин] Ошибка: {e}")
            messagebox.showerror("Ошибка", f"Не удалось авторизоваться:\n{e}")
        finally:
            self.auth_btn.configure(state="normal", text="Войти в YouTube (Сменить)")

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

        print(f"[Очередь] Добавлено видео: {video_path}")
        self.status_label.configure(text=f"Видео добавлено в очередь! (Всего в очереди: {self.upload_queue.qsize() + 1}) 🚀")
        self.file_path_var.set("") 
        
        # Кладем задачу в очередь вместо прямого запуска потока
        self.upload_queue.put({
            'video_path': video_path,
            'title': title,
            'description': description
        })

    def queue_worker(self):
        while True:
            task = self.upload_queue.get()
            self.upload_video_task(task['video_path'], task['title'], task['description'])
            self.upload_queue.task_done()
            if self.upload_queue.empty():
                self.status_label.configure(text="Все видео из очереди загружены! ✅")

    def upload_video_task(self, video_path, title, description):
        filename = os.path.basename(video_path)
        print(f"[{filename}] Начинаем обработку...")
        self.status_label.configure(text=f"Загрузка '{filename}'...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=True,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"]
                )
                page = browser.pages[0]
                
                print(f"[{filename}] Открываем YouTube Studio...")
                page.goto("https://studio.youtube.com/")

                if "accounts.google.com" in page.url:
                    print(f"[{filename}] Ошибка: слетела авторизация.")
                    messagebox.showerror("Ошибка", f"Слетела авторизация! Видео {filename} отменено.")
                    browser.close()
                    return

                print(f"[{filename}] Нажимаем кнопку 'Создать'...")
                # Более надежные селекторы, которые ищут любую кнопку создания
                page.locator("#create-icon, a#upload-icon").first.click()
                time.sleep(1)
                page.locator("#text-item-0").click()

                print(f"[{filename}] Загружаем файл...")
                page.set_input_files("input[type='file']", video_path)
                
                print(f"[{filename}] Ждем окно ввода текста...")
                page.wait_for_selector("div#title-textarea", timeout=30000)
                time.sleep(3)

                print(f"[{filename}] Пишем название...")
                # Полностью очищаем поле перед вводом
                page.locator("div#title-textarea #textbox").first.fill("")
                page.locator("div#title-textarea #textbox").first.type(title)
                
                print(f"[{filename}] Пишем описание...")
                page.locator("div#description-textarea #textbox").first.fill("")
                page.locator("div#description-textarea #textbox").first.type(description)

                print(f"[{filename}] Ставим галочку 'Не для детей'...")
                page.locator("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']").first.click()

                print(f"[{filename}] Прокликиваем 'Далее'...")
                page.locator("#next-button").first.click()
                time.sleep(1.5)
                page.locator("#next-button").first.click()
                time.sleep(1.5)
                page.locator("#next-button").first.click()
                time.sleep(1.5)

                print(f"[{filename}] Ставим публичный доступ и публикуем...")
                page.locator("tp-yt-paper-radio-button[name='PUBLIC']").first.click()
                page.locator("#done-button").first.click()

                print(f"[{filename}] Ждем завершения...")
                page.wait_for_selector("ytcp-video-share-dialog", timeout=90000)
                time.sleep(2)
                browser.close()

            print(f"[{filename}] УСПЕХ! Видео опубликовано.")
            
        except Exception as e:
            print(f"[{filename}] ПРОИЗОШЛА ОШИБКА: {e}")
            try:
                browser.close()
            except:
                pass

if __name__ == "__main__":
    app = YouTubeUploaderApp()
    app.check_auth()
    app.mainloop()
