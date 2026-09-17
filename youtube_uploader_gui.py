import os
import sys
import threading
import time
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

    def open_login_browser(self):
        self.auth_btn.configure(state="disabled", text="Браузер открыт...")
        threading.Thread(target=self._login_thread, daemon=True).start()

    def _login_thread(self):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=False,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
                )
                page = browser.pages[0]
                page.goto("https://studio.youtube.com/")
                
                # Wait until the user closes the browser manually
                messagebox.showinfo("Авторизация", "Пожалуйста, войдите в свой аккаунт YouTube в открывшемся браузере.\n\nКогда зайдете в YouTube Studio, просто закройте браузер вручную.")
                
                page.wait_for_event("close", timeout=0)
                browser.close()
                
            self.status_label.configure(text="Авторизация сохранена! ✅")
        except Exception as e:
            print(f"Login error: {e}")
            messagebox.showerror("Ошибка", f"Не удалось открыть Chrome. Убедитесь, что Google Chrome установлен на вашем компьютере!\n\nОшибка: {e}")
        finally:
            self.auth_btn.configure(state="normal", text="Войти в YouTube")

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

        self.upload_btn.configure(state="disabled", text="Робот работает... Не трогайте мышку!")
        self.status_label.configure(text="Робот открывает YouTube...")
        
        threading.Thread(target=self.upload_thread, args=(video_path, title, description), daemon=True).start()

    def upload_thread(self, video_path, title, description):
        try:
            with sync_playwright() as p:
                # We show the browser so the user can see the magic
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=False,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
                )
                page = browser.pages[0]
                page.goto("https://studio.youtube.com/")

                # Check if logged in
                if "accounts.google.com" in page.url:
                    messagebox.showerror("Ошибка", "Вы не авторизованы! Сначала нажмите 'Войти в YouTube' и залогиньтесь.")
                    browser.close()
                    return

                self.status_label.configure(text="Нажимаем кнопку создания...")
                # Click Create -> Upload Video
                page.click("ytcp-button#create-icon")
                page.click("tp-yt-paper-item#text-item-0")

                # Set file
                self.status_label.configure(text="Загружаем видео-файл...")
                page.set_input_files("input[type='file']", video_path)
                
                # Wait for upload dialog to load fully
                page.wait_for_selector("div#title-textarea", timeout=20000)
                time.sleep(2) # Extra buffer for UI animation

                # Enter Title
                self.status_label.configure(text="Пишем название и описание...")
                page.fill("div#title-textarea #textbox", title)
                
                # Enter Description
                page.fill("div#description-textarea #textbox", description)

                # Click "No, it's not made for kids"
                page.click("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']")

                # Next (Details -> Video Elements)
                self.status_label.configure(text="Проходим проверки YouTube...")
                page.click("ytcp-button#next-button")
                time.sleep(1)
                
                # Next (Video Elements -> Checks)
                page.click("ytcp-button#next-button")
                time.sleep(1)
                
                # Next (Checks -> Visibility)
                page.click("ytcp-button#next-button")
                time.sleep(1)

                # Select Public
                self.status_label.configure(text="Публикуем видео...")
                page.click("tp-yt-paper-radio-button[name='PUBLIC']")
                
                # Click Publish
                page.click("ytcp-button#done-button")

                # Wait for the confirmation dialog (meaning it's done or processing)
                page.wait_for_selector("ytcp-video-share-dialog", timeout=60000)
                
                browser.close()

            self.status_label.configure(text="Видео успешно опубликовано! ✅")
            messagebox.showinfo("Успех", "Робот успешно загрузил и опубликовал ваше видео на YouTube!")
            
        except Exception as e:
            self.status_label.configure(text="Ошибка загрузки.")
            messagebox.showerror("Ошибка робота", f"Что-то пошло не так:\n{e}\n\nВозможно, интерфейс YouTube изменился или видео слишком большое.")
        finally:
            self.upload_btn.configure(state="normal", text="Запустить робота-загрузчика 🚀")

if __name__ == "__main__":
    app = YouTubeUploaderApp()
    app.mainloop()
