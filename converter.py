import customtkinter as ctk
from tkinter import filedialog
from tkinterdnd2 import TkinterDnD, DND_FILES
from PIL import Image
import subprocess
import threading
import os
import sys
import imageio_ffmpeg
import webbrowser
import re
import io
import base64
import concurrent.futures
import requests
import time

try:
    from b64 import B64_AVATAR
except ImportError:
    B64_AVATAR = None

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

def get_ffmpeg_path():
    return imageio_ffmpeg.get_ffmpeg_exe()

def time_to_seconds(time_str):
    parts = time_str.split(':')
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return 0

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        # If frozen, but we want the user to be able to drop profile.png NEXT to the exe
        return os.path.join(os.path.dirname(sys.executable), relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def get_media_info(file_path):
    cmd = [get_ffmpeg_path(), "-i", file_path]
    try:
        creationflags = 0x08000000 if sys.platform == "win32" else 0
        result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, creationflags=creationflags)
        output = result.stderr
        
        duration = "Unknown"
        dur_match = re.search(r"Duration: (\d{2}:\d{2}:\d{2})", output)
        if dur_match:
            duration = dur_match.group(1)
            
        res_match = re.search(r"Video:.*?,.*?(\d{3,4}x\d{3,4})", output)
        resolution = res_match.group(1) if res_match else "Audio Only"
        
        size_bytes = os.path.getsize(file_path)
        size_mb = size_bytes / (1024 * 1024)
        
        return f"Duration: {duration} | Res: {resolution} | Size: {size_mb:.2f} MB"
    except Exception:
        return "Info not available"

class TkinterDnD_CTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

class ConverterApp(TkinterDnD_CTk):
    def __init__(self):
        super().__init__()
        self.title("Media Converter - Dev RULE")
        self.geometry("1150x750")
        self.resizable(False, False)
        
        try:
            self.iconbitmap(get_resource_path("app_icon.ico"))
        except:
            pass
        
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.handle_drop)
        
        self.c_bg = "#0B0B10"
        self.c_panel = "#12121A"
        self.c_border = "#2A2A3A"
        self.c_purple = "#9D4EDD"
        self.c_purple_hover = "#7B2CBF" 
        self.c_cyan = "#00F0FF"
        self.c_text_gray = "#8A8A9D"
        self.c_danger = "#E63946"
        
        self.configure(fg_color=self.c_bg)
        
        self.file_paths = []
        self.output_dir = ""
        self.ffmpeg_path = get_ffmpeg_path()
        self.cancel_flag = threading.Event()
        self.active_processes = []
        self.thread_pool = None
        
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # --- 1. Top Header ---
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=30, pady=(20, 10))
        self.header_frame.grid_columnconfigure(0, weight=1)
        
        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(title_box, text="Media Converter", font=ctk.CTkFont(size=26, weight="bold"), text_color=self.c_purple).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(title_box, text="⚡ Smart FFMPEG Engine • Drag & Drop Enabled", font=ctk.CTkFont(size=12), text_color=self.c_cyan).grid(row=1, column=0, sticky="w", pady=(2,0))
        
        self.dev_box = ctk.CTkFrame(self.header_frame, fg_color=self.c_bg, border_width=1, border_color=self.c_purple, corner_radius=15)
        self.dev_box.grid(row=0, column=1, sticky="e")
        
        self.img_lbl = ctk.CTkLabel(self.dev_box, text="")
        self.img_lbl.grid(row=0, column=0, padx=(15, 10), pady=10)
        
        self.load_profile_picture()
        
        ctk.CTkLabel(self.dev_box, text="Dev RULE", font=ctk.CTkFont(size=16, weight="bold"), text_color="white").grid(row=0, column=1, padx=(0, 15), pady=10)
        ctk.CTkButton(self.dev_box, text="✖ Exit", width=60, fg_color="transparent", border_width=1, border_color=self.c_text_gray, hover_color=self.c_danger, command=self.quit).grid(row=0, column=2, padx=(0, 15), pady=10)
        
        # --- 2. Content Area ---
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=30, pady=(10, 30))
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(1, weight=0)
        
        self.sidebar_frame = ctk.CTkFrame(self.content_frame, width=120, fg_color=self.c_panel, border_width=1, border_color=self.c_border, corner_radius=15)
        self.sidebar_frame.grid(row=0, column=1, sticky="ns", padx=(20, 0))
        
        ctk.CTkLabel(self.sidebar_frame, text="MENU", font=ctk.CTkFont(size=10, weight="bold"), text_color=self.c_text_gray).grid(row=0, column=0, pady=(20, 15))
        
        self.btn_file = self.create_nav_button("File", 1, "file")
        self.btn_video = self.create_nav_button("Video", 2, "video")
        self.btn_audio = self.create_nav_button("Audio", 3, "audio")
        self.btn_info = self.create_nav_button("Info", 4, "info")
        
        self.panels_container = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.panels_container.grid(row=0, column=0, sticky="nsew")
        self.panels_container.grid_rowconfigure(0, weight=1)
        self.panels_container.grid_columnconfigure(0, weight=1)
        
        self.panel_file = self.build_file_panel()
        self.panel_video = self.build_video_panel()
        self.panel_audio = self.build_audio_panel()
        self.panel_info = self.build_info_panel()
        
        self.current_panel = self.panel_file
        self.current_panel.grid(row=0, column=0, sticky="nsew")
        self.set_active_nav("file")

    def change_theme(self, theme_name):
        old_bg, old_panel, old_purple, old_purple_hover, old_cyan = self.c_bg, self.c_panel, self.c_purple, self.c_purple_hover, self.c_cyan
        
        if theme_name == "Blood Red":
            self.c_bg, self.c_panel, self.c_purple, self.c_purple_hover, self.c_cyan = "#1a0505", "#240a0a", "#b51717", "#8c1212", "#ff3333"
        elif theme_name == "Hacker Green":
            self.c_bg, self.c_panel, self.c_purple, self.c_purple_hover, self.c_cyan = "#050f05", "#0a170a", "#17b517", "#128c12", "#33ff33"
        elif theme_name == "Cyber Purple":
            self.c_bg, self.c_panel, self.c_purple, self.c_purple_hover, self.c_cyan = "#13051a", "#1a0a24", "#e017b5", "#ad128c", "#ff33f1"
        else:
            self.c_bg, self.c_panel, self.c_purple, self.c_purple_hover, self.c_cyan = "#0B0B10", "#12121A", "#9D4EDD", "#7B2CBF", "#00F0FF"
            
        self.configure(fg_color=self.c_bg)
        
        def update_widget(w):
            try:
                if hasattr(w, 'cget'):
                    fg = w.cget("fg_color")
                    if isinstance(fg, str):
                        if fg.lower() == old_bg.lower(): w.configure(fg_color=self.c_bg)
                        elif fg.lower() == old_panel.lower(): w.configure(fg_color=self.c_panel)
                        elif fg.lower() == old_purple.lower(): w.configure(fg_color=self.c_purple)
                        
                    if hasattr(w, 'configure'):
                        if "text_color" in w.keys():
                            tc = w.cget("text_color")
                            if isinstance(tc, str) and tc.lower() == old_cyan.lower(): w.configure(text_color=self.c_cyan)
                        if "progress_color" in w.keys():
                            pc = w.cget("progress_color")
                            if isinstance(pc, str) and pc.lower() == old_cyan.lower(): w.configure(progress_color=self.c_cyan)
                            elif isinstance(pc, str) and pc.lower() == old_purple.lower(): w.configure(progress_color=self.c_purple)
                        if "hover_color" in w.keys():
                            hc = w.cget("hover_color")
                            if isinstance(hc, str) and hc.lower() == old_purple_hover.lower(): w.configure(hover_color=self.c_purple_hover)
            except Exception:
                pass
            for child in w.winfo_children():
                update_widget(child)
                
        update_widget(self)

    def load_profile_picture(self):
        img = None
        if B64_AVATAR is not None:
            try:
                img_data = base64.b64decode(B64_AVATAR)
                img = Image.open(io.BytesIO(img_data))
            except Exception:
                pass

        if img is not None:
            try:
                min_dim = min(img.size)
                left = (img.size[0] - min_dim) / 2
                top = (img.size[1] - min_dim) / 2
                img = img.crop((left, top, left + min_dim, top + min_dim))
                self.profile_img = ctk.CTkImage(light_image=img, dark_image=img, size=(40, 40))
                self.img_lbl.configure(image=self.profile_img, text="")
            except Exception:
                self.img_lbl.configure(image="", text="?", width=40, height=40, fg_color=self.c_purple, corner_radius=20)
        else:
            self.img_lbl.configure(image="", text="?", width=40, height=40, fg_color=self.c_purple, corner_radius=20)

    def handle_drop(self, event):
        files = self.tk.splitlist(event.data)
        if files:
            self.file_paths.extend(files)
            self.file_paths = list(dict.fromkeys(self.file_paths))
            self.file_label.configure(text=f"{len(self.file_paths)} Targets Added")
            
            # Show metadata for the first file
            first_file = self.file_paths[0]
            metadata = get_media_info(first_file)
            self.file_info_label.configure(text=f"First File Info: {metadata}")
            
            self.status_label.configure(text="Ready to boost", text_color=self.c_cyan)
            self.progress_bar.set(0)

    def create_nav_button(self, text, row, target):
        btn = ctk.CTkButton(self.sidebar_frame, text=text, width=90, height=60, corner_radius=12, fg_color="transparent", hover_color=self.c_border, command=lambda: self.switch_panel(target))
        btn.grid(row=row, column=0, padx=15, pady=5)
        return btn

    def switch_panel(self, target):
        self.current_panel.grid_forget()
        self.btn_file.configure(fg_color="transparent")
        self.btn_video.configure(fg_color="transparent")
        self.btn_audio.configure(fg_color="transparent")
        self.btn_info.configure(fg_color="transparent")
        
        if target == "file":
            self.current_panel = self.panel_file
            self.btn_file.configure(fg_color=self.c_purple)
        elif target == "video":
            self.current_panel = self.panel_video
            self.btn_video.configure(fg_color=self.c_purple)
        elif target == "audio":
            self.current_panel = self.panel_audio
            self.btn_audio.configure(fg_color=self.c_purple)
        elif target == "info":
            self.current_panel = self.panel_info
            self.btn_info.configure(fg_color=self.c_purple)
            
        self.current_panel.grid(row=0, column=0, sticky="nsew")

    def set_active_nav(self, target):
        self.switch_panel(target)

    # --- Panel Builders ---

    def build_file_panel(self):
        panel = ctk.CTkFrame(self.panels_container, fg_color="transparent")
        panel.grid_columnconfigure(0, weight=1)
        
        stats_box = ctk.CTkFrame(panel, fg_color=self.c_panel, border_width=1, border_color=self.c_border, corner_radius=15)
        stats_box.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        
        ctk.CTkLabel(stats_box, text="File Targets", font=ctk.CTkFont(size=14, weight="bold"), text_color="white").grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")
        self.file_label = ctk.CTkLabel(stats_box, text="0 Targets (Drag & Drop files anywhere)", font=ctk.CTkFont(size=22, weight="bold"), text_color=self.c_cyan)
        self.file_label.grid(row=1, column=0, padx=20, pady=(0, 5), sticky="w")
        
        # Metadata label
        self.file_info_label = ctk.CTkLabel(stats_box, text="Waiting for files...", font=ctk.CTkFont(size=12), text_color=self.c_text_gray)
        self.file_info_label.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="w")
        
        actions_box = ctk.CTkFrame(panel, fg_color=self.c_panel, border_width=1, border_color=self.c_border, corner_radius=15)
        actions_box.grid(row=1, column=0, sticky="nsew")
        actions_box.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(actions_box, text="Actions", font=ctk.CTkFont(size=14, weight="bold"), text_color="white").grid(row=0, column=0, padx=20, pady=10, sticky="w")
        
        # Output Directory Selector
        out_frame = ctk.CTkFrame(actions_box, fg_color="transparent")
        out_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        out_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(out_frame, text="Save Location:").grid(row=0, column=0, sticky="w", padx=(0,10))
        self.lbl_out_dir = ctk.CTkLabel(out_frame, text="Same as original file", text_color=self.c_purple)
        self.lbl_out_dir.grid(row=0, column=1, sticky="w")
        ctk.CTkButton(out_frame, text="Change Folder", width=100, command=self.select_output_dir, fg_color="#333", hover_color="#555").grid(row=0, column=2, sticky="e")
        
        btn_sel = ctk.CTkButton(actions_box, text="Browse Files Manually", font=ctk.CTkFont(weight="bold"), fg_color=self.c_purple, hover_color=self.c_purple_hover, height=45, command=self.select_files)
        btn_sel.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        
        fmt_frame = ctk.CTkFrame(actions_box, fg_color="transparent")
        fmt_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        ctk.CTkLabel(fmt_frame, text="Target Format:").grid(row=0, column=0, sticky="w")
        self.format_var = ctk.StringVar(value="mp4")
        ctk.CTkOptionMenu(fmt_frame, variable=self.format_var, values=["mp4", "mkv", "avi", "mov", "gif", "mp3", "wav", "flac"], fg_color=self.c_bg).grid(row=0, column=1, padx=10, sticky="e")
        
        self.discord_fit_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(fmt_frame, text="👾 ضغط ذكي للديسكورد (25MB)", variable=self.discord_fit_var, progress_color=self.c_purple).grid(row=0, column=2, padx=20, sticky="e")
        
        self.convert_btn = ctk.CTkButton(actions_box, text="FULL BOOST (CONVERT ALL)", font=ctk.CTkFont(weight="bold"), fg_color=self.c_danger, hover_color="#C1121F", height=45, command=self.start_conversion)
        self.convert_btn.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        
        btn_frame = ctk.CTkFrame(actions_box, fg_color="transparent")
        btn_frame.grid(row=5, column=0, padx=20, pady=(0,10), sticky="ew")
        btn_frame.grid_columnconfigure((0,1,2), weight=1)
        
        self.extract_btn = ctk.CTkButton(btn_frame, text="🎵 Extract Audio (Fast)", font=ctk.CTkFont(weight="bold"), fg_color="#FCA311", hover_color="#E5980E", text_color="black", height=35, command=lambda: self.start_conversion(audio_only=True))
        self.extract_btn.grid(row=0, column=0, padx=(0,5), sticky="ew")
        
        self.thumb_btn = ctk.CTkButton(btn_frame, text="🖼️ Extract Thumbnail", font=ctk.CTkFont(weight="bold"), fg_color="#023E8A", hover_color="#0077B6", text_color="white", height=35, command=lambda: self.start_conversion(thumbnail_only=True))
        self.thumb_btn.grid(row=0, column=1, padx=5, sticky="ew")
        
        self.cancel_btn = ctk.CTkButton(btn_frame, text="⛔ CANCEL", font=ctk.CTkFont(weight="bold"), fg_color="#333", hover_color="#555", height=35, state="disabled", command=self.cancel_conversion)
        self.cancel_btn.grid(row=0, column=2, padx=(5,0), sticky="ew")
        
        self.progress_bar = ctk.CTkProgressBar(actions_box, progress_color=self.c_cyan, fg_color=self.c_bg)
        self.progress_bar.grid(row=6, column=0, padx=20, pady=10, sticky="ew")
        self.progress_bar.set(0)
        
        self.status_label = ctk.CTkLabel(actions_box, text="Ready to boost", font=ctk.CTkFont(weight="bold"), text_color=self.c_cyan)
        self.status_label.grid(row=7, column=0, pady=10)
        
        return panel

    def build_video_panel(self):
        panel = ctk.CTkFrame(self.panels_container, fg_color=self.c_panel, border_width=1, border_color=self.c_border, corner_radius=15)
        panel.grid_columnconfigure((0,1), weight=1)
        
        header_frame = ctk.CTkFrame(panel, fg_color="transparent")
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(20, 10))
        header_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(header_frame, text="خصائص الفيديو - Video Settings", font=ctk.CTkFont(size=16, weight="bold"), text_color="white").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header_frame, text="⚡ Smart Auto-Detect PC", font=ctk.CTkFont(weight="bold"), fg_color="#FCA311", hover_color="#E5980E", text_color="black", command=self.auto_detect_hardware).grid(row=0, column=1, sticky="e")
        
        self.detect_label = ctk.CTkLabel(panel, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color=self.c_cyan)
        self.detect_label.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="w")
        
        desc_enc = "📌 المعالج (وحدة التحويل):\n• استخدم كرت الشاشة لتسريع التحويل وتقليل الضغط على الجهاز.\n• استخدم المعالج العادي (CPU) إذا واجهت أي مشاكل أو أخطاء."
        ctk.CTkLabel(panel, text=desc_enc, justify="left", text_color=self.c_text_gray, font=ctk.CTkFont(size=12)).grid(row=2, column=0, columnspan=2, padx=20, pady=(5,10), sticky="w")
        self.encoder_var = self.add_option_row(panel, "المعالج:", ["CPU (x264)", "NVIDIA (NVENC)", "AMD (AMF)", "Intel (QSV)"], 3)
        
        desc_res = "📌 أبعاد الفيديو (المقاس):\n• لتصغير حجم الملف اختر أبعاداً أقل (مثل 720p أو 480p).\n• اختر (Original) للحفاظ على المقاس الأصلي للفيديو بدون تغيير."
        ctk.CTkLabel(panel, text=desc_res, justify="left", text_color=self.c_text_gray, font=ctk.CTkFont(size=12)).grid(row=4, column=0, columnspan=2, padx=20, pady=(15,10), sticky="w")
        self.res_var = self.add_option_row(panel, "الأبعاد:", ["Original", "1920x1080", "1280x720", "854x480"], 5)
        
        trim_frame = ctk.CTkFrame(panel, fg_color="transparent")
        trim_frame.grid(row=6, column=0, columnspan=2, padx=20, pady=(15, 0), sticky="ew")
        ctk.CTkLabel(trim_frame, text="📌 قص الفيديو (اختياري):", font=ctk.CTkFont(weight="bold", size=12)).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0,5))
        
        ctk.CTkLabel(trim_frame, text="البداية:").grid(row=1, column=0, sticky="w")
        self.trim_start = ctk.CTkEntry(trim_frame, placeholder_text="00:00:00", width=80)
        self.trim_start.grid(row=1, column=1, padx=(5, 15), sticky="w")
        
        ctk.CTkLabel(trim_frame, text="النهاية:").grid(row=1, column=2, sticky="w")
        self.trim_end = ctk.CTkEntry(trim_frame, placeholder_text="00:00:00", width=80)
        self.trim_end.grid(row=1, column=3, padx=(5, 0), sticky="w")
        
        desc_qual = "📌 الجودة:\n• عالية (High) = دقة ممتازة ولكن حجم الملف سيكون كبيراً.\n• منخفضة (Low) = حجم صغير جداً يسهل إرساله ولكن الدقة أقل."
        ctk.CTkLabel(panel, text=desc_qual, justify="left", text_color=self.c_text_gray, font=ctk.CTkFont(size=12)).grid(row=7, column=0, columnspan=2, padx=20, pady=(15,10), sticky="w")
        self.qual_var = self.add_option_row(panel, "الجودة:", ["High (Lossless)", "Medium (Balanced)", "Low (Fast)"], 8)
        
        return panel
        
    def build_audio_panel(self):
        panel = ctk.CTkFrame(self.panels_container, fg_color=self.c_panel, border_width=1, border_color=self.c_border, corner_radius=15)
        panel.grid_columnconfigure((0,1), weight=1)
        
        ctk.CTkLabel(panel, text="خصائص الصوتيات - Audio Settings", font=ctk.CTkFont(size=16, weight="bold"), text_color="white").grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="w")
        
        desc_codec = "📌 صيغة الصوت:\n• صيغة AAC هي الأفضل والأكثر توافقاً للفيديوهات.\n• صيغة MP3 هي الأفضل إذا أردت تحويل المقطع لملف صوتي فقط.\n• خيار (Copy) ينسخ الصوت كما هو بدون أي تغيير وبسرعة فائقة."
        ctk.CTkLabel(panel, text=desc_codec, justify="left", text_color=self.c_text_gray, font=ctk.CTkFont(size=12)).grid(row=1, column=0, columnspan=2, padx=20, pady=(5,10), sticky="w")
        self.audio_codec_var = self.add_option_row(panel, "الصيغة:", ["AAC", "MP3", "Copy (No re-encode)"], 2)
        
        desc_bit = "📌 نقاوة الصوت:\n• (320k) هي الأعلى نقاوة وصافية جداً (جودة استوديو).\n• (128k) حجمها صغير ومناسبة جداً للمقاطع العادية والاستخدام اليومي."
        ctk.CTkLabel(panel, text=desc_bit, justify="left", text_color=self.c_text_gray, font=ctk.CTkFont(size=12)).grid(row=3, column=0, columnspan=2, padx=20, pady=(15,10), sticky="w")
        self.audio_bitrate_var = self.add_option_row(panel, "النقاوة:", ["320k", "256k", "192k", "128k"], 4)
        
        return panel

    def build_info_panel(self):
        panel = ctk.CTkFrame(self.panels_container, fg_color=self.c_panel, border_width=1, border_color=self.c_border, corner_radius=15)
        panel.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(panel, text="About The App", font=ctk.CTkFont(size=20, weight="bold"), text_color="white").grid(row=0, column=0, padx=20, pady=(30, 10), sticky="w")
        
        info_text = (
            "Dev RULE Media Converter v2.0\n\n"
            "This application uses a Smart FFMPEG Engine to process and convert\n"
            "media files automatically. Built by Dev RULE for the ultimate performance.\n\n"
            "Features:\n"
            "- Hardware Accelerated Encoding (NVENC/AMF/QSV)\n"
            "- Full Drag & Drop Support\n"
            "- Multi-thread batch processing\n"
            "- Zero-telemetry, 100% Offline"
        )
        ctk.CTkLabel(panel, text=info_text, justify="left", text_color=self.c_text_gray).grid(row=1, column=0, padx=20, pady=10, sticky="w")
        
        btn_discord = ctk.CTkButton(panel, text="Join Discord", font=ctk.CTkFont(weight="bold"), fg_color="#5865F2", hover_color="#4752C4", height=45, command=lambda: webbrowser.open("https://discord.gg/ec-1"))
        btn_discord.grid(row=2, column=0, padx=20, pady=20, sticky="w")
        
        theme_frame = ctk.CTkFrame(panel, fg_color="transparent")
        theme_frame.grid(row=3, column=0, padx=20, pady=0, sticky="ew")
        ctk.CTkLabel(theme_frame, text="🎨 Theme / ألوان البرنامج:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        self.theme_var = ctk.StringVar(value="Dark Blue (Default)")
        theme_menu = ctk.CTkOptionMenu(theme_frame, variable=self.theme_var, values=["Dark Blue (Default)", "Blood Red", "Hacker Green", "Cyber Purple"], fg_color=self.c_bg, command=self.change_theme)
        theme_menu.grid(row=0, column=1, padx=10, sticky="w")
        
        # Webhook Settings
        webhook_frame = ctk.CTkFrame(panel, fg_color="transparent")
        webhook_frame.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        
        ctk.CTkLabel(webhook_frame, text="Discord Webhook Integration", font=ctk.CTkFont(size=14, weight="bold"), text_color="white").grid(row=0, column=0, sticky="w", pady=(0, 10))
        
        self.webhook_var = ctk.BooleanVar(value=False)
        self.webhook_switch = ctk.CTkSwitch(webhook_frame, text="Upload Output to Discord (Max 25MB)", variable=self.webhook_var, progress_color=self.c_purple)
        self.webhook_switch.grid(row=1, column=0, sticky="w", pady=(0, 10))
        
        self.webhook_url = ctk.CTkEntry(webhook_frame, placeholder_text="Paste your Webhook URL here...", width=400)
        self.webhook_url.grid(row=2, column=0, sticky="w")
        
        return panel

    def add_option_row(self, parent, label_text, options, row):
        ctk.CTkLabel(parent, text=label_text, font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, padx=20, pady=5, sticky="w")
        var = ctk.StringVar(value=options[0])
        ctk.CTkOptionMenu(parent, variable=var, values=options, fg_color=self.c_bg, button_color=self.c_purple, button_hover_color=self.c_purple_hover).grid(row=row, column=1, padx=20, pady=5, sticky="e")
        return var

    # --- Logic ---
    
    def auto_detect_hardware(self):
        try:
            creationflags = 0x08000000 if sys.platform == "win32" else 0
            res = subprocess.run(["wmic", "path", "win32_videocontroller", "get", "name"], stdout=subprocess.PIPE, text=True, creationflags=creationflags)
            gpu_name = res.stdout.strip()
            
            if "NVIDIA" in gpu_name.upper():
                self.encoder_var.set("NVIDIA (NVENC)")
                self.qual_var.set("High (Lossless)")
                gpu_msg = "NVIDIA GPU Detected"
            elif "AMD" in gpu_name.upper():
                self.encoder_var.set("AMD (AMF)")
                self.qual_var.set("High (Lossless)")
                gpu_msg = "AMD GPU Detected"
            elif "INTEL" in gpu_name.upper():
                self.encoder_var.set("Intel (QSV)")
                self.qual_var.set("Medium (Balanced)")
                gpu_msg = "Intel GPU Detected"
            else:
                self.encoder_var.set("CPU (x264)")
                self.qual_var.set("Medium (Balanced)")
                gpu_msg = "Generic/CPU Detected"
                
            self.res_var.set("Original")
            if hasattr(self, "audio_codec_var"): self.audio_codec_var.set("AAC")
            if hasattr(self, "audio_bitrate_var"): self.audio_bitrate_var.set("320k")
            
            self.detect_label.configure(text=f"✅ Best Settings Applied for: {gpu_msg}")
        except Exception as e:
            self.detect_label.configure(text="⚠️ Auto-Detect failed. Fallback to CPU.")
            self.encoder_var.set("CPU (x264)")
            
    def select_output_dir(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_dir = folder
            self.lbl_out_dir.configure(text=folder)

    def select_files(self):
        paths = filedialog.askopenfilenames()
        if paths:
            self.file_paths.extend(paths)
            self.file_paths = list(dict.fromkeys(self.file_paths))
            self.file_label.configure(text=f"{len(self.file_paths)} Targets Ready")
            
            # Show metadata
            first_file = self.file_paths[0]
            metadata = get_media_info(first_file)
            self.file_info_label.configure(text=f"First File Info: {metadata}")
            
            self.status_label.configure(text="Ready to boost", text_color=self.c_cyan)
            self.progress_bar.set(0)
            
    def start_conversion(self, audio_only=False, thumbnail_only=False):
        if not self.file_paths:
            self.status_label.configure(text="No targets selected!", text_color=self.c_danger)
            return
            
        self.status_label.configure(text="Optimizing...", text_color="yellow")
        self.progress_bar.set(0)
        self.cancel_flag.clear()
        self.active_processes.clear()
        self.convert_btn.configure(state="disabled")
        self.extract_btn.configure(state="disabled")
        self.thumb_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal", fg_color=self.c_danger)
        
        threading.Thread(target=self.process_batch, args=(audio_only, thumbnail_only), daemon=True).start()
        
    def cancel_conversion(self):
        self.cancel_flag.set()
        self.status_label.configure(text="Cancelling...", text_color=self.c_danger)
        for p in self.active_processes:
            try:
                p.kill()
            except Exception:
                pass
        
    def process_batch(self, audio_only, thumbnail_only):
        total = len(self.file_paths)
        completed = 0
        
        # Max workers based on hardware, capped at 3 for stability
        workers = min(3, os.cpu_count() or 1)
        
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        
        futures = {self.thread_pool.submit(self.process_single, fp, audio_only, thumbnail_only): fp for fp in self.file_paths}
        
        for future in concurrent.futures.as_completed(futures):
            if self.cancel_flag.is_set():
                break
                
            success, reason, fp, out_path = future.result()
            if not success:
                self.after(0, self.status_label.configure, {"text": f"Error: {reason}", "text_color": self.c_danger})
                # We won't break on a single error, let others finish
            else:
                self.upload_to_webhook_if_enabled(out_path)
                
            completed += 1
            self.after(0, self.progress_bar.set, completed / total)
            
        self.thread_pool.shutdown(wait=False)
        
        if self.cancel_flag.is_set():
            self.after(0, self.status_label.configure, {"text": "Operation Cancelled", "text_color": self.c_danger})
        else:
            self.after(0, self.conversion_done)
            
        self.after(0, self.reset_ui_buttons)

    def reset_ui_buttons(self):
        self.convert_btn.configure(state="normal")
        self.extract_btn.configure(state="normal")
        self.thumb_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled", fg_color="#333")
        
    def upload_to_webhook_if_enabled(self, out_path):
        if not self.webhook_var.get():
            return
            
        url = self.webhook_url.get().strip()
        if not url:
            return
            
        try:
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            if size_mb > 25:
                print(f"File {out_path} is too large for Discord webhook (>25MB).")
                return
                
            with open(out_path, 'rb') as f:
                requests.post(url, files={"file": f}, timeout=30)
        except Exception as e:
            print(f"Webhook upload failed: {e}")
        
    def process_single(self, file_path, audio_only, thumbnail_only):
        if thumbnail_only:
            out_ext = "jpg"
        else:
            out_ext = "mp3" if audio_only else self.format_var.get()
        
        base, _ = os.path.splitext(file_path)
        
        if self.output_dir:
            file_name = os.path.basename(base)
            out_path = os.path.join(self.output_dir, f"{file_name}_devrule.{out_ext}")
        else:
            out_path = f"{base}_devrule.{out_ext}"
            
        cmd = [self.ffmpeg_path, "-y"]
        
        t_start = self.trim_start.get().strip()
        t_end = self.trim_end.get().strip()
        
        if t_start:
            cmd.extend(["-ss", t_start])
        if t_end:
            cmd.extend(["-to", t_end])
            
        if thumbnail_only and not t_start:
            cmd.extend(["-ss", "00:00:01"])
            
        cmd.extend(["-i", file_path])
        
        if thumbnail_only:
            cmd.extend(["-vframes", "1"])
        elif audio_only:
            cmd.extend(["-vn", "-c:a", "libmp3lame", "-q:a", "2"])
        else:
            is_audio = out_ext in ["mp3", "wav", "flac"]
            if not is_audio:
                if out_ext == "gif":
                    cmd.extend(["-filter_complex", "[0:v] split [a][b];[a] palettegen [p];[b][p] paletteuse"])
                else:
                    enc = self.encoder_var.get()
                    if enc == "NVIDIA (NVENC)": cmd.extend(["-c:v", "h264_nvenc"])
                    elif enc == "AMD (AMF)": cmd.extend(["-c:v", "h264_amf"])
                    elif enc == "Intel (QSV)": cmd.extend(["-c:v", "h264_qsv"])
                    else: cmd.extend(["-c:v", "libx264"])
                        
                    res = self.res_var.get()
                    if res != "Original": cmd.extend(["-vf", f"scale={res.replace('x', ':')}"])
                        
                    if self.discord_fit_var.get():
                        dur_str = "0"
                        try:
                            creationflags = 0x08000000 if sys.platform == "win32" else 0
                            d_res = subprocess.run([self.ffmpeg_path, "-i", file_path], stderr=subprocess.PIPE, text=True, creationflags=creationflags)
                            dm = re.search(r"Duration: (\d{2}:\d{2}:\d{2})", d_res.stderr)
                            if dm: dur_str = dm.group(1)
                        except Exception:
                            pass
                        secs = time_to_seconds(dur_str)
                        if secs > 0:
                            total_kbps = 200704 / secs
                            v_kbps = max(50, int(total_kbps - 128))
                            cmd.extend(["-b:v", f"{v_kbps}k", "-maxrate", f"{v_kbps}k", "-bufsize", f"{v_kbps*2}k"])
                        else:
                            cmd.extend(["-b:v", "1M"])
                    else:
                        qual = self.qual_var.get()
                        crf = "23" 
                        if "High" in qual: crf = "18"
                        elif "Low" in qual: crf = "28"
                        
                        if enc == "CPU (x264)":
                            cmd.extend(["-crf", crf])
                        else:
                            b = "5M" if "High" in qual else "2.5M" if "Medium" in qual else "1M"
                            cmd.extend(["-b:v", b])
                    
            # Audio
            a_codec = getattr(self, 'audio_codec_var', None)
            a_bitrate = getattr(self, 'audio_bitrate_var', None)
            
            if hasattr(self, 'discord_fit_var') and self.discord_fit_var.get() and not is_audio:
                cmd.extend(["-c:a", "aac", "-b:a", "128k"])
            elif a_codec and a_codec.get() == "Copy (No re-encode)":
                cmd.extend(["-c:a", "copy"])
            elif a_codec and a_bitrate:
                if a_codec.get() == "AAC": cmd.extend(["-c:a", "aac"])
                elif a_codec.get() == "MP3": cmd.extend(["-c:a", "libmp3lame"])
                cmd.extend(["-b:a", a_bitrate.get()])
                
        cmd.append(out_path)
        
        try:
            creationflags = 0x08000000 if sys.platform == "win32" else 0
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
            self.active_processes.append(proc)
            
            while proc.poll() is None:
                if self.cancel_flag.is_set():
                    proc.kill()
                    return False, "Cancelled", file_path, out_path
                time.sleep(0.1)
                
            if proc.returncode != 0:
                return False, f"FFMPEG Error code {proc.returncode}", file_path, out_path
                
            return True, "Success", file_path, out_path
        except Exception as e:
            return False, str(e), file_path, out_path
            
    def conversion_done(self):
        self.progress_bar.set(1)
        self.status_label.configure(text="System Optimal - Files Saved", text_color=self.c_cyan)
        self.file_paths.clear()

if __name__ == "__main__":
    app = ConverterApp()
    app.mainloop()
