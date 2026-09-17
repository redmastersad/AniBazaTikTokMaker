import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import sys

# Import our processing function
from main import process_video

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("TikTok AI Video Generator")
        self.geometry("600x400")
        
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Title
        self.title_label = ctk.CTkLabel(self, text="ИИ-Генератор TikTok", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # File Selection
        self.file_frame = ctk.CTkFrame(self)
        self.file_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.file_frame.grid_columnconfigure(0, weight=1)

        self.file_path_var = ctk.StringVar()
        self.file_entry = ctk.CTkEntry(self.file_frame, textvariable=self.file_path_var, state="disabled")
        self.file_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        self.browse_btn = ctk.CTkButton(self.file_frame, text="Выбрать видео", command=self.browse_file)
        self.browse_btn.grid(row=0, column=1, padx=(5, 10), pady=10)

        # Output Selection
        self.out_frame = ctk.CTkFrame(self)
        self.out_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.out_frame.grid_columnconfigure(0, weight=1)

        self.out_path_var = ctk.StringVar(value=os.path.abspath("output"))
        self.out_entry = ctk.CTkEntry(self.out_frame, textvariable=self.out_path_var, state="disabled")
        self.out_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        self.browse_out_btn = ctk.CTkButton(self.out_frame, text="Куда сохранить", command=self.browse_output)
        self.browse_out_btn.grid(row=0, column=1, padx=(5, 10), pady=10)
        
        # Logo Selection
        self.logo_frame = ctk.CTkFrame(self)
        self.logo_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.logo_frame.grid_columnconfigure(0, weight=1)

        self.logo_path_var = ctk.StringVar(value="")
        self.logo_entry = ctk.CTkEntry(self.logo_frame, textvariable=self.logo_path_var, state="disabled", placeholder_text="Логотип PNG (необязательно)")
        self.logo_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        self.browse_logo_btn = ctk.CTkButton(self.logo_frame, text="Выбрать Логотип", command=self.browse_logo)
        self.browse_logo_btn.grid(row=0, column=1, padx=(5, 10), pady=10)

        # Status and Run
        self.status_label = ctk.CTkLabel(self, text="Готов к работе. Используется Llama 3.1 8B и Whisper GPU.")
        self.status_label.grid(row=4, column=0, padx=20, pady=10)

        self.run_btn = ctk.CTkButton(self, text="Создать TikTok 🚀", command=self.start_processing, height=40)
        self.run_btn.grid(row=5, column=0, padx=20, pady=20, sticky="ew")
        
        # Grid row config fix
        self.grid_rowconfigure(4, weight=1)

    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Выберите видеофайл",
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv")]
        )
        if filename:
            self.file_path_var.set(filename)

    def browse_output(self):
        dirname = filedialog.askdirectory(title="Выберите папку для сохранения")
        if dirname:
            self.out_path_var.set(dirname)
            
    def browse_logo(self):
        filename = filedialog.askopenfilename(
            title="Выберите PNG логотип",
            filetypes=[("PNG images", "*.png")]
        )
        if filename:
            self.logo_path_var.set(filename)

    def start_processing(self):
        video_path = self.file_path_var.get()
        out_path = self.out_path_var.get()
        logo_path = self.logo_path_var.get()

        if not video_path:
            messagebox.showerror("Ошибка", "Пожалуйста, выберите видеофайл.")
            return

        # Disable button
        self.run_btn.configure(state="disabled", text="Обработка... Смотрите консоль.")
        self.status_label.configure(text="Выполняется магия ИИ... 🪄")

        # Run in thread so GUI doesn't freeze
        threading.Thread(target=self.run_process_thread, args=(video_path, out_path, logo_path), daemon=True).start()

    def run_process_thread(self, video_path, out_path, logo_path):
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
            process_video(video_path, out_path, logo_path=logo_path if logo_path else None)
            messagebox.showinfo("Успех", "TikTok-ролики успешно созданы! Проверьте папку назначения.")
            self.status_label.configure(text="Готово!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Произошла ошибка:\n{e}")
            self.status_label.configure(text="Ошибка обработки.")
        finally:
            sys.stdout = old_stdout
            self.run_btn.configure(state="normal", text="Создать TikTok 🚀")

if __name__ == "__main__":
    app = App()
    app.mainloop()
