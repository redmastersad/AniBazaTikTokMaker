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

        self.title("YouTube Shorts Uploader (Bot Browser)")
        self.geometry("600x550")
        
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        # Title
        self.title_label = ctk.CTkLabel(self, text="Upload Video to YouTube", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Auth Frame
        self.auth_frame = ctk.CTkFrame(self)
        self.auth_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        
        self.auth_status_label = ctk.CTkLabel(self.auth_frame, text="You need to login once via browser")
        self.auth_status_label.grid(row=0, column=0, padx=10, pady=10)
        
        self.auth_btn = ctk.CTkButton(self.auth_frame, text="Login to YouTube", command=self.open_login_browser)
        self.auth_btn.grid(row=0, column=1, padx=10, pady=10)

        # File Selection Frame
        self.file_frame = ctk.CTkFrame(self)
        self.file_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.file_frame.grid_columnconfigure(0, weight=1)

        self.file_path_var = ctk.StringVar()
        self.file_entry = ctk.CTkEntry(self.file_frame, textvariable=self.file_path_var, state="disabled", placeholder_text="Select Video...")
        self.file_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        self.browse_btn = ctk.CTkButton(self.file_frame, text="Browse", command=self.browse_file)
        self.browse_btn.grid(row=0, column=1, padx=(5, 10), pady=10)

        # Meta Info Frame
        self.meta_frame = ctk.CTkFrame(self)
        self.meta_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.meta_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.meta_frame, text="Video Title:").grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        self.title_var = ctk.StringVar(value="#shorts Epic moment!")
        self.title_entry = ctk.CTkEntry(self.meta_frame, textvariable=self.title_var)
        self.title_entry.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(self.meta_frame, text="Description:").grid(row=2, column=0, padx=10, pady=(10, 0), sticky="w")
        self.desc_textbox = ctk.CTkTextbox(self.meta_frame, height=80)
        self.desc_textbox.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.desc_textbox.insert("0.0", "Incredible moment! Be sure to watch to the end. #shorts #highlights")

        # Upload Button
        self.status_label = ctk.CTkLabel(self, text="Waiting for actions...")
        self.status_label.grid(row=4, column=0, padx=20, pady=5)

        self.upload_btn = ctk.CTkButton(self, text="Start Upload Robot", command=self.start_upload, height=40)
        self.upload_btn.grid(row=5, column=0, padx=20, pady=20, sticky="ew")

        self.upload_queue = queue.Queue()
        # Start background queue worker
        threading.Thread(target=self.queue_worker, daemon=True).start()

    def check_auth(self):
        if os.path.exists("channel_name.txt"):
            with open("channel_name.txt", "r", encoding="utf-8") as f:
                channel = f.read().strip()
            self.auth_status_label.configure(text=f"Account: {channel}")

    def open_login_browser(self):
        self.auth_btn.configure(state="disabled", text="Browser is open...")
        threading.Thread(target=self._login_thread, daemon=True).start()

    def _login_thread(self):
        try:
            self.status_label.configure(text="Please log in to your account in the opened browser...")
            print("[Login] Starting browser for authorization...")
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=False,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"]
                )
                page = browser.pages[0]
                page.goto("https://studio.youtube.com/")
                
                print("[Login] Waiting for channel dashboard...")
                page.wait_for_url("**/studio.youtube.com/channel/**", timeout=0)
                
                print("[Login] Waiting for page elements to load...")
                try:
                    page.wait_for_selector("#channel-name", timeout=15000)
                    channel_name = page.locator("#channel-name").first.inner_text().strip()
                except Exception as e:
                    print(f"[Login] Failed to parse channel name: {e}")
                    channel_name = "Successful login"
                
                with open("channel_name.txt", "w", encoding="utf-8") as f:
                    f.write(channel_name)
                    
                browser.close()
                print(f"[Login] Success! Channel: {channel_name}")
                self.auth_status_label.configure(text=f"Account: {channel_name}")
                self.status_label.configure(text="Authorization saved.")
        except Exception as e:
            print(f"[Login] Error: {e}")
            messagebox.showerror("Error", f"Failed to authorize:\n{e}")
        finally:
            self.auth_btn.configure(state="normal", text="Login to YouTube (Change)")

    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Select Video",
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv")]
        )
        if filename:
            self.file_path_var.set(filename)

    def start_upload(self):
        video_path = self.file_path_var.get()
        title = self.title_var.get()
        description = self.desc_textbox.get("0.0", "end").strip()

        if not video_path:
            messagebox.showerror("Error", "Select a video to upload.")
            return
        if not title:
            messagebox.showerror("Error", "Video title is required.")
            return

        print(f"[Queue] Added video: {video_path}")
        self.status_label.configure(text=f"Video added to queue. (Total in queue: {self.upload_queue.qsize() + 1})")
        self.file_path_var.set("") 
        
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
                self.status_label.configure(text="All queued videos have been uploaded.")

    def upload_video_task(self, video_path, title, description):
        filename = os.path.basename(video_path)
        print(f"[{filename}] Starting processing...")
        self.status_label.configure(text=f"Uploading '{filename}'...")
        try:
            with sync_playwright() as p:
                # Use modern headless Chrome which evades YouTube detection
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=False,
                    channel="chrome",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--headless=new",
                        "--window-size=1920,1080",
                        "--mute-audio"
                    ]
                )
                page = browser.pages[0]
                
                print(f"[{filename}] Opening YouTube Studio...")
                page.goto("https://studio.youtube.com/")

                print(f"[{filename}] Waiting for interface to load...")
                page.wait_for_url("**/studio.youtube.com/channel/**", timeout=30000)

                print(f"[{filename}] Clicking 'Create' button (#create-icon)...")
                page.wait_for_selector("#create-icon", state="visible", timeout=30000)
                page.click("#create-icon")
                
                print(f"[{filename}] Selecting 'Upload video' (#text-item-0)...")
                page.wait_for_selector("tp-yt-paper-item#text-item-0", state="visible", timeout=15000)
                page.click("tp-yt-paper-item#text-item-0")

                print(f"[{filename}] Uploading file...")
                page.wait_for_selector("input[type='file']", state="attached", timeout=15000)
                page.set_input_files("input[type='file']", video_path)
                
                print(f"[{filename}] Waiting for text input window...")
                page.wait_for_selector("div#title-textarea", state="visible", timeout=30000)
                time.sleep(3)

                print(f"[{filename}] Writing title...")
                page.locator("div#title-textarea #textbox").first.fill("")
                page.locator("div#title-textarea #textbox").first.type(title, delay=10)
                
                print(f"[{filename}] Writing description...")
                page.locator("div#description-textarea #textbox").first.fill("")
                page.locator("div#description-textarea #textbox").first.type(description, delay=10)

                print(f"[{filename}] Checking 'Not for kids' box...")
                page.locator("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']").first.click()

                print(f"[{filename}] Clicking 'Next'...")
                page.locator("#next-button").first.click()
                time.sleep(2)
                page.locator("#next-button").first.click()
                time.sleep(2)
                page.locator("#next-button").first.click()
                time.sleep(2)

                print(f"[{filename}] Setting public access and publishing...")
                page.locator("tp-yt-paper-radio-button[name='PUBLIC']").first.click()
                time.sleep(1)
                page.locator("#done-button").first.click()

                print(f"[{filename}] Waiting for successful publication window...")
                page.wait_for_selector("ytcp-video-share-dialog", state="visible", timeout=120000)
                browser.close()

            print(f"[{filename}] SUCCESS! Video published.")
            
        except Exception as e:
            print(f"[{filename}] ERROR OCCURRED: {e}")
            try:
                browser.close()
            except:
                pass

if __name__ == "__main__":
    app = YouTubeUploaderApp()
    app.check_auth()
    app.mainloop()
