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
        self.title_label = ctk.CTkLabel(self, text="TikTok AI Generator", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=(20, 10))

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

        # Language Selection
        self.lang_frame = ctk.CTkFrame(self)
        self.lang_frame.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        self.lang_frame.grid_columnconfigure(0, weight=1)

        self.lang_var = ctk.StringVar(value="en")
        
        self.lang_label = ctk.CTkLabel(self.lang_frame, text="Video Language:")
        self.lang_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        
        self.lang_en_rb = ctk.CTkRadioButton(self.lang_frame, text="English", variable=self.lang_var, value="en")
        self.lang_en_rb.grid(row=0, column=1, padx=5, pady=10, sticky="w")
        
        self.lang_ru_rb = ctk.CTkRadioButton(self.lang_frame, text="Russian", variable=self.lang_var, value="ru")
        self.lang_ru_rb.grid(row=0, column=2, padx=5, pady=10, sticky="w")

        # Status and Run
        self.status_label = ctk.CTkLabel(self, text="Ready. Using Llama 3.1 8B and Whisper GPU.")
        self.status_label.grid(row=5, column=0, padx=20, pady=10)

        self.run_btn = ctk.CTkButton(self, text="Generate Video", command=self.start_processing, height=40)
        self.run_btn.grid(row=6, column=0, padx=20, pady=20, sticky="ew")
        
        # Grid row config fix
        self.grid_rowconfigure(5, weight=1)

    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv")]
        )
        if filename:
            self.file_path_var.set(filename)

    def browse_output(self):
        dirname = filedialog.askdirectory(title="Select Output Directory")
        if dirname:
            self.out_path_var.set(dirname)
            
    def browse_logo(self):
        filename = filedialog.askopenfilename(
            title="Select PNG Logo",
            filetypes=[("PNG images", "*.png")]
        )
        if filename:
            self.logo_path_var.set(filename)

    def start_processing(self):
        video_path = self.file_path_var.get()
        out_path = self.out_path_var.get()
        logo_path = self.logo_path_var.get()
        lang = self.lang_var.get()

        if not video_path:
            messagebox.showerror("Error", "Please select a video file.")
            return

        # Disable button
        self.run_btn.configure(state="disabled", text="Processing... Check console.")
        self.status_label.configure(text="Processing with AI...")

        # Run in thread so GUI doesn't freeze
        threading.Thread(target=self.run_process_thread, args=(video_path, out_path, logo_path, lang), daemon=True).start()

    def run_process_thread(self, video_path, out_path, logo_path, lang):
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
            process_video(video_path, out_path, logo_path=logo_path if logo_path else None, language=lang)
            messagebox.showinfo("Success", "Videos generated successfully. Check the output directory.")
            self.status_label.configure(text="Completed.")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred:\n{e}")
            self.status_label.configure(text="Processing error.")
        finally:
            sys.stdout = old_stdout
            self.run_btn.configure(state="normal", text="Generate Video")

if __name__ == "__main__":
    app = App()
    app.mainloop()
