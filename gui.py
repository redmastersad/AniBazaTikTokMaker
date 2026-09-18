import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import sys
from PIL import Image

# Import our processing function
from main import process_video

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AniBaza TikTok AI Generator")
        self.geometry("600x640")
        
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("dark-blue") # More beautiful theme
        self.configure(fg_color="#1F4037")

        self.logos_dir = os.path.abspath(os.path.join("Assets", "Logo"))
        self.music_dir = os.path.abspath(os.path.join("Assets", "Music"))
        os.makedirs(self.logos_dir, exist_ok=True)
        os.makedirs(self.music_dir, exist_ok=True)

        # Try to load the logo image
        self.logo_img = None
        png_files = [f for f in os.listdir(self.logos_dir) if f.lower().endswith('.png')]
        if png_files:
            try:
                logo_path = os.path.join(self.logos_dir, png_files[0])
                pil_image = Image.open(logo_path)
                w, h = pil_image.size
                ratio = 50.0 / h
                new_w = int(w * ratio)
                self.logo_img = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(new_w, 50))
            except Exception as e:
                print("Could not load logo image:", e)

        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(7, weight=1)

        # Header frame
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.header_frame.grid_columnconfigure(0, weight=1)
        
        # Title (if logo is loaded, we hide the text to prevent overlap)
        self.title_label = ctk.CTkLabel(
            self.header_frame, 
            text="AniBaza AI Generator" if not self.logo_img else "", 
            font=ctk.CTkFont(size=24, weight="bold"),
            image=self.logo_img,
            compound="left"
        )
        self.title_label.grid(row=0, column=0, sticky="w")
        
        # UI Language Switch
        self.ui_lang_var = ctk.StringVar(value="EN")
        self.lang_switch = ctk.CTkSegmentedButton(self.header_frame, values=["EN", "RU"], variable=self.ui_lang_var, command=self.change_language)
        self.lang_switch.grid(row=0, column=1, sticky="e")

        # File Selection
        self.file_frame = ctk.CTkFrame(self)
        self.file_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.file_frame.grid_columnconfigure(0, weight=1)

        self.file_path_var = ctk.StringVar()
        self.file_entry = ctk.CTkEntry(self.file_frame, textvariable=self.file_path_var, state="disabled")
        self.file_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        self.browse_btn = ctk.CTkButton(self.file_frame, text="Select Video", command=self.browse_file)
        self.browse_btn.grid(row=0, column=1, padx=(5, 10), pady=10)

        # Output Selection
        self.out_frame = ctk.CTkFrame(self)
        self.out_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.out_frame.grid_columnconfigure(0, weight=1)

        self.out_path_var = ctk.StringVar(value=os.path.abspath("output"))
        self.out_entry = ctk.CTkEntry(self.out_frame, textvariable=self.out_path_var, state="disabled")
        self.out_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        self.browse_out_btn = ctk.CTkButton(self.out_frame, text="Select Output", command=self.browse_output)
        self.browse_out_btn.grid(row=0, column=1, padx=(5, 10), pady=10)
        
        # Logo Selection
        self.logo_frame = ctk.CTkFrame(self)
        self.logo_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.logo_frame.grid_columnconfigure(0, weight=1)

        self.logo_var = ctk.StringVar(value="None")
        logo_files = ["None"] + [f for f in os.listdir(self.logos_dir) if f.lower().endswith('.png')]
        self.logo_menu = ctk.CTkOptionMenu(self.logo_frame, values=logo_files, variable=self.logo_var)
        self.logo_menu.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        self.browse_logo_btn = ctk.CTkButton(self.logo_frame, text="Select Logo", command=self.browse_logo)
        self.browse_logo_btn.grid(row=0, column=1, padx=(5, 10), pady=10)

        # Music Selection
        self.music_frame = ctk.CTkFrame(self)
        self.music_frame.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        self.music_frame.grid_columnconfigure(0, weight=1)

        self.music_var = ctk.StringVar(value="None")
        music_files = ["None"] + [f for f in os.listdir(self.music_dir) if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]
        self.music_menu = ctk.CTkOptionMenu(self.music_frame, values=music_files, variable=self.music_var)
        self.music_menu.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        self.browse_music_btn = ctk.CTkButton(self.music_frame, text="Select Music", command=self.browse_music)
        self.browse_music_btn.grid(row=0, column=1, padx=(5, 10), pady=10)

        # Settings Selection
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.grid(row=5, column=0, padx=20, pady=10, sticky="ew")
        self.settings_frame.grid_columnconfigure(0, weight=1)
        
        self.remove_silence_var = ctk.BooleanVar(value=True)
        self.remove_silence_cb = ctk.CTkCheckBox(self.settings_frame, text="Cut scenes without dialogues (Jump Cuts)", variable=self.remove_silence_var)
        self.remove_silence_cb.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        # Status and Run
        self.status_label = ctk.CTkLabel(self, text="Ready. Using Llama 3.1 8B and Whisper GPU.")
        self.status_label.grid(row=6, column=0, padx=20, pady=10)

        self.run_btn = ctk.CTkButton(self, text="Generate Video", command=self.start_processing, height=40)
        self.run_btn.grid(row=7, column=0, padx=20, pady=10, sticky="ew")
        
        # Watermark
        self.watermark_label = ctk.CTkLabel(self, text="EXCLUSIVELY DEVELOPED FOR ANIBAZA", text_color="gray", font=ctk.CTkFont(size=10, weight="bold"))
        self.watermark_label.grid(row=8, column=0, pady=(0, 10))
        
    def change_language(self, choice):
        if choice == "RU":
            self.title("Генератор AniBaza TikTok ИИ")
            self.title_label.configure(text="Генератор AniBaza ИИ" if not self.logo_img else "")
            self.browse_btn.configure(text="Выбрать Видео")
            self.browse_out_btn.configure(text="Выбрать Папку")
            self.browse_logo_btn.configure(text="Выбрать Лого")
            self.browse_music_btn.configure(text="Выбрать Музыку")
            self.remove_silence_cb.configure(text="Обрезать сцены без диалогов (Jump Cuts)")
            self.run_btn.configure(text="Сгенерировать Видео")
            self.watermark_label.configure(text="СОЗДАНО СПЕЦИАЛЬНО ДЛЯ ANIBAZA")
            if "Ready" in self.status_label.cget("text"):
                self.status_label.configure(text="Готово. Используется Llama 3.1 8B и Whisper GPU.")
        else:
            self.title("AniBaza TikTok AI Generator")
            self.title_label.configure(text="AniBaza AI Generator" if not self.logo_img else "")
            self.browse_btn.configure(text="Select Video")
            self.browse_out_btn.configure(text="Select Output")
            self.browse_logo_btn.configure(text="Select Logo")
            self.browse_music_btn.configure(text="Select Music")
            self.remove_silence_cb.configure(text="Cut scenes without dialogues (Jump Cuts)")
            self.run_btn.configure(text="Generate Video")
            self.watermark_label.configure(text="EXCLUSIVELY DEVELOPED FOR ANIBAZA")
            if "Готово" in self.status_label.cget("text"):
                self.status_label.configure(text="Ready. Using Llama 3.1 8B and Whisper GPU.")

    def browse_file(self):
        title = "Select Video File" if self.ui_lang_var.get() == "EN" else "Выберите Видеофайл"
        filename = filedialog.askopenfilename(
            title=title,
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv")]
        )
        if filename:
            self.file_path_var.set(filename)

    def browse_output(self):
        title = "Select Output Directory" if self.ui_lang_var.get() == "EN" else "Выберите Папку"
        dirname = filedialog.askdirectory(title=title)
        if dirname:
            self.out_path_var.set(dirname)
            
    def browse_logo(self):
        title = "Select PNG Logo" if self.ui_lang_var.get() == "EN" else "Выберите PNG Логотип"
        filename = filedialog.askopenfilename(
            title=title,
            filetypes=[("PNG images", "*.png")]
        )
        if filename:
            current_values = self.logo_menu.cget("values")
            if filename not in current_values:
                self.logo_menu.configure(values=current_values + [filename])
            self.logo_var.set(filename)

    def browse_music(self):
        title = "Select Music File" if self.ui_lang_var.get() == "EN" else "Выберите Музыкальный Файл"
        filename = filedialog.askopenfilename(
            title=title,
            filetypes=[("Audio files", "*.mp3 *.wav *.m4a *.aac")]
        )
        if filename:
            current_values = self.music_menu.cget("values")
            if filename not in current_values:
                self.music_menu.configure(values=current_values + [filename])
            self.music_var.set(filename)

    def start_processing(self):
        video_path = self.file_path_var.get()
        out_path = self.out_path_var.get()
        
        logo_val = self.logo_var.get()
        logo_path = None
        if logo_val != "None":
            if os.path.exists(logo_val):
                logo_path = logo_val
            else:
                logo_path = os.path.join(self.logos_dir, logo_val)
                
        music_val = self.music_var.get()
        music_path = None
        if music_val != "None":
            if os.path.exists(music_val):
                music_path = music_val
            else:
                music_path = os.path.join(self.music_dir, music_val)
                
        remove_silence = self.remove_silence_var.get()

        if not video_path:
            err_msg = "Please select a video file." if self.ui_lang_var.get() == "EN" else "Пожалуйста, выберите видеофайл."
            err_title = "Error" if self.ui_lang_var.get() == "EN" else "Ошибка"
            messagebox.showerror(err_title, err_msg)
            return

        # Disable button
        if self.ui_lang_var.get() == "RU":
            self.run_btn.configure(state="disabled", text="Обработка... Смотрите консоль.")
            self.status_label.configure(text="Обработка с помощью ИИ...")
        else:
            self.run_btn.configure(state="disabled", text="Processing... Check console.")
            self.status_label.configure(text="Processing with AI...")

        # Run in thread so GUI doesn't freeze
        threading.Thread(target=self.run_process_thread, args=(video_path, out_path, logo_path, music_path, remove_silence), daemon=True).start()

    def run_process_thread(self, video_path, out_path, logo_path, music_path, remove_silence):
        class StdoutRedirector:
            def __init__(self, app):
                self.app = app
            def write(self, msg):
                if msg.strip():
                    self.app.status_label.configure(text=msg.strip()[-50:]) # Show last part of message
                sys.__stdout__.write(msg)
            def flush(self):
                sys.__stdout__.flush()
                
        # Redirect stdout to update status label (simple approach)
        old_stdout = sys.stdout
        sys.stdout = StdoutRedirector(self)
        
        try:
            process_video(video_path, out_path, logo_path=logo_path, music_path=music_path, remove_silence=remove_silence)
            
            if self.ui_lang_var.get() == "RU":
                messagebox.showinfo("Успех", "Видео успешно созданы. Проверьте папку вывода.")
                self.status_label.configure(text="Завершено.")
            else:
                messagebox.showinfo("Success", "Videos generated successfully. Check the output directory.")
                self.status_label.configure(text="Completed.")
        except Exception as e:
            if self.ui_lang_var.get() == "RU":
                messagebox.showerror("Ошибка", f"Произошла ошибка:\n{e}")
                self.status_label.configure(text="Ошибка обработки.")
            else:
                messagebox.showerror("Error", f"An error occurred:\n{e}")
                self.status_label.configure(text="Processing error.")
        finally:
            sys.stdout = old_stdout
            if self.ui_lang_var.get() == "RU":
                self.run_btn.configure(state="normal", text="Сгенерировать Видео")
            else:
                self.run_btn.configure(state="normal", text="Generate Video")

if __name__ == "__main__":
    app = App()
    app.mainloop()
