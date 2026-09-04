import tkinter as tk
from pickle import GLOBAL
from tkinter import messagebox, ttk, filedialog
import os
import sys
import shutil
import threading
import subprocess
import json
import time
import re
from datetime import datetime
import cv2
from PIL import Image, ImageTk
import numpy as np

from config import (
    BUILD_DIR, DEFAULT_DOWNLOAD_PAGE, DEFAULT_JUMP_PAGE,
    dynamic_config, OUTPUT_DIR, DEFAULT_CONFIG_TEMPLATE,
    DEFAULT_SINGLE_VIDEO_URL, DEFAULT_BATCH_VIDEO_URL,
    BATCH_VIDEO_LINKS,BATCH_FAILED_LOG_PATH,LAST_BATCH_URL,
    get_config_file_path, SAFE_MODE
)
from video_downloader import VideoDownloader
from batch_manager import BatchDownloadManager

class VideoDownloaderApp:
    """视频下载器GUI应用类"""

    def __init__(self, root):
        # 主窗口配置
        self.root = root
        self.safe_mode = SAFE_MODE
        self.root.title("视频小助手" if self.safe_mode else "阿P助手")

        self.last_batch_url = LAST_BATCH_URL  # 初始化实例变量

        # 下载核心变量
        self.downloader = None
        self.download_thread = None
        self.stop_download = False
        self.current_url = ""
        self.is_resuming = False
        self.m3u8_url = None
        self.output_name = ""
        self.downloading_name_label = None

        # 配置参数
        self.download_page = dynamic_config["default_download_page"]
        self.jump_page = dynamic_config["default_jump_page"]
        self.start_video_url = ""
        self.reverse_download = tk.BooleanVar(value=False)

        # 下载状态锁
        self.is_single_downloading = False
        self.is_batch_downloading = False

        # 批量管理器实例
        self.batch_manager = BatchDownloadManager(self)

        # 预览播放相关配置
        self.is_preview_playing = False
        self.preview_timer = None
        self.current_video_path = ""
        self.PREVIEW_FRAME_DELAY = 250 #每x毫秒播放帧
        self.PREVIEW_FRAME_COUNT = 40 #总帧数
        self.preview_frame_positions = []
        self.current_preview_index = 0

        # 预览窗口尺寸配置
        self.PREVIEW_WIDTH = 400
        self.PREVIEW_HEIGHT = 300

        # 配置文件相关
        self.config_path = ""
        self.config_data = {}
        self.download_entries = {}
        self.path_entries = {}
        self.urls_entries = {}
        self.batch_link_name = None
        self.batch_link_url = None
        self.batch_links_list = None

        # UI控件声明
        self.notebook = None
        self.download_frame = None
        self.file_manager_frame = None
        self.config_frame = None
        self.url_entry = None
        self.download_btn = None
        self.page_url_entry = None
        self.start_url_entry = None
        self.download_page_entry = None
        self.jump_page_entry = None
        self.reverse_check = None
        self.batch_download_btn = None
        self.open_failed_log_btn = None
        self.batch_info_label = None
        self.refresh_btn = None
        self.open_dir_btn = None
        self.inner_frame = None
        self.play_video_btn = None
        self.file_list_scroll = None
        self.file_tree = None
        self.preview_play_btn = None
        self.file_name_label = None
        self.cover_canvas = None
        self.batch_status_label = None
        self.status_label = None
        self.progress_bar = None
        self.current_status_text = "准备就绪"
        self.current_status_color = self.colors["text_muted"] if hasattr(self, "colors") else "#71717a"

        # 隐藏界面模式入口需要快速连续点击5次
        self.hidden_mode_click_count = 0
        self.hidden_mode_click_target = None
        self.hidden_mode_last_click = 0.0

        # 初始化操作
        self.hide_console()
        self.setup_styles()
        self.setup_ui()


    def hide_console(self):
        """隐藏打包后的控制台窗口"""
        try:
            if hasattr(sys, '_MEIPASS'):
                import ctypes
                whnd = ctypes.windll.kernel32.GetConsoleWindow()
                if whnd != 0:
                    ctypes.windll.user32.ShowWindow(whnd, 0)
        except:
            pass

    def setup_styles(self):
        """配置统一的现代桌面界面样式。"""
        self.colors = {
            "background": "#f7f7f8",
            "surface": "#ffffff",
            "surface_alt": "#f1f1f3",
            "border": "#e4e4e7",
            "text": "#18181b",
            "muted": "#71717a",
            "accent": "#2563eb",
            "accent_hover": "#1d4ed8",
            "danger": "#b42318",
        }

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        def remove_focus_elements(layout):
            cleaned_layout = []
            for element_name, options in layout:
                element_options = dict(options)
                children = remove_focus_elements(element_options.get("children", []))
                if "children" in element_options:
                    element_options["children"] = children
                if "focus" in element_name.lower():
                    cleaned_layout.extend(children)
                else:
                    cleaned_layout.append((element_name, element_options))
            return cleaned_layout

        for style_name in ("TButton", "TCheckbutton", "TRadiobutton", "TNotebook.Tab"):
            try:
                style.layout(style_name, remove_focus_elements(style.layout(style_name)))
            except tk.TclError:
                pass

        default_font = ("Microsoft YaHei UI", 10)
        self.root.configure(background=self.colors["background"])
        self.root.option_add("*Font", default_font)
        self.root.option_add("*TCombobox*Listbox.font", default_font)

        style.configure(".", font=default_font, background=self.colors["background"],
                        foreground=self.colors["text"])
        style.configure("TFrame", background=self.colors["surface"])
        style.configure("App.TFrame", background=self.colors["background"])
        style.configure("Surface.TFrame", background=self.colors["surface"])
        style.configure("TLabel", background=self.colors["surface"], foreground=self.colors["text"])
        style.configure("Muted.TLabel", foreground=self.colors["muted"])
        style.configure("Status.TLabel", background=self.colors["surface"], foreground=self.colors["muted"])

        style.configure("TButton", background=self.colors["surface_alt"], foreground=self.colors["text"],
                        borderwidth=0, relief="flat", padding=(12, 7), focusthickness=0,
                        focuscolor=self.colors["surface_alt"])
        style.map("TButton",
                  background=[("active", "#e9e9ec"), ("pressed", "#dedee2"), ("disabled", "#f4f4f5")],
                  foreground=[("disabled", "#a1a1aa")])
        style.configure("Primary.TButton", background=self.colors["accent"], foreground="#ffffff",
                        padding=(18, 9), font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Primary.TButton",
                  background=[("active", self.colors["accent_hover"]), ("pressed", "#1e40af"),
                              ("disabled", "#9db7ed")],
                  foreground=[("disabled", "#f3f4f6")])
        style.configure("Subtle.TButton", background=self.colors["surface"], foreground=self.colors["muted"],
                        borderwidth=0, relief="flat", padding=(12, 7))
        style.map("Subtle.TButton", background=[("active", self.colors["surface_alt"])],
                  foreground=[("active", self.colors["text"])])
        style.configure("Icon.TButton", background=self.colors["background"], foreground=self.colors["muted"],
                        padding=(7, 5), borderwidth=0, font=("Segoe UI Symbol", 12))
        style.map("Icon.TButton", background=[("active", self.colors["surface_alt"])],
                  foreground=[("active", self.colors["text"])])
        self.corner_button_image = tk.PhotoImage(width=6, height=6)
        self.corner_button_image.put("#d4d4d8", to=(0, 0, 6, 6))
        style.configure("Hidden.TButton", background=self.colors["surface"], padding=(2, 2), borderwidth=0)
        style.map("Hidden.TButton", background=[("active", self.colors["surface_alt"])])

        style.configure("TNotebook", background=self.colors["background"], borderwidth=0,
                        lightcolor=self.colors["background"], darkcolor=self.colors["background"],
                        tabmargins=(0, 0, 0, 10))
        style.configure("TNotebook.Tab", background=self.colors["surface_alt"], foreground=self.colors["muted"],
                        borderwidth=0, relief="flat", padding=(18, 10), font=("Microsoft YaHei UI", 10),
                        bordercolor=self.colors["background"], lightcolor=self.colors["background"],
                        darkcolor=self.colors["background"], focuscolor=self.colors["background"])
        style.map("TNotebook.Tab",
                  background=[("selected", self.colors["surface"]), ("active", "#eeeef0")],
                  foreground=[("selected", self.colors["text"]), ("active", self.colors["text"])],
                  bordercolor=[("selected", self.colors["surface"]), ("active", "#eeeef0")],
                  lightcolor=[("selected", self.colors["surface"]), ("active", "#eeeef0")],
                  darkcolor=[("selected", self.colors["surface"]), ("active", "#eeeef0")])

        style.configure("TLabelframe", background=self.colors["surface"], bordercolor=self.colors["surface"],
                        lightcolor=self.colors["surface"], darkcolor=self.colors["surface"],
                        borderwidth=0, relief="flat")
        style.configure("TLabelframe.Label", background=self.colors["surface"], foreground=self.colors["text"],
                        font=("Microsoft YaHei UI", 10, "bold"), padding=(4, 0))
        style.configure("TEntry", fieldbackground=self.colors["surface"], foreground=self.colors["text"],
                        bordercolor=self.colors["border"], lightcolor=self.colors["border"],
                        darkcolor=self.colors["border"], borderwidth=1, padding=(8, 7))
        style.map("TEntry", bordercolor=[("focus", self.colors["accent"])],
                  lightcolor=[("focus", self.colors["accent"])], darkcolor=[("focus", self.colors["accent"])])
        style.configure("TCheckbutton", background=self.colors["surface"], foreground=self.colors["text"], padding=4)
        style.configure(
            "Minimal.TCheckbutton",
            background=self.colors["surface"],
            foreground=self.colors["text"],
            indicatorbackground=self.colors["surface"],
            indicatorforeground=self.colors["surface"],
            indicatorcolor=self.colors["surface"],
            bordercolor=self.colors["border"],
            lightcolor=self.colors["border"],
            darkcolor=self.colors["border"],
            indicatorrelief="flat",
            indicatordiameter=15,
            indicatormargin=(0, 5, 8, 5),
            borderwidth=0,
            padding=3,
        )
        style.map(
            "Minimal.TCheckbutton",
            indicatorbackground=[("selected", self.colors["accent"]), ("active", "#f4f4f5")],
            indicatorforeground=[("selected", "#ffffff")],
            indicatorcolor=[("selected", self.colors["accent"])],
            bordercolor=[("selected", self.colors["accent"]), ("active", "#a1a1aa")],
        )

        style.configure("Treeview", background=self.colors["surface"], fieldbackground=self.colors["surface"],
                        foreground=self.colors["text"], borderwidth=0, rowheight=32)
        style.map("Treeview", background=[("selected", "#dbe7ff")], foreground=[("selected", self.colors["text"])])
        style.configure("Treeview.Heading", background=self.colors["surface_alt"], foreground=self.colors["muted"],
                        borderwidth=0, relief="flat", padding=(8, 8), font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", "#e9e9ec")])
        style.configure("Horizontal.TProgressbar", background=self.colors["accent"],
                        troughcolor=self.colors["border"], bordercolor=self.colors["surface"],
                        lightcolor=self.colors["accent"], darkcolor=self.colors["accent"],
                        relief="flat", borderwidth=0, thickness=7)

        scrollbar_thumb = "#c7c7cc"
        scrollbar_active = "#a1a1aa"
        for orientation in ("Vertical", "Horizontal"):
            style_name = f"{orientation}.TScrollbar"
            style.configure(style_name, background=scrollbar_thumb, troughcolor=self.colors["surface"],
                            bordercolor=self.colors["surface"], lightcolor=scrollbar_thumb,
                            darkcolor=scrollbar_thumb, arrowcolor=self.colors["surface"],
                            gripcount=0, borderwidth=0, relief="flat", width=9)
            style.map(style_name, background=[("active", scrollbar_active), ("pressed", "#8e8e93")])

        style.configure("Horizontal.TScale", background=self.colors["surface"],
                        troughcolor=self.colors["border"], sliderlength=18, borderwidth=0)
        style.configure("Vertical.TScale", background=self.colors["surface"],
                        troughcolor=self.colors["border"], sliderlength=18, borderwidth=0)

    def handle_hidden_mode_click(self, target_mode):
        """连续快速点击5次后切换界面模式。"""
        now = time.monotonic()
        if (self.hidden_mode_click_target != target_mode or
                now - self.hidden_mode_last_click > 1.0):
            self.hidden_mode_click_count = 0
        self.hidden_mode_click_target = target_mode
        self.hidden_mode_last_click = now
        self.hidden_mode_click_count += 1

        if self.hidden_mode_click_count >= 5:
            self.hidden_mode_click_count = 0
            self.hidden_mode_click_target = None
            self.set_ui_mode(target_mode)

    def _set_status(self, text, color=None, refresh=False):
        """统一保存并更新底部状态，避免界面重建或输入清理覆盖任务状态。"""
        self.current_status_text = str(text)
        if color is not None:
            self.current_status_color = color
        if self.status_label is not None:
            self.status_label.config(text=self.current_status_text, foreground=self.current_status_color)
        if refresh:
            self.root.update_idletasks()

    def _setup_file_manager_mode_switch(self):
        """在两种模式的输出目录页使用完全相同的位置放置切换入口。"""
        mode_footer = ttk.Frame(self.file_manager_frame, height=18)
        mode_footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
        mode_footer.pack_propagate(False)

        target_mode = 1 if self.safe_mode else 0
        self.mode_switch_btn = ttk.Button(
            mode_footer,
            image=self.corner_button_image,
            text="",
            style="Hidden.TButton",
            takefocus=False,
            command=lambda: self.handle_hidden_mode_click(target_mode),
        )
        self.mode_switch_btn.place(relx=1.0, rely=1.0, anchor=tk.SE, x=-2, y=-1)
        if self.safe_mode:
            self.restore_mode_btn = self.mode_switch_btn
        else:
            self.safe_mode_btn = self.mode_switch_btn

    def open_output_dir(self):
        """打开输出目录"""
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            if sys.platform == 'win32':
                os.startfile(OUTPUT_DIR)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', OUTPUT_DIR])
            else:
                subprocess.Popen(['xdg-open', OUTPUT_DIR])
        except Exception as e:
            self.show_error(f"打开输出目录失败：{str(e)}")

    def open_batch_failed_log(self):
        """打开下载失败日志文件（不存在则创建空文件）"""
        log_file_path = BATCH_FAILED_LOG_PATH

        try:
            # 检查并创建空日志文件（如果不存在）
            if not os.path.exists(log_file_path):
                with open(log_file_path, 'w', encoding='utf-8') as f:
                    # 写入日志头部，方便识别
                    f.write("# 下载失败日志\n")
                    f.write("-" * 50 + "\n\n")

            # 调用系统默认程序打开日志文件
            if sys.platform == 'win32':
                os.startfile(log_file_path)  # Windows
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', log_file_path])  # Mac
            else:
                subprocess.Popen(['xdg-open', log_file_path])  # Linux

        except Exception as e:
            self.show_error(f"打开失败日志文件失败：{str(e)}")

    def open_config_file(self):
        """打开配置文件"""
        try:
            config_path = get_config_file_path()
            if sys.platform == 'win32':
                subprocess.Popen(['notepad.exe', config_path], shell=True)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', config_path])
            else:
                subprocess.Popen(['xdg-open', config_path])
        except FileNotFoundError:
            self.show_error("配置文件未找到！")
        except Exception as e:
            self.show_error(f"打开配置文件失败：{str(e)}")

    def _snapshot_ui_state(self):
        """保存重建界面时需要保留的输入。"""
        def entry_value(name, default=""):
            widget = getattr(self, name, None)
            try:
                return widget.get()
            except (AttributeError, tk.TclError):
                return default

        return {
            "single_url": entry_value("url_entry", DEFAULT_SINGLE_VIDEO_URL),
            "batch_url": entry_value("page_url_entry", DEFAULT_BATCH_VIDEO_URL),
            "start_url": entry_value("start_url_entry"),
            "download_page": entry_value("download_page_entry", str(self.download_page)),
            "jump_page": entry_value("jump_page_entry", str(self.jump_page)),
            "reverse": bool(self.reverse_download.get()),
        }

    def _restore_ui_state(self, state):
        """恢复模式切换前的输入。"""
        for widget_name, state_key in (
                ("url_entry", "single_url"),
                ("page_url_entry", "batch_url"),
                ("start_url_entry", "start_url"),
                ("download_page_entry", "download_page"),
                ("jump_page_entry", "jump_page")):
            widget = getattr(self, widget_name, None)
            if widget is None:
                continue
            widget.delete(0, tk.END)
            widget.insert(0, state[state_key])
        self.reverse_download.set(state["reverse"])

    def set_ui_mode(self, mode):
        """保存界面模式并在当前进程中立即重建界面。"""
        if mode not in (0, 1):
            return
        target_safe_mode = mode == 0
        if target_safe_mode == self.safe_mode:
            return
        if self.is_single_downloading or self.batch_manager.batch_downloading:
            self.show_error("下载任务进行中，完成或停止任务后才能切换界面模式。")
            return

        config_path = get_config_file_path()
        try:
            with open(config_path, "r", encoding="utf-8") as config_file:
                config_data = json.load(config_file)
            config_data["_UI_MODE"] = mode
            temp_path = f"{config_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as config_file:
                json.dump(config_data, config_file, ensure_ascii=False, indent=4)
            os.replace(temp_path, config_path)
        except (OSError, json.JSONDecodeError) as error:
            self.show_error(f"切换界面模式失败：{error}")
            return

        state = self._snapshot_ui_state()
        self.stop_preview_play()
        self.safe_mode = target_safe_mode
        self.root.title("视频小助手" if self.safe_mode else "阿P助手")
        self.root.withdraw()
        for child in self.root.winfo_children():
            child.destroy()
        self.setup_ui(recenter=False)
        self._restore_ui_state(state)
        if not self.safe_mode:
            self.notebook.select(self.config_frame)
        self.root.update_idletasks()
        self.root.deiconify()

    def setup_ui(self, recenter=True):
        """构建主UI界面"""
        self.download_entries = {}
        self.path_entries = {}
        self.urls_entries = {}

        main_container = ttk.Frame(self.root, padding=(16, 14, 16, 10), style="App.TFrame")
        main_container.pack(fill=tk.BOTH, expand=True)
        main_container.columnconfigure(0, weight=1)
        main_container.rowconfigure(0, weight=1)
        main_container.rowconfigure(1, weight=0)

        notebook_frame = ttk.Frame(main_container, style="App.TFrame")
        notebook_frame.grid(row=0, column=0, sticky="nsew")

        self.notebook = ttk.Notebook(notebook_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.download_frame = ttk.Frame(self.notebook, padding="14", style="Surface.TFrame")
        self.file_manager_frame = ttk.Frame(self.notebook, padding="14", style="Surface.TFrame")
        self.config_frame = ttk.Frame(self.notebook, padding="14", style="Surface.TFrame")

        self.notebook.add(self.download_frame, text="下载页面")
        self.notebook.add(self.file_manager_frame, text="输出目录")

        self.setup_download_tab()
        self.setup_file_manager_tab()
        if not self.safe_mode:
            self.notebook.add(self.config_frame, text="修改配置")
            self.setup_config_tab()

        bottom_frame = ttk.Frame(main_container, padding=(12, 8), style="Surface.TFrame")
        bottom_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        bottom_frame.columnconfigure(0, weight=1)

        self.batch_status_label = ttk.Label(bottom_frame, text="", foreground=self.colors["accent"],
                                            style="Status.TLabel")
        self.batch_status_label.pack(pady=2, fill=tk.X)
        self.batch_status_label.configure(anchor=tk.CENTER)

        self.downloading_name_label = ttk.Label(bottom_frame, text="当前下载：无",
                                                foreground=self.colors["accent"], style="Status.TLabel")
        self.downloading_name_label.configure(anchor=tk.CENTER)

        self.status_label = ttk.Label(bottom_frame, text=self.current_status_text,
                                      foreground=self.current_status_color, style="Status.TLabel")
        self.status_label.configure(anchor=tk.CENTER)

        if not self.safe_mode:
            self.downloading_name_label.pack(pady=2, fill=tk.X)
        self.status_label.pack(pady=2, fill=tk.X)

        self.progress_bar = ttk.Progressbar(bottom_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=5, padx=20)
        self.progress_bar["value"] = 0

        if recenter:
            self.center_window()
        self.root.bind("<Configure>", self.on_window_resize)

    def on_window_resize(self, event):
        """窗口大小变化时强制刷新布局"""
        self.root.update_idletasks()

    def setup_download_tab(self):
        """下载页面"""
        main_container = ttk.Frame(self.download_frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        main_container.columnconfigure(0, weight=1, minsize=360)
        main_container.columnconfigure(1, weight=1, minsize=360)
        main_container.rowconfigure(0, weight=1)

        # 左侧：单视频下载区域
        single_frame = ttk.LabelFrame(main_container, text="单视频下载", padding="18")
        single_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 7), pady=2)
        single_frame.columnconfigure(0, weight=1)

        url_frame = ttk.Frame(single_frame)
        url_frame.pack(fill=tk.X, pady=5)

        ttk.Label(url_frame, text="视频链接:").pack(side=tk.LEFT, padx=3)
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.insert(0, DEFAULT_SINGLE_VIDEO_URL)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)

        btn_container = ttk.Frame(single_frame)
        btn_container.pack(fill=tk.X, pady=8)
        self.download_btn = ttk.Button(btn_container, text="开始下载", command=self.start_or_resume_download,
                                       width=15, style="Primary.TButton")
        self.download_btn.pack(side=tk.TOP, anchor=tk.CENTER)

        # 右侧：批量下载区域
        batch_frame = ttk.LabelFrame(main_container, text="批量下载", padding="18")
        batch_frame.grid(row=0, column=1, sticky="nsew", padx=(7, 0), pady=2)
        batch_frame.columnconfigure(0, weight=1)

        page_frame = ttk.Frame(batch_frame)
        page_frame.pack(fill=tk.X, pady=3)

        ttk.Label(page_frame, text="批量URL:").pack(side=tk.LEFT, padx=3)
        self.page_url_entry = ttk.Entry(page_frame)
        self.page_url_entry.insert(0, DEFAULT_BATCH_VIDEO_URL)
        self.page_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)

        if not self.safe_mode:
            btn_frame = ttk.Frame(batch_frame)
            btn_frame.pack(fill=tk.X, pady=3)
            ttk.Label(btn_frame, text="推荐链接:").pack(side=tk.LEFT, padx=3)

            btn_wrap_frame = ttk.Frame(btn_frame)
            btn_wrap_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
            last_batch_btn = ttk.Button(
                btn_wrap_frame,
                text="上次下载",
                command=lambda: self.fill_batch_url(self.last_batch_url),  # 点击填充历史值
                width=8
            )

            last_batch_btn.pack(side=tk.LEFT, padx=2, pady=1)
            for btn_name, url in BATCH_VIDEO_LINKS:
                btn = ttk.Button(btn_wrap_frame, text=btn_name, command=lambda u=url: self.fill_batch_url(u), width=8)
                btn.pack(side=tk.LEFT, padx=2, pady=1)

        start_url_frame = ttk.Frame(batch_frame)
        start_url_frame.pack(fill=tk.X, pady=3)
        ttk.Label(start_url_frame, text="起始链接:").pack(side=tk.LEFT, padx=3)
        self.start_url_entry = ttk.Entry(start_url_frame)
        self.start_url_entry.insert(0, "")
        self.start_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)

        param_frame = ttk.Frame(batch_frame)
        param_frame.pack(fill=tk.X, pady=3)

        page_count_frame = ttk.Frame(param_frame)
        page_count_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Label(page_count_frame, text="提取页数:").pack(side=tk.LEFT, padx=2)
        self.download_page_entry = ttk.Entry(page_count_frame, width=8)
        self.download_page_entry.insert(0, self.download_page)
        self.download_page_entry.pack(side=tk.LEFT, padx=2)

        jump_count_frame = ttk.Frame(param_frame)
        jump_count_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Label(jump_count_frame, text="跳过数:").pack(side=tk.LEFT, padx=2)
        self.jump_page_entry = ttk.Entry(jump_count_frame, width=8)
        self.jump_page_entry.insert(0, self.jump_page)
        self.jump_page_entry.pack(side=tk.LEFT, padx=2)

        combo_frame = ttk.Frame(batch_frame)
        combo_frame.pack(fill=tk.X, pady=3)

        self.reverse_check = ttk.Checkbutton(combo_frame, text="倒序下载", variable=self.reverse_download,
                                             style="Minimal.TCheckbutton")
        self.reverse_check.pack(side=tk.LEFT, padx=3)

        if not self.safe_mode:
            self.open_failed_log_btn = ttk.Button(
                combo_frame,
                text="失败日志",
                command=self.open_batch_failed_log,
                width=10
            )
            self.open_failed_log_btn.pack(side=tk.RIGHT, anchor=tk.NE, padx=3)

        batch_btn_container = ttk.Frame(batch_frame)
        batch_btn_container.pack(fill=tk.X, pady=8)
        self.batch_download_btn = ttk.Button(batch_btn_container, text="开始批量下载",
                                             command=self.start_batch_download, width=15,
                                             style="Primary.TButton")
        self.batch_download_btn.pack(side=tk.TOP, anchor=tk.CENTER)


        self.batch_info_label = ttk.Label(batch_frame, text="", style="Muted.TLabel",
                                          font=("Microsoft YaHei UI", 9))
        self.batch_info_label.pack(pady=2)

    def setup_file_manager_tab(self):
        """输出目录管理页"""
        if self.safe_mode:
            btn_frame = ttk.Frame(self.file_manager_frame)
            btn_frame.pack(fill=tk.X, pady=2)

            self.refresh_btn = ttk.Button(btn_frame, text="刷新列表", command=self.refresh_file_list, width=8)
            self.refresh_btn.pack(side=tk.LEFT, padx=2)

            self._setup_file_manager_mode_switch()

            preview_frame = ttk.Frame(self.file_manager_frame)
            preview_frame.pack(fill=tk.BOTH, expand=True, pady=1)
            preview_frame.columnconfigure(0, weight=1)
            preview_frame.columnconfigure(1, weight=0)
            preview_frame.rowconfigure(0, weight=1)

            list_frame = ttk.Frame(preview_frame)
            list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 2))

            self.file_list_scroll = ttk.Scrollbar(list_frame)
            self.file_list_scroll.pack(side=tk.RIGHT, fill=tk.Y)

            self.file_tree = ttk.Treeview(list_frame, yscrollcommand=self.file_list_scroll.set,
                                          columns=("seq", "size"), show="headings")

            self.file_tree.heading("seq", text="序号")
            self.file_tree.heading("size", text="大小")

            self.file_tree.column("seq", width=40, anchor=tk.CENTER)
            self.file_tree.column("size", width=60, anchor=tk.CENTER)

            self.file_tree.pack(fill=tk.BOTH, expand=True)
            self.file_list_scroll.config(command=self.file_tree.yview)
        else:
            btn_frame = ttk.Frame(self.file_manager_frame)
            btn_frame.pack(fill=tk.X, pady=2)

            self.refresh_btn = ttk.Button(btn_frame, text="刷新列表", command=self.refresh_file_list, width=8)
            self.refresh_btn.pack(side=tk.LEFT, padx=2)

            self.open_dir_btn = ttk.Button(btn_frame, text="打开目录", command=self.open_output_dir, width=8)
            self.open_dir_btn.pack(side=tk.LEFT, padx=2)

            self.play_video_btn = ttk.Button(btn_frame, text="播放视频", command=self.play_selected_video, width=8,
                                             state=tk.DISABLED)
            self.play_video_btn.pack(side=tk.LEFT, padx=2)

            self._setup_file_manager_mode_switch()

            preview_frame = ttk.Frame(self.file_manager_frame)
            preview_frame.pack(fill=tk.BOTH, expand=True, pady=1)
            preview_frame.columnconfigure(0, weight=1)
            preview_frame.columnconfigure(1, weight=0)
            preview_frame.rowconfigure(0, weight=1)

            list_frame = ttk.Frame(preview_frame)
            list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 2))

            self.file_list_scroll = ttk.Scrollbar(list_frame)
            self.file_list_scroll.pack(side=tk.RIGHT, fill=tk.Y)

            self.file_tree = ttk.Treeview(list_frame, yscrollcommand=self.file_list_scroll.set,
                                          columns=("seq", "name", "size"), show="headings")

            self.file_tree.heading("seq", text="序号")
            self.file_tree.heading("name", text="文件名")
            self.file_tree.heading("size", text="大小")

            self.file_tree.column("seq", width=40, anchor=tk.CENTER)
            self.file_tree.column("name", width=200)
            self.file_tree.column("size", width=60, anchor=tk.CENTER)

            self.file_tree.pack(fill=tk.BOTH, expand=True)
            self.file_list_scroll.config(command=self.file_tree.yview)

            # 预览区域
            cover_frame = ttk.LabelFrame(preview_frame, text="视频预览", padding="8", width=416, height=340)
            cover_frame.grid(row=0, column=1, sticky="nsew", padx=(2, 0))
            cover_frame.pack_propagate(False)

            cover_inner_frame = ttk.Frame(cover_frame, width=400, height=320)
            cover_inner_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            cover_inner_frame.pack_propagate(False)

            # 控制区域：文件名显示 + 预览按钮
            control_frame = ttk.Frame(cover_inner_frame)
            control_frame.pack(fill=tk.X, pady=(0, 2))

            # 文件名显示标签
            self.preview_play_btn = ttk.Button(control_frame, text="预览播放", command=self.toggle_preview_play,
                                               width=8)
            self.preview_play_btn.pack(side=tk.LEFT)
            self.file_name_label = ttk.Label(control_frame, text="未选择文件", anchor=tk.W)
            self.file_name_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

            # 画布
            self.cover_canvas = tk.Canvas(cover_inner_frame, width=self.PREVIEW_WIDTH, height=self.PREVIEW_HEIGHT,
                                          bg=self.colors["surface_alt"], highlightthickness=0)
            self.cover_canvas.pack(pady=2)

            self.cover_canvas.create_text(self.PREVIEW_WIDTH // 2, self.PREVIEW_HEIGHT // 2,
                                          text="未选择视频文件", fill="#999999", font=("Arial", 12))

            self.file_tree.bind("<<TreeviewSelect>>", self.on_file_select)
            self.file_tree.bind("<Double-1>", self.open_selected_file)

        self.refresh_file_list()
        self.mode_switch_btn.lift()

    def calculate_preview_frames(self, video_path):
        """计算预览帧位置"""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return []

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            video_duration = total_frames / fps if fps > 0 else 0

            if fps <= 0 or total_frames <= 0 or video_duration <= 0:
                cap.release()
                return []

            preview_frame_count = self.PREVIEW_FRAME_COUNT
            preview_frame_count = max(2, min(preview_frame_count, total_frames))

            preview_frames = []
            for i in range(preview_frame_count):
                time_ratio = i / (preview_frame_count - 1) if preview_frame_count > 1 else 0.0
                frame_pos = int(total_frames * time_ratio)
                frame_pos = max(0, min(frame_pos, total_frames - 1))
                preview_frames.append(frame_pos)

            cap.release()
            return preview_frames

        except Exception as e:
            print(f"计算预览帧失败: {e}")
            return []

    def toggle_preview_play(self):
        """切换预览播放状态"""
        if not self.current_video_path:
            self.show_error("请先选择视频文件！")
            return

        if self.is_preview_playing:
            self.stop_preview_play()
            self.preview_play_btn.config(text="预览播放")
        else:
            self.start_preview_play()
            self.preview_play_btn.config(text="停止预览")

    def start_preview_play(self):
        """开始预览播放"""
        self.stop_preview_play()

        self.preview_frame_positions = self.calculate_preview_frames(self.current_video_path)
        if not self.preview_frame_positions:
            self.show_error("无法计算预览帧！")
            self.preview_play_btn.config(text="预览播放")
            return

        self.is_preview_playing = True
        self.current_preview_index = 0
        self.show_preview_frame(self.preview_frame_positions[0])
        self.preview_timer = self.root.after(self.PREVIEW_FRAME_DELAY, self.play_next_preview_frame)

    def play_next_preview_frame(self):
        """播放下一预览帧"""
        if not self.is_preview_playing or not self.preview_frame_positions:
            return

        frame_pos = self.preview_frame_positions[self.current_preview_index]
        self.show_preview_frame(frame_pos)

        self.current_preview_index += 1
        if self.current_preview_index >= len(self.preview_frame_positions):
            self.current_preview_index = 0

        if self.is_preview_playing:
            self.preview_timer = self.root.after(self.PREVIEW_FRAME_DELAY, self.play_next_preview_frame)

    def show_preview_frame(self, frame_pos):
        """显示指定位置的预览帧"""
        try:
            cap = cv2.VideoCapture(self.current_video_path)
            if not cap.isOpened():
                return

            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
            ret, frame = cap.read()
            cap.release()

            if not ret:
                return

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)

            img.thumbnail((self.PREVIEW_WIDTH, self.PREVIEW_HEIGHT), Image.Resampling.LANCZOS)

            self.cover_canvas.delete("all")
            tk_img = ImageTk.PhotoImage(img)
            self.cover_canvas.tk_img = tk_img
            self.cover_canvas.create_image(
                (self.PREVIEW_WIDTH - img.width) // 2,
                (self.PREVIEW_HEIGHT - img.height) // 2,
                anchor=tk.NW,
                image=tk_img
            )

        except Exception as e:
            print(f"显示预览帧失败: {e}")

    def stop_preview_play(self):
        """停止预览播放"""
        self.is_preview_playing = False
        if self.preview_timer:
            self.root.after_cancel(self.preview_timer)
            self.preview_timer = None

    # 在 VideoDownloaderApp 类中新增/修改以下方法

    def select_output_dir(self):
        """选择输出目录"""
        selected_dir = filedialog.askdirectory(title="选择视频输出目录")
        if selected_dir:
            self.path_entries["OUTPUT_DIR_ABSOLUTE"].delete(0, tk.END)
            self.path_entries["OUTPUT_DIR_ABSOLUTE"].insert(0, selected_dir)

    def setup_config_tab(self):
        """配置修改标签页"""
        self.config_path = get_config_file_path()
        self.load_config_data()

        main_container = ttk.Frame(self.config_frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=3)
        main_container.rowconfigure(0, weight=1)
        main_container.rowconfigure(1, weight=0)
        main_container.columnconfigure(0, weight=1)

        scroll_container = ttk.Frame(main_container)
        scroll_container.grid(row=0, column=0, sticky="nsew")

        y_scrollbar = ttk.Scrollbar(scroll_container, orient=tk.VERTICAL)
        y_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        content_canvas = tk.Canvas(scroll_container, yscrollcommand=y_scrollbar.set, highlightthickness=0, bd=0,
                                   background=self.colors["surface"])
        content_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y_scrollbar.config(command=content_canvas.yview)

        self.inner_frame = ttk.Frame(content_canvas)
        canvas_window = content_canvas.create_window((0, 0), window=self.inner_frame, anchor=tk.NW,
                                                     tags=("inner_frame",))

        main_container.bind("<MouseWheel>", lambda e: self.on_wheel_universal(e, content_canvas))
        scroll_container.bind("<MouseWheel>", lambda e: self.on_wheel_universal(e, content_canvas))
        content_canvas.bind("<MouseWheel>", lambda e: self.on_wheel_universal(e, content_canvas))
        self.inner_frame.bind("<MouseWheel>", lambda e: self.on_wheel_universal(e, content_canvas))

        main_container.bind("<Configure>", lambda e: self.update_canvas_layout(e, content_canvas, canvas_window))
        scroll_container.bind("<Configure>", lambda e: self.update_canvas_layout(e, content_canvas, canvas_window))
        self.config_frame.after(100, lambda: self.update_canvas_layout(None, content_canvas, canvas_window))

        config_items_frame = ttk.Frame(self.inner_frame)
        config_items_frame.pack(fill=tk.X, expand=True, padx=30, pady=3)

        download_frame = ttk.LabelFrame(config_items_frame, text="下载核心参数", padding="10")
        download_frame.pack(fill=tk.X, expand=True, pady=3)
        download_frame.columnconfigure(1, weight=1)
        download_frame.columnconfigure(3, weight=1)

        download_configs = [
            ("DEFAULT_MAX_GLOBAL_RETRIES", "失败分片全局重试次数", int),
            ("DEFAULT_MAX_WORKERS", "下载线程数", int),
            ("DEFAULT_BATCH_INTERVAL", "批量下载间隔（秒）", int),
            ("DEFAULT_DOWNLOAD_PAGE", "批量下载默认提取页数", int),
            ("DEFAULT_JUMP_PAGE", "批量下载默认跳过视频数", int),
            ("DEFAULT_MAX_RETRIES", "TS分片单分片最大重试次数", int),
            ("DEFAULT_TS_TIMEOUT_CONNECT", "TS分片连接超时（秒）", int),
            ("DEFAULT_TS_TIMEOUT_READ", "TS分片读取超时（秒）", int),
            ("DEFAULT_CHUNK_SIZE", "TS下载块大小（字节）", int),
            ("DEFAULT_M3U8_MAX_RETRIES", "M3U8解析单链接最大重试次数", int),
            ("DEFAULT_M3U8_TIMEOUT", "M3U8解析超时时间（秒）", int),
            ("DEFAULT_M3U8_RETRY_DELAY", "M3U8解析重试延迟（秒）", int),
            ("DEFAULT_DOWNLOAD_TIMEOUT", "M3U8整体下载超时（秒）", int),
            ("DEFAULT_VIDEO_MAX_RETRIES", "视频解析单链接最大重试次数", int),
            ("DEFAULT_VIDEO_TIMEOUT", "视频解析超时时间（秒）", int),
            ("DEFAULT_VIDEO_RETRY_DELAY", "视频解析重试延迟（秒）", int)
        ]

        self.download_entries = {}
        for idx, (key, label, dtype) in enumerate(download_configs):
            row = idx // 2
            col = idx % 2
            ttk.Label(download_frame, text=label, width=25).grid(row=row, column=col * 2, padx=5, pady=2, sticky=tk.E)
            entry = ttk.Entry(download_frame)
            entry.insert(0, self.config_data['download'].get(key, ""))
            entry.grid(row=row, column=col * 2 + 1, padx=5, pady=2, sticky=tk.W + tk.E)
            self.download_entries[key] = (entry, dtype)

        paths_frame = ttk.LabelFrame(config_items_frame, text="文件存储路径配置", padding="10")
        paths_frame.pack(fill=tk.X, expand=True, pady=3)
        paths_frame.columnconfigure(1, weight=1)
        paths_frame.columnconfigure(2, weight=0)  # 新增列用于选择按钮

        ttk.Label(paths_frame, text="视频输出目录(绝对或相对)", width=25).grid(row=0, column=0, padx=5, pady=2,
                                                                             sticky=tk.E)
        output_entry = ttk.Entry(paths_frame)
        output_entry.insert(0, self.config_data['paths'].get("OUTPUT_DIR_ABSOLUTE", ""))
        output_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W + tk.E)
        self.path_entries["OUTPUT_DIR_ABSOLUTE"] = output_entry

        select_dir_btn = ttk.Button(paths_frame, text="选择路径", command=self.select_output_dir, width=10)
        select_dir_btn.grid(row=0, column=2, padx=5, pady=2, sticky=tk.W)

        urls_frame = ttk.LabelFrame(config_items_frame, text="默认下载链接配置", padding="10")
        urls_frame.pack(fill=tk.X, expand=True, pady=3)
        urls_frame.columnconfigure(1, weight=1)

        ttk.Label(urls_frame, text="单视频默认下载链接", width=20).grid(row=0, column=0, padx=5, pady=2, sticky=tk.E)
        single_url_entry = ttk.Entry(urls_frame)
        single_url_entry.insert(0, self.config_data['urls'].get("DEFAULT_SINGLE_VIDEO_URL", ""))
        single_url_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W + tk.E)
        self.urls_entries = {"DEFAULT_SINGLE_VIDEO_URL": single_url_entry}

        ttk.Label(urls_frame, text="批量默认链接管理", width=20).grid(row=1, column=0, padx=5, pady=5, sticky=tk.E)
        link_input_frame = ttk.Frame(urls_frame)
        link_input_frame.grid(row=2, column=0, columnspan=2, padx=5, pady=3, sticky=tk.W + tk.E)
        link_input_frame.columnconfigure(1, weight=1)
        link_input_frame.columnconfigure(3, weight=3)

        ttk.Label(link_input_frame, text="链接名称:").pack(side=tk.LEFT, padx=2)
        self.batch_link_name = ttk.Entry(link_input_frame)
        self.batch_link_name.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        ttk.Label(link_input_frame, text="链接地址:").pack(side=tk.LEFT, padx=2)
        self.batch_link_url = ttk.Entry(link_input_frame)
        self.batch_link_url.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        btn_frame = ttk.Frame(link_input_frame)
        btn_frame.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="添加", command=self.add_batch_link, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除", command=self.del_batch_link, width=6).pack(side=tk.LEFT, padx=2)

        self.batch_links_list = tk.Listbox(
            urls_frame,
            background=self.colors["surface"],
            foreground=self.colors["text"],
            selectbackground="#dbe7ff",
            selectforeground=self.colors["text"],
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["accent"],
            highlightthickness=1,
            relief="flat",
            borderwidth=0,
            activestyle="none",
        )
        self.batch_links_list.grid(row=3, column=0, columnspan=2, padx=5, pady=3, sticky=tk.W + tk.E)
        self.batch_links_list.config(height=8)
        self.load_batch_links()

        btn_frame = ttk.Frame(main_container)
        btn_frame.grid(row=1, column=0, sticky="ew", pady=5)
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=0)
        btn_frame.columnconfigure(2, weight=1)

        btn_inner_frame = ttk.Frame(btn_frame)
        btn_inner_frame.grid(row=0, column=1)

        self.save_config_btn = ttk.Button(btn_inner_frame, text="保存配置", command=self.save_config, width=12)
        self.save_config_btn.pack(side=tk.LEFT, padx=10)
        self.open_config_btn = ttk.Button(btn_inner_frame, text="打开配置文件", command=self.open_config_file, width=12)
        self.open_config_btn.pack(side=tk.LEFT, padx=10)
        self.restart_btn = ttk.Button(btn_inner_frame, text="重启应用", command=self.restart_app, width=12)
        self.restart_btn.pack(side=tk.LEFT, padx=10)
    def load_config_data(self):
        """加载配置数据"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
            # 确保paths节点存在，防止KeyError
            if 'paths' not in self.config_data:
                self.config_data['paths'] = {}
            # 确保OUTPUT_DIR_ABSOLUTE键存在
            if 'OUTPUT_DIR_ABSOLUTE' not in self.config_data['paths']:
                self.config_data['paths']['OUTPUT_DIR_ABSOLUTE'] = DEFAULT_CONFIG_TEMPLATE['paths'][
                    'OUTPUT_DIR_ABSOLUTE']
        except (FileNotFoundError, json.JSONDecodeError):
            self.config_data = DEFAULT_CONFIG_TEMPLATE.copy()

    def save_config(self):
        """保存配置"""
        try:
            for key, (entry, dtype) in self.download_entries.items():
                value = entry.get().strip()
                if dtype == int:
                    self.config_data['download'][key] = int(value)
                else:
                    self.config_data['download'][key] = value

            self.config_data['paths']['OUTPUT_DIR_ABSOLUTE'] = self.path_entries['OUTPUT_DIR_ABSOLUTE'].get().strip()

            self.config_data['urls']['DEFAULT_SINGLE_VIDEO_URL'] = self.urls_entries[
                'DEFAULT_SINGLE_VIDEO_URL'].get().strip()

            self.config_data['urls']['BATCH_VIDEO_LINKS'] = self.config_data['urls'].get("BATCH_VIDEO_LINKS", [])

            # 保存上次批量下载URL
            if hasattr(self, 'last_batch_url') and self.last_batch_url:
                self.config_data['urls']['LAST_BATCH_URL'] = self.last_batch_url

            # 写入配置文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=4)

            # 更新全局变量
            global dynamic_config, OUTPUT_DIR, BUILD_DIR, DEFAULT_DOWNLOAD_PAGE, DEFAULT_JUMP_PAGE

            dynamic_config["max_retries"] = self.config_data['download']['DEFAULT_MAX_RETRIES']
            dynamic_config["max_global_retries"] = self.config_data['download']['DEFAULT_MAX_GLOBAL_RETRIES']
            dynamic_config["max_workers"] = self.config_data['download']['DEFAULT_MAX_WORKERS']
            dynamic_config["batch_interval"] = self.config_data['download']['DEFAULT_BATCH_INTERVAL']
            dynamic_config["download_timeout"] = self.config_data['download']['DEFAULT_DOWNLOAD_TIMEOUT']
            dynamic_config["ts_timeout_connect"] = self.config_data['download']['DEFAULT_TS_TIMEOUT_CONNECT']
            dynamic_config["ts_timeout_read"] = self.config_data['download']['DEFAULT_TS_TIMEOUT_READ']
            dynamic_config["chunk_size"] = self.config_data['download']['DEFAULT_CHUNK_SIZE']
            dynamic_config["default_download_page"] = self.config_data['download']['DEFAULT_DOWNLOAD_PAGE']
            dynamic_config["default_jump_page"] = self.config_data['download']['DEFAULT_JUMP_PAGE']
            dynamic_config["m3u8_max_retries"] = self.config_data['download']['DEFAULT_M3U8_MAX_RETRIES']
            dynamic_config["m3u8_timeout"] = self.config_data['download']['DEFAULT_M3U8_TIMEOUT']
            dynamic_config["m3u8_retry_delay"] = self.config_data['download']['DEFAULT_M3U8_RETRY_DELAY']
            dynamic_config["video_max_retries"] = self.config_data['download']['DEFAULT_VIDEO_MAX_RETRIES']
            dynamic_config["video_timeout"] = self.config_data['download']['DEFAULT_VIDEO_TIMEOUT']
            dynamic_config["video_retry_delay"] = self.config_data['download']['DEFAULT_VIDEO_RETRY_DELAY']

            DEFAULT_DOWNLOAD_PAGE = self.config_data['download']['DEFAULT_DOWNLOAD_PAGE']
            DEFAULT_JUMP_PAGE = self.config_data['download']['DEFAULT_JUMP_PAGE']
            CONFIG_DIR = os.path.dirname(self.config_path)
            BUILD_DIR = os.path.join(CONFIG_DIR, "build_dir")
            OUTPUT_DIR = self.config_data['paths']['OUTPUT_DIR_ABSOLUTE']

            self.show_info("配置保存成功！部分配置需要重启应用生效")

        except ValueError as e:
            self.show_error(f"请输入有效的数字：{str(e)}")
        except KeyError as e:
            self.show_error(f"配置项缺失：{str(e)}，请检查配置文件结构")
        except Exception as e:
            self.show_error(f"保存配置失败：{str(e)}")

    def bind_all_widgets_wheel(self, widget, canvas):
        """绑定滚轮事件"""
        try:
            widget.bind("<MouseWheel>", lambda e: self.on_wheel_universal(e, canvas))
            for child in widget.winfo_children():
                self.bind_all_widgets_wheel(child, canvas)
        except Exception as e:
            print(f"绑定滚轮事件失败: {e}")

    def on_wheel_universal(self, event, canvas):
        """通用滚轮处理"""
        delta = -int(event.delta / 120)
        canvas.yview_scroll(delta, "units")
        return "break"

    def update_canvas_layout(self, event, canvas, canvas_window):
        """更新画布布局"""
        self.inner_frame.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))
        if canvas.winfo_width() > 0:
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
        canvas.focus_set()
        self.bind_all_widgets_wheel(self.inner_frame, canvas)

    def load_batch_links(self):
        """加载批量链接"""
        self.batch_links_list.delete(0, tk.END)
        batch_links = self.config_data['urls'].get("BATCH_VIDEO_LINKS", [])
        for name, url in batch_links:
            self.batch_links_list.insert(tk.END, f"{name}: {url}")

    def add_batch_link(self):
        """添加批量链接"""
        name = self.batch_link_name.get().strip()
        url = self.batch_link_url.get().strip()
        if not name or not url:
            self.show_error("链接名称和地址不能为空！")
            return

        batch_links = self.config_data['urls'].get("BATCH_VIDEO_LINKS", [])
        batch_links.append([name, url])
        self.config_data['urls']["BATCH_VIDEO_LINKS"] = batch_links

        self.load_batch_links()
        self.batch_link_name.delete(0, tk.END)
        self.batch_link_url.delete(0, tk.END)

    def del_batch_link(self):
        """删除批量链接"""
        try:
            idx = self.batch_links_list.curselection()[0]
            batch_links = self.config_data['urls'].get("BATCH_VIDEO_LINKS", [])
            if 0 <= idx < len(batch_links):
                batch_links.pop(idx)
                self.config_data['urls']["BATCH_VIDEO_LINKS"] = batch_links
                self.load_batch_links()
        except IndexError:
            self.show_error("请先选中要删除的链接！")

    def restart_app(self):
        """重启应用"""
        if messagebox.askyesno("确认", "是否重启应用以应用新配置？"):
            python = sys.executable
            os.execl(python, python, *sys.argv)

    def refresh_file_list(self):
        """刷新文件列表"""
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)

        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)

            files = []
            for file_name in os.listdir(OUTPUT_DIR):
                file_path = os.path.join(OUTPUT_DIR, file_name)
                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    modify_time = os.path.getmtime(file_path)

                    files.append({
                        "path": file_path,
                        "name": file_name,
                        "size": file_size,
                        "modify_time": modify_time
                    })

            files.sort(key=lambda x: x["modify_time"], reverse=True)

            for idx, file_info in enumerate(files, 1):
                size_str = self.format_file_size(file_info["size"])
                if self.safe_mode:
                    values_tmp = (
                        idx,
                        size_str
                    )
                else:
                    values_tmp=(
                        idx,
                        file_info["name"],
                        size_str
                    )

                self.file_tree.insert(
                    "",
                    tk.END,
                    values=values_tmp,
                    tags=(file_info["path"],)
                )

        except Exception as e:
            self.show_error(f"加载文件列表失败：{str(e)}")

    def format_file_size(self, size):
        """格式化文件大小"""
        units = ['B', 'KB', 'MB', 'GB']
        unit_index = 0
        while size >= 1024 and unit_index < 3:
            size /= 1024
            unit_index += 1
        return f"{size:.2f} {units[unit_index]}"

    def on_file_select(self, event):
        """选中文件事件"""
        # 标记当前是否正在预览播放
        was_playing = self.is_preview_playing

        # 停止当前预览
        self.stop_preview_play()
        self.preview_play_btn.config(text="预览播放")

        selected_items = self.file_tree.selection()
        if selected_items:
            self.play_video_btn.config(state=tk.NORMAL)
            selected_item = selected_items[0]
            file_path = self.file_tree.item(selected_item, "tags")[0]
            self.current_video_path = file_path

            file_name = os.path.basename(file_path)
            self.file_name_label.config(text=file_name)

            # 显示新视频的缩略图
            self.display_video_thumbnail(file_path)

            # 如果之前正在播放，自动启动新视频的预览
            if was_playing:
                self.start_preview_play()
                self.preview_play_btn.config(text="停止预览")
        else:
            self.play_video_btn.config(state=tk.DISABLED)
            self.current_video_path = ""
            self.file_name_label.config(text="未选择文件")
            self.cover_canvas.delete("all")
            self.cover_canvas.create_text(
                self.PREVIEW_WIDTH // 2, self.PREVIEW_HEIGHT // 2,
                text="未选择视频文件",
                fill="#999999",
                font=("Arial", 12)
            )

        self.root.update_idletasks()

    def display_video_thumbnail(self, file_path):
        """显示视频缩略图"""
        self.cover_canvas.delete("all")

        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext in ['.mp4', '.avi', '.mkv', '.flv', '.mov']:
            try:
                cap = cv2.VideoCapture(file_path)
                if cap.isOpened():
                    # 获取视频总帧数
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    # 计算中间帧位置（可以调整比例，比如0.1表示10%位置，0.5表示中间）
                    preview_frame_pos = int(total_frames * 0.1)
                    # 确保帧位置有效
                    preview_frame_pos = max(1, min(preview_frame_pos, total_frames - 1))

                    # 设置读取的帧位置
                    cap.set(cv2.CAP_PROP_POS_FRAMES, preview_frame_pos)
                    ret, frame = cap.read()

                    if ret:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        img = Image.fromarray(frame)

                        img.thumbnail((self.PREVIEW_WIDTH, self.PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
                        tk_img = ImageTk.PhotoImage(img)
                        self.cover_canvas.tk_img = tk_img
                        self.cover_canvas.create_image(
                            (self.PREVIEW_WIDTH - img.width) // 2,
                            (self.PREVIEW_HEIGHT - img.height) // 2,
                            anchor=tk.NW,
                            image=tk_img
                        )
                    else:
                        # 如果中间帧读取失败，退回到第一帧
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = cap.read()
                        if ret:
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            img = Image.fromarray(frame)
                            img.thumbnail((self.PREVIEW_WIDTH, self.PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
                            tk_img = ImageTk.PhotoImage(img)
                            self.cover_canvas.tk_img = tk_img
                            self.cover_canvas.create_image(
                                (self.PREVIEW_WIDTH - img.width) // 2,
                                (self.PREVIEW_HEIGHT - img.height) // 2,
                                anchor=tk.NW,
                                image=tk_img
                            )
                    cap.release()
            except Exception as e:
                print(f"读取视频缩略图失败: {e}")
                self.cover_canvas.create_text(
                    self.PREVIEW_WIDTH // 2, self.PREVIEW_HEIGHT // 2,
                    text="无法读取视频预览",
                    fill="#999999",
                    font=("Arial", 12)
                )
        else:
            self.cover_canvas.create_text(
                self.PREVIEW_WIDTH // 2, self.PREVIEW_HEIGHT // 2,
                text="非视频文件\n无封面预览",
                fill="#999999",
                font=("Arial", 10)
            )

    def play_selected_video(self):
        """播放选中视频"""
        self.open_selected_file(None)

    def open_selected_file(self, event):
        """打开选中文件"""
        try:
            selected_items = self.file_tree.selection()
            if not selected_items:
                return
            selected_item = selected_items[0]
            file_path = self.file_tree.item(selected_item, "tags")[0]

            if sys.platform == 'win32':
                os.startfile(file_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', file_path])
            else:
                subprocess.Popen(['xdg-open', file_path])

        except Exception as e:
            self.show_error(f"打开文件失败：{str(e)}")

    def fill_batch_url(self, url):
        """填充批量URL"""
        self.page_url_entry.delete(0, tk.END)
        self.page_url_entry.insert(0, url)
        self.status_label.config(text=f"已选择: {url}", foreground="blue")

    def center_window(self):
        """窗口居中"""
        self.root.update_idletasks()
        width = 1040
        height = 700
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        self.root.minsize(width, height)

    def check_url_change(self, event=None):
        """检查URL变化"""
        new_url = self.url_entry.get().strip()
        if new_url != self.current_url:
            self.current_url = new_url
            self.is_resuming = False
            self.m3u8_url = None
            self.output_name = ""
            self.download_btn.config(text="开始下载")
            self.progress_bar["value"] = 0

    def _clear_safe_mode_urls(self):
        """安全模式开始任务后不在界面保留敏感链接。"""
        if not self.safe_mode:
            return
        for entry in (self.url_entry, self.page_url_entry):
            if entry is not None:
                entry.delete(0, tk.END)

    def clean_build_dir(self):
        """清理构建目录"""
        try:
            shutil.rmtree(BUILD_DIR, ignore_errors=True)
            os.makedirs(BUILD_DIR, exist_ok=True)
        except Exception as e:
            print(f"清理构建目录失败: {e}")

    def start_or_resume_download(self):
        """开始或续传下载"""
        if self.is_batch_downloading or self.batch_manager.batch_downloading:
            self.show_error("当前正在进行批量下载，无法启动单视频下载！")
            return
        if self.is_single_downloading:
            return

        url = self.url_entry.get().strip()
        if not url and self.safe_mode and self.is_resuming:
            url = self.current_url
        if not url:
            self.show_error("请输入视频URL")
            return

        if url != self.current_url or not self.is_resuming:
            self.clean_build_dir()
            self.is_resuming = False
            self.m3u8_url = None
            self.output_name = ""
            self.download_btn.config(text="开始下载")
            self.progress_bar["value"] = 0

        self.current_url = url
        self._clear_safe_mode_urls()
        self.start_download(url)

    def start_download(self, url=None):
        """启动下载"""
        url = (url or self.url_entry.get()).strip()
        if not url:
            self.show_error("请输入视频URL")
            return

        self.is_single_downloading = True
        self.batch_download_btn.config(state=tk.DISABLED)

        self.download_btn.config(state=tk.DISABLED)
        self._set_status("正在初始化...", "blue", refresh=True)
        self.progress_bar.stop()
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(12)

        self.download_thread = threading.Thread(
            target=self.download_video,
            args=(url, None),
            daemon=True
        )
        self.download_thread.start()

    def start_download_single_for_batch(self, url, callback):
        """批量下载单个视频"""
        self.is_batch_downloading = True
        self.download_btn.config(state=tk.DISABLED)

        self.download_btn.config(state=tk.DISABLED)
        self._set_status(f"批量下载第{self.batch_manager.current_index + 1}个视频...", "blue", refresh=True)
        self.progress_bar.stop()
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(12)

        self.download_thread = threading.Thread(
            target=self.download_video,
            args=(url, callback),
            daemon=True
        )
        self.download_thread.start()

    def start_batch_download(self):
        """开始批量下载"""
        if self.is_batch_downloading or self.batch_manager.batch_downloading:
            return
        if self.is_single_downloading:
            self.show_error("当前正在进行单视频下载，无法启动批量下载！")
            return

        self.last_batch_url = self.page_url_entry.get().strip()
        if self.last_batch_url:
            try:
                config_path = get_config_file_path()
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)

                config_data['urls']['LAST_BATCH_URL'] = self.last_batch_url

                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=4)
            except Exception as e:
                self.show_error(f"保存上次下载URL失败：{str(e)}")

        self.update_download_page()
        self.update_jump_page()
        self.update_start_video_url()

        page_url = self.page_url_entry.get().strip()
        if not page_url:
            self.show_error("请输入视频列表页面URL")
            return

        self._clear_safe_mode_urls()
        self._set_status("正在提取批量链接...", "blue")
        self.batch_info_label.config(text="正在提取批量链接...")
        self.progress_bar.stop()
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(12)
        self.is_batch_downloading = True
        self.batch_download_btn.config(state=tk.DISABLED)
        self.download_btn.config(state=tk.DISABLED)
        self.root.update_idletasks()
        self.batch_manager.start_batch_download(
            page_url,
            start_video_url=self.start_video_url,
            reverse_download=self.reverse_download.get()
        )

    def update_download_page(self, event=None):
        """更新下载页数"""
        try:
            self.download_page = int(self.download_page_entry.get().strip())
        except:
            self.download_page = dynamic_config["default_download_page"]
            self.download_page_entry.delete(0, tk.END)
            self.download_page_entry.insert(0, self.download_page)

    def update_jump_page(self, event=None):
        """更新跳过页数"""
        try:
            self.jump_page = int(self.jump_page_entry.get().strip())
        except:
            self.jump_page = dynamic_config["default_jump_page"]
            self.jump_page_entry.delete(0, tk.END)
            self.jump_page_entry.insert(0, self.jump_page)

    def update_start_video_url(self, event=None):
        """更新起始视频链接"""
        self.start_video_url = self.start_url_entry.get().strip()

    def update_batch_prepare_progress(self, current_page, total_pages):
        """显示批量链接提取阶段的实时状态。"""
        if not self.batch_manager.batch_downloading:
            return
        text = f"正在提取批量链接... {current_page}/{total_pages} 页"
        self._set_status(text, "blue")
        self.batch_status_label.config(text=text)
        self.batch_info_label.config(text=text)

    def update_batch_status(self):
        """更新批量下载状态"""
        if self.batch_manager.batch_downloading:
            self.is_batch_downloading = True
            total = self.batch_manager.batch_total
            current = self.batch_manager.current_index
            batch_progress = (current / total) * 100 if total > 0 else 0
            self.progress_bar.stop()
            self.progress_bar.config(mode="determinate")
            self.progress_bar["value"] = batch_progress

            self.batch_status_label.config(
                text=f"批量下载中: {self.batch_manager.current_index}/{self.batch_manager.batch_total} "
                     f"(成功: {self.batch_manager.batch_success}, 失败: {self.batch_manager.batch_failed})"
            )
            self.batch_info_label.config(
                text=f"进度: {self.batch_manager.current_index}/{self.batch_manager.batch_total} "
                     f"成功: {self.batch_manager.batch_success} 失败: {self.batch_manager.batch_failed}"
            )
            self.batch_download_btn.config(state=tk.DISABLED)
            self.download_btn.config(state=tk.DISABLED)
        else:
            self.is_batch_downloading = False
            self.progress_bar.stop()
            self.progress_bar.config(mode="determinate")
            total = self.batch_manager.batch_total
            current = self.batch_manager.current_index
            if total > 0 and current >= total:
                self.progress_bar["value"] = 100
                self.batch_status_label.config(
                    text=f"批量下载完成: 共{total}个，成功{self.batch_manager.batch_success}个，失败{self.batch_manager.batch_failed}个"
                )
                self.batch_info_label.config(
                    text=f"批量下载完成: 共{total}个，成功{self.batch_manager.batch_success}个，失败{self.batch_manager.batch_failed}个"
                )
            else:
                self.progress_bar["value"] = 0
            self.batch_download_btn.config(state=tk.NORMAL)
            self.download_btn.config(state=tk.NORMAL)

    def _update_ui_progress(self, text, progress, status_type="info"):
        """更新UI进度"""
        if self.safe_mode:
            text = re.sub(r"https?://\S+", "链接已隐藏", str(text), flags=re.IGNORECASE)
        color_map = {"error": "red", "success": "green", "warning": "orange", "info": "blue"}
        self._set_status(text, color_map.get(status_type, "blue"))
        progress = max(0, min(100, progress))
        if progress == 0 and status_type == "info":
            self.progress_bar.stop()
            self.progress_bar.config(mode="indeterminate")
            self.progress_bar.start(12)
        else:
            self.progress_bar.stop()
            self.progress_bar.config(mode="determinate")
            self.progress_bar["value"] = progress
        self.root.update_idletasks()

    def _finish_download_worker(self, callback, success, error_msg):
        """在界面线程完成任务收尾，批量任务结束前始终保持按钮锁定。"""
        self.is_single_downloading = False
        try:
            if callback:
                callback(success, error_msg)
        finally:
            batch_active = self.is_batch_downloading or self.batch_manager.batch_downloading
            button_state = tk.DISABLED if batch_active else tk.NORMAL
            self.batch_download_btn.config(state=button_state)
            self.download_btn.config(state=button_state)

    def download_video(self, url, callback=None):
        """下载视频"""
        success = False
        error_msg = ""
        downloader = None

        try:
            def update_progress(text, progress, status_type="info"):
                self.root.after(0, lambda: self._update_ui_progress(text, progress, status_type))

            downloader = VideoDownloader(None, update_progress)
            self.downloader = downloader

            if not self.m3u8_url or not self.is_resuming:
                update_progress("正在提取视频信息...", 0, "info")
                self.m3u8_url, self.output_name = downloader.extract_video_info(url, wait_time=12)
                if not self.m3u8_url or not self.output_name:
                    error_msg = "提取视频信息失败"
                    update_progress(error_msg, 0, "error")
                    return

            self.root.after(0, lambda: self.downloading_name_label.config(
                text=f"当前下载：{self.output_name}",
                foreground="blue"
            ))

            update_progress("解析m3u8分片...", 0, "info")
            ts_urls, parse_msg = downloader.parse_m3u8(self.m3u8_url)
            if not ts_urls:
                error_msg = parse_msg
                update_progress(error_msg, 0, "error")
                return

            update_progress(parse_msg, 0, "info")

            update_progress("开始下载分片...", 0, "info")
            download_success, download_msg = downloader.download_all_ts_segments(ts_urls, BUILD_DIR)
            if not download_success:
                error_msg = download_msg
                update_progress(error_msg, 0, "error")
                if not callback:
                    self.is_resuming = True
                    self.download_btn.config(text="继续下载")
                return

            update_progress("正在合并视频...", 100, "info")

            os.makedirs(OUTPUT_DIR, exist_ok=True)
            merge_success, merge_msg, final_file = downloader.merge_video_segments(BUILD_DIR, OUTPUT_DIR,
                                                                                    self.output_name)

            if merge_success:
                success_msg = f"下载完成: {final_file}"
                update_progress(success_msg, 100, "success")
                success = True
                self.is_resuming = False
                self.download_btn.config(text="开始下载")
                self.clean_build_dir()
            else:
                error_msg = merge_msg
                update_progress(error_msg, 0, "error")
                self.is_resuming = True
                self.download_btn.config(text="继续下载")

        except Exception as e:
            error_msg = f"下载异常: {str(e)}"
            print(error_msg)
            update_progress(error_msg, 0, "error")
            if not callback:
                self.status_label.config(text=f"错误: {str(e)},点击继续下载", foreground="red")
                self.is_resuming = True
                self.download_btn.config(text="继续下载")

        finally:
            try:
                if downloader:
                    downloader.close()
            finally:
                if self.downloader is downloader:
                    self.downloader = None
                self.root.after(
                    0,
                    lambda: self._finish_download_worker(callback, success, error_msg),
                )

    def show_error(self, msg):
        """显示错误信息"""
        messagebox.showerror("错误", msg)

    def show_info(self, msg):
        """显示提示信息"""
        messagebox.showinfo("提示", msg)

