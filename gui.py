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
        self.geometry("600x450")
        
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        # Header frame
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.header_frame.grid_columnconfigure(0, weight=1)
        
        # Title
        self.title_label = ctk.CTkLabel(self.header_frame, text="TikTok AI Generator", font=ctk.CTkFont(size=24, weight="bold"))
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

        self.logo_path_var = ctk.StringVar(value="")
        self.logo_entry = ctk.CTkEntry(self.logo_frame, textvariable=self.logo_path_var, state="disabled", placeholder_text="PNG Logo (Optional)")
        self.logo_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        self.browse_logo_btn = ctk.CTkButton(self.logo_frame, text="Select Logo", command=self.browse_logo)
        self.browse_logo_btn.grid(row=0, column=1, padx=(5, 10), pady=10)

        # Status and Run
        self.status_label = ctk.CTkLabel(self, text="Ready. Using Llama 3.1 8B and Whisper GPU.")
        self.status_label.grid(row=4, column=0, padx=20, pady=10)

        self.run_btn = ctk.CTkButton(self, text="Generate Video", command=self.start_processing, height=40)
        self.run_btn.grid(row=5, column=0, padx=20, pady=20, sticky="ew")
        
    def change_language(self, choice):
        if choice == "RU":
            self.title("Генератор TikTok ИИ")
            self.title_label.configure(text="Генератор TikTok ИИ")
            self.browse_btn.configure(text="Выбрать Видео")
            self.browse_out_btn.configure(text="Выбрать Папку")
            self.browse_logo_btn.configure(text="Выбрать Лого")
            self.logo_entry.configure(placeholder_text="PNG Логотип (Опционально)")
            self.run_btn.configure(text="Сгенерировать Видео")
            if "Ready" in self.status_label.cget("text"):
                self.status_label.configure(text="Готово. Используется Llama 3.1 8B и Whisper GPU.")
        else:
            self.title("TikTok AI Video Generator")
            self.title_label.configure(text="TikTok AI Generator")
            self.browse_btn.configure(text="Select Video")
            self.browse_out_btn.configure(text="Select Output")
            self.browse_logo_btn.configure(text="Select Logo")
            self.logo_entry.configure(placeholder_text="PNG Logo (Optional)")
            self.run_btn.configure(text="Generate Video")
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
            self.logo_path_var.set(filename)

    def start_processing(self):
        video_path = self.file_path_var.get()
        out_path = self.out_path_var.get()
        logo_path = self.logo_path_var.get()

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
