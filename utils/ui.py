"""
UI Module for Roblox Account Manager
Contains the main AccountManagerUI class
"""

import os
import json
import sys
import asyncio
import queue
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, simpledialog
import requests
import threading
import msvcrt
import ctypes
from ctypes import wintypes
import webbrowser
import time
import re
import shlex
import secrets
import win32event
import win32api
import win32gui
from datetime import datetime, timedelta, timezone
import zipfile
import tempfile
import shutil
import platform
import traceback
import psutil
import random
import stat
import math
import win32process
import tkinter.font as tkfont
import xml.etree.ElementTree as ET
import win32clipboard
from PIL import Image, ImageTk
from io import BytesIO
from tkinter import filedialog
from urllib.request import urlretrieve
import autoit
from classes.roblox_api import RobloxAPI
from classes.account_manager import RobloxAccountManager
from bot.client import DiscordBot
from classes.summary_service import AccountSummaryService
from utils.encryption_setup import EncryptionSetupUI
from utils.theme_manager import ThemeManager
import websockets

class AccountManagerUI:
    def __init__(self, root, manager, icon_path=None, discord_logo_path=None):
        self.root = root
        self.manager = manager
        self.icon_path = icon_path
        self.APP_VERSION = "2.4.8"
        self._game_name_after_id = None
        self._save_settings_timer = None
        
        self.console_output = []
        self.console_window = None
        self.console_text_widget = None
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
        self.tooltip = None
        self.tooltip_timer = None
        
        sys.stdout = self
        sys.stderr = self

        self._ui_task_queue = queue.Queue()
        
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except:
                pass
        
        self.data_folder = "AccountManagerData"
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)
        
        self.settings_file = os.path.join(self.data_folder, "ui_settings.json")
        self.load_settings()
        
        self.root.title("Account Manager by Nerd")
        
        saved_pos = self.settings.get('main_window_position')
        if saved_pos:
            self.root.geometry(f"450x520+{saved_pos['x']}+{saved_pos['y']}")
        else:
            self.root.geometry("450x520")
        self.root.configure(bg="#2b2b2b")
        self.root.resizable(True, True)
        self.root.minsize(450, 520)
        
        self.multi_roblox_handle = None
        self.handle64_monitoring = False
        self.handle64_monitor_thread = None
        self.handle64_path = None
        
        self.anti_afk_thread = None
        self.anti_afk_stop_event = threading.Event()
        self.anti_afk_window = None
        self.anti_afk_tooltip = None
        self.anti_afk_tooltip_label = None
        self.anti_afk_tooltip_timer = None
        self.optimize_ram_thread = None
        self.optimize_ram_stop_event = threading.Event()
        self.optimize_ram_seen_pids = set()
        
        self.rename_thread = None
        self.rename_stop_event = threading.Event()
        self.renamed_pids = set()
        
        self.instances_monitor_thread = None
        self.instances_monitor_stop = threading.Event()
        self.instances_data = []
        self.instances_pids = set()
        self.instances_failed_pids = {} 
        self.instances_data_updated = False
        self.instances_cache = {
            "user_id_to_username": {},
            "user_id_to_avatar": {},
            "user_id_to_photo": {}
        }
        
        self.auto_rejoin_threads = {}
        self.auto_rejoin_stop_events = {}
        self.auto_rejoin_configs = self.settings.get("auto_rejoin_configs", {})
        self.auto_rejoin_pids = {}
        self.auto_rejoin_launch_lock = threading.Lock()
        self.auto_rejoin_presence_lock = threading.Lock()
        self.auto_rejoin_next_presence_time = 0.0
        self._webhook_screenshot_thread = None

        self.websocket_thread = None
        self.websocket_stop_event = threading.Event()
        self.websocket_loop = None
        self.websocket_running = False
        self.discord_bot = DiscordBot(self)
        self.summary_service = AccountSummaryService(self)
        
        self.cookie_status = {}
        for _u, _d in list(self.manager.accounts.items()):
            if isinstance(_d, dict):
                self.cookie_status[_u] = _d.get('cookie_valid', None)
        self.account_tooltip = None
        self.account_tooltip_timer = None
        self.account_tooltip_last_index = None
        self._active_instance_indicators = {}
        self._active_instance_usernames = set()
        self._active_instance_indicator_sync_after = None

        self._list_row_map = []
        self._collapsed_groups = set(self.settings.get("group_collapsed", []))

        try:
            webhook_cfg = self.settings.get("discord_webhook", {})
            webhook_url = str(webhook_cfg.get("url", "") or "").strip()
            if webhook_url and webhook_cfg.get("enabled"):
                try:
                    self._send_webhook_embed(webhook_url, "Connected to Discord!", "Roblox Account Manager started and is now connected.", 0x2ECC71)
                except Exception:
                    pass
            if webhook_url and webhook_cfg.get("screenshot_enabled") and webhook_cfg.get("enabled"):
                threading.Thread(target=self._global_screenshot_worker, daemon=True, name="WebhookScreenshot").start()
        except Exception:
            pass

        self.theme_manager = ThemeManager(os.path.join(self.data_folder, "themes"))
        selected_theme = self.settings.get("selected_theme", "Dark")
        current_theme_config = self._load_current_theme_config()
        if current_theme_config:
            source_theme = str(current_theme_config.get("source_theme", selected_theme) or selected_theme)
            base_data = self.theme_manager.load_theme(source_theme)
            merged_data = self.theme_manager._merge_with_defaults(base_data)
            merged_data = self.theme_manager._merge_with_defaults(current_theme_config)
            self.current_theme_data = merged_data
        else:
            self.current_theme_data = self.theme_manager.load_theme(selected_theme)
        
        self.BG_DARK = self.current_theme_data["colors"].get("bg_dark", "#2b2b2b")
        self.BG_MID = self.current_theme_data["colors"].get("bg_mid", "#3a3a3a")
        self.BG_LIGHT = self.current_theme_data["colors"].get("bg_light", "#4b4b4b")
        self.FG_TEXT = self.current_theme_data["colors"].get("fg_text", "white")
        self.FG_ACCENT = self.current_theme_data["colors"].get("fg_accent", "#0078D7")
        self.FONT_FAMILY = self.current_theme_data["fonts"].get("family", "Segoe UI")
        self.FONT_SIZE = self.current_theme_data["fonts"].get("size_base", 10)
        self.root.configure(bg=self.BG_DARK)

        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Dark.TFrame", background=self.BG_DARK)
        style.configure("Dark.TLabel", background=self.BG_DARK, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE))
        style.configure("Dark.TButton", background=self.BG_MID, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE - 1))
        style.map("Dark.TButton", background=[("active", self.BG_LIGHT)])
        style.configure("Dark.TEntry", fieldbackground=self.BG_MID, background=self.BG_MID, foreground=self.FG_TEXT)
        style.configure("Dark.TCheckbutton", background=self.BG_DARK, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE))
        style.map("Dark.TCheckbutton", background=[("active", self.BG_DARK)], foreground=[("active", self.FG_TEXT)])

        self.notebook = ttk.Notebook(self.root, style="TNotebook")
        self.notebook.pack(fill="both", expand=True)

        self.manager_tab = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(self.manager_tab, text="Manager")

        self.dashboard_tab = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(self.dashboard_tab, text="Dashboard")

        self.watchlist_tab = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(self.watchlist_tab, text="Watchlist")

        bottom_frame = ttk.Frame(self.manager_tab, style="Dark.TFrame")
        bottom_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self.add_account_split_btn = ttk.Button(
            bottom_frame,
            text="Add Account  ▼",
            style="Dark.TButton",
        )
        self.add_account_split_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.add_account_split_btn.bind("<Button-1>", self.on_add_account_split_click)
        
        self.add_account_dropdown = None
        self.add_account_dropdown_visible = False
        
        self.join_place_dropdown = None
        self.join_place_dropdown_visible = False
        
        ttk.Button(bottom_frame, text="Remove", style="Dark.TButton", command=self.remove_account).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(bottom_frame, text="Launch Roblox Home", style="Dark.TButton", command=self.launch_home).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(bottom_frame, text="Settings", style="Dark.TButton", command=self.open_settings).pack(side="left", fill="x", expand=True, padx=(2, 0))

        main_frame = ttk.Frame(self.manager_tab, style="Dark.TFrame")
        main_frame.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 0))

        left_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        header_frame = ttk.Frame(left_frame, style="Dark.TFrame")
        header_frame.pack(fill="x", anchor="w")
        
        ttk.Label(header_frame, text="Account List", style="Dark.TLabel").pack(side="left")
        
        encryption_status = ""
        encryption_color = self.FG_TEXT
        if self.manager.encryption_config.is_encryption_enabled():
            method = self.manager.encryption_config.get_encryption_method()
            if method == 'hardware':
                encryption_status = "[HARDWARE ENCRYPTED]"
                encryption_color = "#90EE90"
            elif method == 'password':
                encryption_status = "[PASSWORD ENCRYPTED]"
                encryption_color = "#87CEEB"
        else:
            encryption_status = "[NOT ENCRYPTED]"
            encryption_color = "#FFB6C1"
            
        self.encryption_label = tk.Label(
            header_frame,
            text=encryption_status,
            bg=self.BG_DARK,
            fg=encryption_color,
            font=("Segoe UI", 8, "bold")
        )
        self.encryption_label.pack(side="right", padx=(5, 0))

        list_frame = ttk.Frame(left_frame, style="Dark.TFrame")
        list_frame.pack(fill="both", expand=True)

        selectmode = tk.EXTENDED if self.settings.get("enable_multi_select", False) else tk.SINGLE
        
        self.account_list = tk.Listbox(
            list_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            highlightthickness=0,
            border=0,
            font=("Segoe UI", 10),
            width=20,
            selectmode=selectmode,
            activestyle="none",
        )
        self.account_list.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, command=self.account_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.account_list_scrollbar = scrollbar
        self.account_list.config(yscrollcommand=self._on_account_list_scroll)
        
        self.drag_data = {
            "item": None, 
            "index": None, 
            "start_x": 0, 
            "start_y": 0,
            "dragging": False,
            "hold_timer": None
        }
        self.drag_indicator = None
        
        self.account_list.bind("<Button-1>", self.on_drag_start)
        self.account_list.bind("<B1-Motion>", self.on_drag_motion)
        self.account_list.bind("<ButtonRelease-1>", self.on_drag_release)
        self.account_list.bind("<Button-3>", self.show_account_context_menu)
        self.account_list.bind("<Motion>", self.on_account_list_hover)
        self.account_list.bind("<Leave>", self.on_account_list_leave)
        self.account_list.bind("<<ListboxSelect>>", lambda _event: self._schedule_active_instance_indicator_sync())

        right_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        right_frame.pack(side="right", fill="y")
        
        self.game_name_label = ttk.Label(right_frame, text="", style="Dark.TLabel", font=("Segoe UI", 9))
        self.game_name_label.pack(anchor="w", pady=(0, 5))
        
        ttk.Label(right_frame, text="Place ID", style="Dark.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.place_entry = ttk.Entry(right_frame, style="Dark.TEntry")
        self.place_entry.pack(fill="x", pady=(0, 5))
        self.place_entry.insert(0, self.settings.get("last_place_id", ""))
        self.place_entry.bind("<KeyRelease>", self.on_place_id_change)

        ttk.Label(right_frame, text="Private Server ID (Optional)", style="Dark.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.private_server_entry = ttk.Entry(right_frame, style="Dark.TEntry")
        self.private_server_entry.pack(fill="x", pady=(0, 5))
        self.private_server_entry.insert(0, self.settings.get("last_private_server", ""))
        self.private_server_entry.bind("<KeyRelease>", self.on_private_server_change)

        self.join_place_split_btn = ttk.Button(
            right_frame,
            text="Join Place ID",
            style="Dark.TButton"
        )
        self.join_place_split_btn.pack(fill="x", pady=(0, 10))
        self.join_place_split_btn.bind("<Button-1>", self.on_join_place_split_click)
        self.join_place_split_btn.bind("<Button-3>", self.on_join_place_right_click)
        self.join_place_split_btn.bind("<Enter>", self.on_join_place_hover)
        self.join_place_split_btn.bind("<Leave>", self.on_join_place_leave)
        
        recent_games_header = ttk.Frame(right_frame, style="Dark.TFrame")
        recent_games_header.pack(fill="x", anchor="w", pady=(10, 2))
        
        ttk.Label(recent_games_header, text="Recent games", style="Dark.TLabel", font=("Segoe UI", 9, "bold")).pack(side="left")
        
        self.star_btn = tk.Button(
            recent_games_header,
            text="⭐",
            bg=self.BG_DARK,
            fg="#FFD700",
            font=("Segoe UI", 10),
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.open_favorites_window
        )
        self.star_btn.pack(side="left", padx=(5, 0))
        
        self.auto_rejoin_btn = tk.Button(
            recent_games_header,
            text="🔁",
            bg=self.BG_DARK,
            fg="#00BFFF",
            font=("Segoe UI", 10),
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.open_auto_rejoin
        )
        self.auto_rejoin_btn.pack(side="left", padx=(5, 0))
        
        game_list_frame = ttk.Frame(right_frame, style="Dark.TFrame")
        game_list_frame.pack(fill="both", expand=True)
        
        self.game_list = tk.Listbox(
            game_list_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            highlightthickness=0,
            border=0,
            font=("Segoe UI", 9),
            height=5,
        )
        self.game_list.pack(side="left", fill="both", expand=True)
        self.game_list.bind("<<ListboxSelect>>", self.on_game_select)
        
        game_scrollbar = ttk.Scrollbar(game_list_frame, command=self.game_list.yview)
        game_scrollbar.pack(side="right", fill="y")
        self.game_list.config(yscrollcommand=game_scrollbar.set)
        
        ttk.Button(right_frame, text="Delete Selected", style="Dark.TButton", command=self.delete_game_from_list).pack(fill="x", pady=(5, 0))

        quick_actions_row = ttk.Frame(right_frame, style="Dark.TFrame")
        quick_actions_row.pack(fill="x", pady=(10, 5))
        ttk.Label(quick_actions_row, text="Quick Actions", style="Dark.TLabel").pack(side="left")
        self.quick_actions_row = quick_actions_row
        self.discord_btn = None

        action_frame = ttk.Frame(right_frame, style="Dark.TFrame")
        action_frame.pack(fill="x")

        ttk.Button(action_frame, text="Donate", style="Dark.TButton", command=lambda: webbrowser.open("https://www.roblox.com/games/718090786/donation#!/store")).pack(fill="x", pady=2)
        ttk.Button(action_frame, text="Edit Note", style="Dark.TButton", command=self.edit_account_note).pack(fill="x", pady=2)
        ttk.Button(action_frame, text="Refresh List", style="Dark.TButton", command=self.refresh_accounts).pack(fill="x", pady=2)


        
        self.root.bind("<Button-1>", self.hide_dropdown_on_click_outside)
        self.root.bind("<Configure>", self.on_root_configure)
        self.root.bind("<Delete>", lambda e: self.remove_account())

        self.refresh_accounts()
        self.refresh_game_list()
        self.update_game_name_on_startup()
        
        try:
            from utils.system_tray import WindowsSystemTray
            self.system_tray = WindowsSystemTray(
                root=self.root,
                on_open=self.restore_from_tray,
                on_exit=self.exit_completely,
                icon_path=self.icon_path
            )
            self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        except Exception as e:
            print(f"[Tray Error] Failed to initialize system tray: {e}")
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        def on_minimize(event=None):
            if event and event.widget == self.root and self.root.state() == "iconic":
                self.minimize_to_tray()
        self.root.bind("<Unmap>", on_minimize)

        try:
            import win32api, win32process
            curr_proc = win32api.GetCurrentProcess()
            win32process.SetPriorityClass(curr_proc, 0x00008000)
            print("[Priority] Process priority successfully set to ABOVE_NORMAL_PRIORITY_CLASS.")
        except Exception as e:
            print(f"[Priority Error] Failed to set process priority: {e}")

        self.root.after(50, self._process_ui_task_queue)
        
        threading.Thread(target=self.check_for_updates, daemon=True).start()
        threading.Thread(target=self._silent_check_cookies_worker, daemon=True).start()
        self.root.after(10000, self.auto_cookie_refresh_heartbeat)
        
        if self.settings.get("lock_roblox_settings", False):
            self.root.after(1000, self.apply_and_lock_roblox_settings)

        if self.settings.get("developer_mode", False) and self.settings.get("websocket_enabled", False):
            self.root.after(1200, self.start_websocket_server)

        if self.settings.get("discord_bot_enabled", False):
            self.root.after(1500, self.start_discord_bot)

        self.presence_statuses = {}
        self.presence_alerted_accounts = set()
        self.setup_dashboard_tab()
        self.start_presence_tracker()
        self.update_dashboard()
        self.pulse_telemetry_indicators()
        
        self.watchlist_alerted_states = {}
        self.watchlist_statuses = {}
        self.setup_watchlist_tab()
        self.start_watchlist_tracker()
        self.start_instances_monitoring()
        self.start_dashboard_report_automation()
        
        try:
            from classes.roblox_api import RobloxAPI
            RobloxAPI.apply_graphics_optimization(self.settings.get("graphics_optimizer_enabled", False))
            
            try:
                if not os.path.exists("icon.png") and os.path.exists("icon.ico"):
                    from PIL import Image
                    img = Image.open("icon.ico")
                    img.save("icon.png", format="PNG")
                    print("[Icon Converter] icon.ico successfully converted to icon.png!")
            except Exception as e:
                print(f"[Icon Converter Error] {e}")

            if self.settings.get("discord_rpc_enabled", True):
                from utils.discord_rpc import DiscordRPC
                rpc_id = self.settings.get("discord_rpc_client_id", "1240954157790367804")
                self.discord_rpc = DiscordRPC(client_id=rpc_id)
                
                def rpc_worker():
                    import psutil
                    time.sleep(5)
                    while True:
                        try:
                            if not self.settings.get("discord_rpc_enabled", True):
                                break
                                
                            active_users = []
                            if hasattr(self, '_active_instance_usernames'):
                                active_users = list(self._active_instance_usernames)
                            
                            cpu_val = psutil.cpu_percent()
                            mem_val = psutil.virtual_memory().percent
                            
                            if active_users:
                                raw_user = active_users[0]
                                display_user = raw_user
                                for key in list(self.manager.accounts.keys()):
                                    if key.lower() == raw_user.lower():
                                        display_user = key
                                        break
                                        
                                self.discord_rpc.set_activity(
                                    details=f"🎮 Running: {len(active_users)} client(s)",
                                    state=f"💻 CPU: {cpu_val:.0f}% | RAM: {mem_val:.0f}%",
                                    large_image="https://raw.githubusercontent.com/ic3w0lf22/Roblox-Account-Manager/master/RBX%20Alt%20Manager/Resources/Roblox%20Account%20Manager.png",
                                    large_text="Account Manager by Nerd",
                                    small_image="https://images.rbxcdn.com/97800c6d7bb00b55502c34db97837012.png",
                                    small_text="Roblox active"
                                )
                            else:
                                total_accts = len(self.manager.accounts)
                                self.discord_rpc.set_activity(
                                    details=f"📁 Idle | Managing {total_accts} account(s)",
                                    state=f"💻 CPU: {cpu_val:.0f}% | RAM: {mem_val:.0f}%",
                                    large_image="https://raw.githubusercontent.com/ic3w0lf22/Roblox-Account-Manager/master/RBX%20Alt%20Manager/Resources/Roblox%20Account%20Manager.png",
                                    large_text="Account Manager by Nerd"
                                )
                        except Exception as e:
                            print(f"[Discord RPC Worker Error] {e}")
                        time.sleep(10)
                        
                threading.Thread(target=rpc_worker, daemon=True).start()
                print("[Discord RPC] Dedicated presence background worker successfully started.")
        except Exception as e:
            print(f"[Discord RPC Setup Error] {e}")
    def minimize_to_tray(self):
        self.root.withdraw()

    def restore_from_tray(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def exit_completely(self):
        if hasattr(self, 'system_tray') and self.system_tray:
            try:
                self.system_tray.destroy()
            except:
                pass
        self.on_closing()

    def on_closing(self):
        """Handle application closing - restore installers and exit"""
        
        self.settings['main_window_position'] = {
            'x': self.root.winfo_x(),
            'y': self.root.winfo_y()
        }
        self.save_settings(force_immediate=True)
        
        if hasattr(self, 'anti_afk_stop_event'):
            self.stop_anti_afk()

        if hasattr(self, 'optimize_ram_stop_event'):
            self.stop_optimize_roblox_ram()
        
        if hasattr(self, 'rename_stop_event'):
            self.stop_rename_monitoring()
        
        if hasattr(self, 'auto_rejoin_threads'):
            self.stop_all_auto_rejoin()

        if hasattr(self, 'websocket_stop_event'):
            self.stop_websocket_server()

        if hasattr(self, 'discord_bot'):
            self.stop_discord_bot()

        if hasattr(self, 'presence_tracker_thread'):
            self.stop_presence_tracker()
            
        if hasattr(self, 'watchlist_tracker_thread'):
            self.stop_watchlist_tracker()

        if hasattr(self, 'db_auto_thread'):
            self.stop_dashboard_report_automation()

        RobloxAPI.restore_installers()
        self.root.destroy()

    def _deepcopy_theme_data(self, theme_data):
        return json.loads(json.dumps(theme_data))

    def _normalize_hex_color(self, value, fallback):
        text = str(value or "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
            return text

        try:
            rgb = self.root.winfo_rgb(text)
            return "#{:02x}{:02x}{:02x}".format(rgb[0] // 256, rgb[1] // 256, rgb[2] // 256)
        except Exception:
            return fallback

    def _apply_theme_data(self, theme_data, selected_theme_name=None, persist_selection=False):
        merged_theme = self.theme_manager._merge_with_defaults(theme_data)

        colors = merged_theme.get("colors", {})
        fonts = merged_theme.get("fonts", {})
        defaults = self.theme_manager.DEFAULT_THEME

        self.BG_DARK = self._normalize_hex_color(colors.get("bg_dark"), defaults["colors"]["bg_dark"])
        self.BG_MID = self._normalize_hex_color(colors.get("bg_mid"), defaults["colors"]["bg_mid"])
        self.BG_LIGHT = self._normalize_hex_color(colors.get("bg_light"), defaults["colors"]["bg_light"])
        self.FG_TEXT = self._normalize_hex_color(colors.get("fg_text"), defaults["colors"]["fg_text"])
        self.FG_ACCENT = self._normalize_hex_color(colors.get("fg_accent"), defaults["colors"]["fg_accent"])

        self.FONT_FAMILY = str(fonts.get("family", defaults["fonts"]["family"]))
        try:
            self.FONT_SIZE = max(8, min(24, int(fonts.get("size_base", defaults["fonts"]["size_base"]))))
        except Exception:
            self.FONT_SIZE = defaults["fonts"]["size_base"]

        self.current_theme_data = self._deepcopy_theme_data(merged_theme)
        self.current_theme_data["colors"]["bg_dark"] = self.BG_DARK
        self.current_theme_data["colors"]["bg_mid"] = self.BG_MID
        self.current_theme_data["colors"]["bg_light"] = self.BG_LIGHT
        self.current_theme_data["colors"]["fg_text"] = self.FG_TEXT
        self.current_theme_data["colors"]["fg_accent"] = self.FG_ACCENT
        self.current_theme_data["fonts"]["family"] = self.FONT_FAMILY
        self.current_theme_data["fonts"]["size_base"] = self.FONT_SIZE

        self.root.configure(bg=self.BG_DARK)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TFrame", background=self.BG_DARK)
        style.configure("Dark.TLabel", background=self.BG_DARK, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE))
        style.configure("Dark.TButton", background=self.BG_MID, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, max(8, self.FONT_SIZE - 1)))
        style.map("Dark.TButton", background=[("active", self.BG_LIGHT)], foreground=[("active", self.FG_TEXT)])
        style.configure("Dark.TEntry", fieldbackground=self.BG_MID, background=self.BG_MID, foreground=self.FG_TEXT)
        style.configure("Dark.TCheckbutton", background=self.BG_DARK, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE))
        style.map("Dark.TCheckbutton", background=[("active", self.BG_DARK)], foreground=[("active", self.FG_TEXT)])
        style.configure("Dark.TRadiobutton", background=self.BG_DARK, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, self.FONT_SIZE))
        style.map("Dark.TRadiobutton", background=[("active", self.BG_DARK)], foreground=[("active", self.FG_TEXT)])
        style.configure("TNotebook", background=self.BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.BG_MID, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, max(8, self.FONT_SIZE - 1)), focuscolor="none")
        style.map("TNotebook.Tab", background=[("selected", self.BG_LIGHT)], focuscolor=[("!focus", "none")])
        style.configure(
            "ThemeEditor.TCombobox",
            fieldbackground=self.BG_MID,
            background=self.BG_MID,
            foreground=self.FG_TEXT,
            arrowcolor=self.FG_TEXT,
            bordercolor=self.BG_LIGHT,
            lightcolor=self.BG_LIGHT,
            darkcolor=self.BG_LIGHT,
            relief="flat",
        )
        style.map(
            "ThemeEditor.TCombobox",
            fieldbackground=[("readonly", self.BG_MID)],
            foreground=[("readonly", self.FG_TEXT)],
            selectbackground=[("readonly", self.BG_MID)],
            selectforeground=[("readonly", self.FG_TEXT)],
        )

        if hasattr(self, "settings_window") and self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.configure(bg=self.BG_DARK)

        if hasattr(self, "star_btn") and self.star_btn:
            self.star_btn.config(bg=self.BG_DARK, activebackground=self.BG_DARK)
        if hasattr(self, "auto_rejoin_btn") and self.auto_rejoin_btn:
            self.auto_rejoin_btn.config(bg=self.BG_DARK, activebackground=self.BG_DARK)
        if hasattr(self, "discord_btn") and self.discord_btn:
            self.discord_btn.config(bg=self.BG_DARK, activebackground=self.BG_DARK)

        for widget_name in (
            "topmost_check",
            "multi_roblox_check",
            "confirm_check",
            "multi_select_check",
            "disable_launch_popup_check",
            "auto_tile_check",
            "start_menu_check",
            "rename_check",
            "anti_afk_check",
        ):
            widget = getattr(self, widget_name, None)
            if widget:
                try:
                    widget.configure(style="Dark.TCheckbutton")
                except Exception:
                    pass

        settings_btn = getattr(self, "settings_btn", None)
        if settings_btn:
            try:
                settings_btn.configure(bg=self.BG_DARK, fg=self.FG_TEXT, activebackground=self.BG_MID, activeforeground=self.FG_TEXT)
            except Exception:
                pass

        for widget_name in (
            "key_button",
            "max_games_spinner",
            "interval_spinner",
            "amount_spinner",
            "optimize_ram_limit_entry",
        ):
            widget = getattr(self, widget_name, None)
            if widget:
                try:
                    widget.configure(bg=self.BG_MID, fg=self.FG_TEXT, buttonbackground=self.BG_LIGHT, readonlybackground=self.BG_MID, selectbackground=self.FG_ACCENT, selectforeground=self.FG_TEXT, insertbackground=self.FG_TEXT, highlightbackground=self.BG_LIGHT)
                except Exception:
                    pass

        for widget_name in (
            "theme_editor_shell",
            "theme_editor_area",
            "theme_editor_canvas",
            "theme_editor_content",
            "theme_color_section",
            "theme_color_rows",
            "theme_font_section",
        ):
            widget = getattr(self, widget_name, None)
            if widget:
                try:
                    widget.configure(bg=self.BG_MID)
                except Exception:
                    pass

        editor_widgets = getattr(self, "theme_editor_widgets", [])
        color_swatch_widgets = getattr(self, "theme_color_swatch_widgets", {})
        for widget in editor_widgets:
            try:
                if widget in color_swatch_widgets.values():
                    continue
                if isinstance(widget, tk.Entry):
                    widget.configure(bg=self.BG_MID, fg=self.FG_TEXT, insertbackground=self.FG_TEXT, highlightbackground=self.BG_LIGHT, highlightcolor=self.FG_ACCENT)
                elif isinstance(widget, tk.Button):
                    widget.configure(bg=self.BG_MID, fg=self.FG_TEXT, activebackground=self.BG_LIGHT, activeforeground=self.FG_TEXT)
                elif isinstance(widget, tk.Checkbutton):
                    widget.configure(bg=self.BG_MID, fg=self.FG_TEXT, selectcolor=self.BG_LIGHT, activebackground=self.BG_MID, activeforeground=self.FG_TEXT)
                elif isinstance(widget, tk.Label):
                    widget.configure(bg=self.BG_MID, fg=self.FG_TEXT)
                elif isinstance(widget, tk.Frame):
                    widget.configure(bg=self.BG_MID)
            except Exception:
                pass

        color_vars = getattr(self, "theme_color_vars", {})
        for key, swatch in color_swatch_widgets.items():
            try:
                value = color_vars.get(key).get().strip() if key in color_vars else ""
                if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                    swatch.configure(bg=value)
            except Exception:
                pass

        for widget_name in ("theme_family_combo",):
            widget = getattr(self, widget_name, None)
            if widget:
                try:
                    widget.configure(style="ThemeEditor.TCombobox")
                except Exception:
                    pass

        if hasattr(self, "account_list") and self.account_list:
            self.account_list.configure(bg=self.BG_MID, fg=self.FG_TEXT, selectbackground=self.FG_ACCENT, selectforeground=self.FG_TEXT)
        if hasattr(self, "game_list") and self.game_list:
            self.game_list.configure(bg=self.BG_MID, fg=self.FG_TEXT, selectbackground=self.FG_ACCENT, selectforeground=self.FG_TEXT)
        if hasattr(self, "encryption_label") and self.encryption_label:
            self.encryption_label.configure(bg=self.BG_DARK)

        if hasattr(self, "account_list"):
            try:
                self.refresh_accounts()
            except Exception:
                pass
        if hasattr(self, "game_list"):
            try:
                self.refresh_game_list()
            except Exception:
                pass

        if persist_selection and selected_theme_name:
            self.settings["selected_theme"] = selected_theme_name
            self.save_settings()

    def _get_current_theme_config_path(self):
        return os.path.join(self.data_folder, "themes", "current_theme.json")

    def _load_current_theme_config(self):
        path = self._get_current_theme_config_path()
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            print(f"[ERROR] Failed to load current theme config: {exc}")
            return None

    def _save_current_theme_config(self, theme_data, source_theme_name="Dark"):
        path = self._get_current_theme_config_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            current_theme_data = self._deepcopy_theme_data(theme_data)
            current_theme_data.pop("metadata", None)
            current_theme_data["source_theme"] = source_theme_name or "Dark"

            with open(path, "w", encoding="utf-8") as handle:
                json.dump(current_theme_data, handle, indent=2)
            return True
        except Exception as exc:
            print(f"[ERROR] Failed to save current theme config: {exc}")
            return False

    def open_theme_manager(self, parent=None, on_themes_changed=None):
        if hasattr(self, "theme_manager_window") and self.theme_manager_window and self.theme_manager_window.winfo_exists():
            self.theme_manager_window.lift()
            self.theme_manager_window.focus()
            return

        owner = parent if parent and parent.winfo_exists() else self.root
        manager_window = tk.Toplevel(owner)
        self.theme_manager_window = manager_window
        self.apply_window_icon(manager_window)
        manager_window.title("Theme Manager")
        manager_window.configure(bg=self.BG_DARK)
        manager_window.geometry("680x420")
        manager_window.resizable(False, False)
        manager_window.transient(owner)

        if self.settings.get("enable_topmost", False):
            manager_window.attributes("-topmost", True)

        if owner is not self.root:
            manager_window.grab_set()

        container = ttk.Frame(manager_window, style="Dark.TFrame")
        container.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(
            container,
            text="Themes",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w", pady=(0, 6))

        list_shell = tk.Frame(container, bg=self.BG_MID, relief="solid", borderwidth=1)
        list_shell.pack(fill="both", expand=True)

        header = tk.Frame(list_shell, bg=self.BG_LIGHT)
        header.pack(fill="x")
        tk.Label(header, text="Name", bg=self.BG_LIGHT, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 9, "bold"), anchor="w", width=18).pack(side="left", padx=(8, 4), pady=6)
        tk.Label(header, text="Author", bg=self.BG_LIGHT, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 9, "bold"), anchor="w", width=16).pack(side="left", padx=4, pady=6)
        tk.Label(header, text="Description", bg=self.BG_LIGHT, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 9, "bold"), anchor="w").pack(side="left", fill="x", expand=True, padx=4, pady=6)

        list_body = tk.Frame(list_shell, bg=self.BG_MID)
        list_body.pack(fill="both", expand=True)

        theme_list_scroll = tk.Scrollbar(list_body, orient="vertical")
        theme_list_scroll.pack(side="right", fill="y")

        theme_list_canvas = tk.Canvas(list_body, bg=self.BG_MID, highlightthickness=0, yscrollcommand=theme_list_scroll.set)
        theme_list_canvas.pack(side="left", fill="both", expand=True)
        theme_list_scroll.config(command=theme_list_canvas.yview)

        theme_list_container = tk.Frame(theme_list_canvas, bg=self.BG_MID)
        theme_list_window = theme_list_canvas.create_window((0, 0), window=theme_list_container, anchor="nw")

        def _sync_theme_list_scrollregion(_event=None):
            theme_list_canvas.configure(scrollregion=theme_list_canvas.bbox("all"))

        def _sync_theme_list_width(event):
            theme_list_canvas.itemconfigure(theme_list_window, width=event.width)

        theme_list_container.bind("<Configure>", _sync_theme_list_scrollregion)
        theme_list_canvas.bind("<Configure>", _sync_theme_list_width)

        selected_theme_name = [None]
        row_widgets = {}

        def _set_row_selected(name):
            selected_theme_name[0] = name
            for row_name, widgets in row_widgets.items():
                is_selected = row_name == name
                row_bg = self.BG_LIGHT if is_selected else self.BG_MID
                for widget in widgets:
                    try:
                        widget.configure(bg=row_bg)
                    except Exception:
                        pass

        def refresh_theme_list(select_name=None):
            for child in theme_list_container.winfo_children():
                child.destroy()
            row_widgets.clear()

            catalog = self.theme_manager.get_available_themes()
            names = sorted(catalog.keys(), key=str.lower)

            for name in names:
                data = self.theme_manager.load_theme(name)
                metadata = data.get("metadata", {})
                author = str(metadata.get("author", ""))
                description = str(metadata.get("description", ""))

                row = tk.Frame(theme_list_container, bg=self.BG_MID)
                row.pack(fill="x", padx=4, pady=1)
                name_label = tk.Label(row, text=name, bg=self.BG_MID, fg=self.FG_TEXT, anchor="w", width=18, font=(self.FONT_FAMILY, 9))
                author_label = tk.Label(row, text=author, bg=self.BG_MID, fg=self.FG_TEXT, anchor="w", width=16, font=(self.FONT_FAMILY, 9))
                desc_label = tk.Label(row, text=description, bg=self.BG_MID, fg=self.FG_TEXT, anchor="w", font=(self.FONT_FAMILY, 9))
                name_label.pack(side="left", padx=(8, 4), pady=5)
                author_label.pack(side="left", padx=4, pady=5)
                desc_label.pack(side="left", fill="x", expand=True, padx=4, pady=5)

                row_widgets[name] = [row, name_label, author_label, desc_label]
                for widget in row_widgets[name]:
                    widget.bind("<Button-1>", lambda _event, n=name: _set_row_selected(n))

            preferred = select_name
            if not preferred and selected_theme_name[0] in names:
                preferred = selected_theme_name[0]
            if not preferred and names:
                preferred = names[0]
            if preferred:
                for name in names:
                    if name.lower() == str(preferred).lower():
                        preferred = name
                        break
                _set_row_selected(preferred)

        def get_selected_theme_name():
            return selected_theme_name[0]

        def import_theme():
            path = filedialog.askopenfilename(
                title="Import Theme JSON",
                filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
                parent=manager_window,
            )
            if not path:
                return

            if not self.theme_manager.import_theme(path):
                messagebox.showerror("Import Failed", "Could not import this theme file.", parent=manager_window)
                return

            imported_name = None
            try:
                with open(path, "r", encoding="utf-8") as f:
                    imported_name = json.load(f).get("metadata", {}).get("name")
            except Exception:
                imported_name = None

            refresh_theme_list(select_name=imported_name)
            if callable(on_themes_changed):
                on_themes_changed(imported_name)

        def export_theme():
            selected_name = get_selected_theme_name()
            if not selected_name:
                messagebox.showwarning("Export Theme", "Select a theme to export.", parent=manager_window)
                return

            path = filedialog.asksaveasfilename(
                title="Export Theme",
                defaultextension=".json",
                initialfile=f"{selected_name}.json",
                filetypes=[("JSON Files", "*.json")],
                parent=manager_window,
            )
            if not path:
                return

            if not self.theme_manager.export_theme(selected_name, path):
                messagebox.showerror("Export Failed", "Could not export theme.", parent=manager_window)
                return

        def remove_theme():
            selected_name = get_selected_theme_name()
            if not selected_name:
                messagebox.showwarning("Remove Theme", "Select a theme to remove.", parent=manager_window)
                return

            themes = self.theme_manager.get_available_themes()
            if selected_name not in themes:
                messagebox.showwarning("Remove Theme", "Theme not found.", parent=manager_window)
                return

            if not messagebox.askyesno("Remove Theme", f"Remove '{selected_name}'?", parent=manager_window):
                return

            if not self.theme_manager.delete_theme(selected_name):
                messagebox.showerror("Remove Failed", "Could not remove theme.", parent=manager_window)
                return

            refresh_theme_list()
            if callable(on_themes_changed):
                on_themes_changed(None)

        button_row = ttk.Frame(container, style="Dark.TFrame")
        button_row.pack(fill="x", pady=(8, 0))

        ttk.Button(button_row, text="Import", style="Dark.TButton", command=import_theme).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(button_row, text="Export", style="Dark.TButton", command=export_theme).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(button_row, text="Remove", style="Dark.TButton", command=remove_theme).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(button_row, text="Close", style="Dark.TButton", command=manager_window.destroy).pack(side="left", fill="x", expand=True, padx=(4, 0))

        def on_close_manager():
            self.theme_manager_window = None
            manager_window.destroy()

        manager_window.protocol("WM_DELETE_WINDOW", on_close_manager)
        refresh_theme_list()

    def load_settings(self):
        """Load UI settings from file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    self.settings = json.load(f)
            else:
                self.settings = {
                    "last_place_id": "",
                    "last_private_server": "",
                    "game_list": [],
                    "favorite_games": [],
                    "enable_topmost": False,
                    "enable_multi_roblox": False,
                    "confirm_before_launch": False,
                    "custom_roblox_launcher_path": "",
                    "max_recent_games": 10,
                    "enable_multi_select": False,
                    "anti_afk_enabled": False,
                    "anti_afk_interval_minutes": 10,
                    "anti_afk_press_time_seconds": 1,
                    "anti_afk_key": "w",
                    "optimize_roblox_ram": False,
                    "disable_launch_popup": False,
                    "auto_rejoin_configs": {},
                    "multi_roblox_method": "default",
                    "last_joined_user": "",
                    "auto_tile_windows": False,
                    "selected_theme": "Dark",
                    "rejoin_webhook": {},
                    "websocket_enabled": False,
                    "websocket_port": 8765,
                    "websocket_require_password": False
                }
        except:
            self.settings = {
                "last_place_id": "",
                "last_private_server": "",
                "game_list": [],
                "favorite_games": [],
                "enable_topmost": False,
                "enable_multi_roblox": False,
                "confirm_before_launch": False,
                "custom_roblox_launcher_path": "",
                "max_recent_games": 10,
                "enable_multi_select": False,
                "anti_afk_enabled": False,
                "anti_afk_interval_minutes": 10,
                "anti_afk_press_time_seconds": 1,
                "anti_afk_key": "w",
                "optimize_roblox_ram": False,
                "auto_rejoin_configs": {},
                "disable_launch_popup": False,
                "multi_roblox_method": "default",
                "last_joined_user": "",
                "auto_tile_windows": False,
                "selected_theme": "Dark",
                "rejoin_webhook": {},
                "websocket_enabled": False,
                "websocket_port": 8765,
                "websocket_require_password": False
            }

        settings_migrated = self._ensure_discord_settings_defaults()
        settings_migrated = self._ensure_websocket_settings_defaults() or settings_migrated
        if "anti_afk_press_count" not in self.settings:
            self.settings["anti_afk_press_count"] = self.settings.get("anti_afk_press_time_seconds", self.settings.get("anti_afk_key_amount", 1))
            settings_migrated = True
        if "anti_afk_press_time_seconds" not in self.settings:
            self.settings["anti_afk_press_time_seconds"] = self.settings.get("anti_afk_key_amount", 1)
            settings_migrated = True
        if "optimize_roblox_ram" not in self.settings:
            self.settings["optimize_roblox_ram"] = False
            settings_migrated = True
        if "optimize_roblox_ram_limit_mb" not in self.settings:
            self.settings["optimize_roblox_ram_limit_mb"] = 750
            settings_migrated = True
        if "dashboard_webhook_url" not in self.settings:
            self.settings["dashboard_webhook_url"] = ""
            settings_migrated = True
        if "dashboard_auto_report" not in self.settings:
            self.settings["dashboard_auto_report"] = False
            settings_migrated = True
        if "dashboard_report_interval" not in self.settings:
            self.settings["dashboard_report_interval"] = 60
            settings_migrated = True
        if "watchlist_webhook_url" not in self.settings:
            self.settings["watchlist_webhook_url"] = ""
            settings_migrated = True
        if "watchlist_interval" not in self.settings:
            self.settings["watchlist_interval"] = 300
            settings_migrated = True
        if "watchlist_ping_id" not in self.settings:
            self.settings["watchlist_ping_id"] = ""
            settings_migrated = True
        if "watchlist_tracking_enabled" not in self.settings:
            self.settings["watchlist_tracking_enabled"] = True
            settings_migrated = True
        if settings_migrated:
            try:
                with open(self.settings_file, 'w') as f:
                    json.dump(self.settings, f, indent=2)
            except Exception as e:
                print(f"[ERROR] Failed to persist migrated Discord settings: {e}")

        if self.settings.get("enable_topmost", False):
            self.root.attributes("-topmost", True)
        
        if self.settings.get("enable_multi_roblox", False):
            self.root.after(100, self.initialize_multi_roblox)

    def _get_roblox_launcher_config(self):
        launcher_pref = self.settings.get("roblox_launcher", "default")
        custom_path = str(self.settings.get("custom_roblox_launcher_path", "") or "").strip()
        return launcher_pref, custom_path

    def apply_window_icon(self, window):
        icon_path = self.icon_path

        if icon_path and os.path.exists(icon_path):
            try:
                window.iconbitmap(icon_path)
            except Exception as e:
                print(f"[ERROR] Could not set window icon: {e}")

    def check_for_updates(self):
        """Check for updates from GitHub releases"""
        try:
            print("[INFO] Checking for updates...")
            response = requests.get(
                "https://api.github.com/repos/evanovar/RobloxAccountManager/releases/latest",
                timeout=5
            )
            
            if response.status_code == 200:
                latest_release = response.json()
                latest_version = latest_release.get("tag_name", "").lstrip("v")
                
                current_clean = re.sub(r'(alpha|beta).*$', '', self.APP_VERSION, flags=re.IGNORECASE)
                latest_clean = re.sub(r'(alpha|beta).*$', '', latest_version, flags=re.IGNORECASE)
                
                current_parts = tuple(map(int, current_clean.split(".")))
                latest_parts = tuple(map(int, latest_clean.split(".")))
                
                if latest_parts > current_parts:
                    print(f"[WARNING] New version available: {latest_version}")
                    self.root.after(0, lambda: self.show_update_notification(latest_version))
                else:
                    print(f"[SUCCESS] You are on the latest version ({self.APP_VERSION})")
            else:
                print(f"[ERROR] Failed to check for updates (Status: {response.status_code})")
                
        except Exception as e:
            print(f"[ERROR] Error checking for updates: {str(e)}")

    def show_update_notification(self, latest_version):
        """Show update notification dialog with download options"""
        update_window = tk.Toplevel(self.root)
        self.apply_window_icon(update_window)
        update_window.title("Update Available")
        update_window.geometry("450x280")
        update_window.configure(bg=self.BG_DARK)
        update_window.resizable(False, False)
        update_window.transient(self.root)
        
        if self.settings.get("enable_topmost", False):
            update_window.attributes("-topmost", True)
        
        update_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (update_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (update_window.winfo_height() // 2)
        update_window.geometry(f"+{x}+{y}")
        
        container = ttk.Frame(update_window, style="Dark.TFrame")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            container,
            text="🎉 New Update Available!",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 12, "bold")
        ).pack(anchor="w", pady=(0, 15))
        
        info_frame = ttk.Frame(container, style="Dark.TFrame", relief="solid", borderwidth=0)
        info_frame.pack(fill="x", pady=(0, 15))
        
        info_inner = ttk.Frame(info_frame, style="Dark.TFrame")
        info_inner.pack(fill="x", padx=15, pady=12)
        
        ttk.Label(
            info_inner,
            text=f"Current Version: {self.APP_VERSION}",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        ).pack(fill="x")
        
        ttk.Label(
            info_inner,
            text=f"Latest Version: {latest_version}",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9, "bold")
        ).pack(fill="x", pady=(5, 0))
        
        progress_outer = tk.Frame(container, bg=self.BG_LIGHT, relief="solid", borderwidth=1)
        progress_outer.pack(fill="x", pady=(0, 10))
        
        progress_inner = tk.Frame(progress_outer, bg=self.BG_MID, height=22)
        progress_inner.pack(fill="x", padx=1, pady=1)
        progress_inner.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_inner, bg=self.BG_LIGHT, width=0)
        progress_fill.place(x=0, y=0, relheight=1)
        
        progress_label = tk.Label(
            progress_inner,
            text="0%",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=(self.FONT_FAMILY, 9, "bold")
        )
        progress_label.place(relx=0.5, rely=0.5, anchor="center")
        
        status_label = ttk.Label(
            container,
            text="Choose how to update:",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        )
        status_label.pack(anchor="w", pady=(5, 8))
        
        btn_frame = ttk.Frame(container, style="Dark.TFrame")
        btn_frame.pack(side="bottom", fill="x")
        
        def update_progress(percent):
            """Update the custom progress bar"""
            progress_inner.update_idletasks()
            total_width = progress_inner.winfo_width()
            fill_width = int((percent / 100) * total_width)
            progress_fill.place(x=0, y=0, relheight=1, width=fill_width)
            
            label_x = total_width // 2
            if fill_width >= label_x:
                progress_label.config(bg=self.BG_LIGHT, fg=self.BG_DARK)
            else:
                progress_label.config(bg=self.BG_MID, fg=self.FG_TEXT)
            
            progress_label.config(text=f"{int(percent)}%")
            update_window.update()
        
        def download_update():
            """Download and replace current executable using batch script"""
            try:
                auto_btn.config(state="disabled")
                manual_btn.config(state="disabled")
                close_btn.config(state="disabled")
                
                status_label.config(text="Downloading update...")
                update_progress(0)
                
                response = requests.get(
                    "https://api.github.com/repos/evanovar/RobloxAccountManager/releases/latest",
                    timeout=10
                )
                
                if response.status_code != 200:
                    raise Exception("Failed to fetch release information")
                
                release_data = response.json()
                assets = release_data.get("assets", [])
                
                exe_asset = None
                for asset in assets:
                    if asset["name"].endswith(".exe"):
                        exe_asset = asset
                        break
                
                if not exe_asset:
                    raise Exception("No .exe file found in release")
                
                download_url = exe_asset["browser_download_url"]
                file_name = exe_asset["name"]
                
                current_exe = sys.executable
                if current_exe.lower().endswith("python.exe") or current_exe.lower().endswith("pythonw.exe"):
                    current_exe = os.path.abspath(sys.argv[0])
                
                temp_dir = tempfile.gettempdir()
                temp_file = os.path.join(temp_dir, file_name)
                
                status_label.config(text=f"Downloading {file_name}...")
                
                response = requests.get(download_url, stream=True, timeout=30)
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(temp_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                update_progress(progress)
                
                update_progress(100)
                status_label.config(text="Preparing update...")
                update_window.update()
                
                batch_file = os.path.join(temp_dir, "ram_update.bat")
                batch_content = f'''@echo off
setlocal enabledelayedexpansion

if not exist "{temp_file}" (
    exit /b 1
)

for /F %%A in ('dir /b "{temp_file}"') do set size=%%~zA
if !size! LSS 1000000 (
    exit /b 1
)

:wait_loop
copy /Y "{temp_file}" "{current_exe}" >nul 2>&1
if errorlevel 1 (
    timeout /t 0 /nobreak >nul
    goto wait_loop
)

if exist "{temp_file}" del /f /q "{temp_file}"

del /f /q "%~f0"
'''
                with open(batch_file, 'w') as f:
                    f.write(batch_content)
                
                status_label.config(text="Update complete! Please relaunch.")
                update_window.update()
                
                messagebox.showinfo(
                    "Update Complete",
                    "Update has been installed successfully!\n\nPlease close this window and wait a second before launching the application again.",
                    parent=update_window
                )
                
                subprocess.Popen([batch_file], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self.root.quit()
                
            except Exception as e:
                status_label.config(text="Download failed. Try manual update.")
                update_progress(0)
                messagebox.showerror(
                    "Update Failed",
                    f"Failed to update:\n{str(e)}\n\nPlease use Manual Update instead.",
                    parent=update_window
                )
                auto_btn.config(state="normal")
                manual_btn.config(state="normal")
                close_btn.config(state="normal")
        
        def manual_update():
            """Open GitHub releases page"""
            webbrowser.open("https://github.com/evanovar/RobloxAccountManager/releases/latest")
            update_window.destroy()
        
        auto_btn = ttk.Button(
            btn_frame,
            text="Auto Update",
            style="Dark.TButton",
            command=download_update
        )
        auto_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        manual_btn = ttk.Button(
            btn_frame,
            text="Manual Update",
            style="Dark.TButton",
            command=manual_update
        )
        manual_btn.pack(side="left", fill="x", expand=True, padx=(2.5, 2.5))
        
        close_btn = ttk.Button(
            btn_frame,
            text="Close",
            style="Dark.TButton",
            command=update_window.destroy
        )
        close_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))

    def toggle_add_account_dropdown(self):
        """Toggle the Add Account dropdown menu"""
        self.add_account_dropdown_visible = not self.add_account_dropdown_visible
        if self.add_account_dropdown_visible:
            self.show_add_account_dropdown()
        else:
            self.hide_add_account_dropdown()
    
    def on_add_account_split_click(self, event):
        """Handle clicks on the unified split button: left area adds account, right area opens dropdown."""
        try:
            width = event.widget.winfo_width()
        except Exception:
            width = 0
        arrow_zone = 24
        if event.x >= max(0, width - arrow_zone):
            self.toggle_add_account_dropdown()
        else:
            self.add_account()
        return "break"
    
    def show_add_account_dropdown(self):
        """Show the Add Account dropdown menu"""
        if self.add_account_dropdown is not None:
            self.add_account_dropdown.destroy()
        
        self.add_account_dropdown = tk.Toplevel(self.root)
        self.add_account_dropdown.overrideredirect(True)
        self.add_account_dropdown.configure(bg=self.BG_MID, highlightthickness=1, highlightbackground="white")
        
        self.position_add_account_dropdown()
        
        import_cookie_btn = tk.Button(
            self.add_account_dropdown,
            text="Import Cookie",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: [self.hide_add_account_dropdown(), self.import_cookie()]
        )
        import_cookie_btn.pack(fill="x", padx=2, pady=1)
        
        javascript_btn = tk.Button(
            self.add_account_dropdown,
            text="Javascript",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: [self.hide_add_account_dropdown(), self.javascript_import()]
        )
        javascript_btn.pack(fill="x", padx=2, pady=1)
        
        self.position_add_account_dropdown()
        
        if self.settings.get("enable_topmost", False):
            self.add_account_dropdown.attributes("-topmost", True)
        
        self.add_account_dropdown.bind("<FocusOut>", lambda e: self.hide_add_account_dropdown())

    def position_add_account_dropdown(self):
        """Position the dropdown right under the split button and match its width."""
        try:
            if self.add_account_dropdown is None or not self.add_account_dropdown_visible:
                return
            self.root.update_idletasks()
            x = self.add_account_split_btn.winfo_rootx()
            y = self.add_account_split_btn.winfo_rooty() + self.add_account_split_btn.winfo_height()
            width = self.add_account_split_btn.winfo_width()
            req_h = self.add_account_dropdown.winfo_reqheight()
            self.add_account_dropdown.geometry(f"{width}x{req_h}+{x}+{y}")
            if self.settings.get("enable_topmost", False):
                self.add_account_dropdown.attributes("-topmost", True)
        except Exception:
            pass

    def on_root_configure(self, event=None):
        """Called when the main window moves/resizes; keep dropdown attached."""
        if self.add_account_dropdown_visible and self.add_account_dropdown is not None:
            self.position_add_account_dropdown()
        if self.join_place_dropdown_visible and self.join_place_dropdown is not None:
            self.position_join_place_dropdown()
    
    def hide_add_account_dropdown(self):
        """Hide the Add Account dropdown menu"""
        if self.add_account_dropdown is not None:
            self.add_account_dropdown.destroy()
            self.add_account_dropdown = None
        self.add_account_dropdown_visible = False
    
    def is_child_of(self, child, parent):
        """Check if a widget is a child of another widget"""
        while child is not None:
            if child == parent:
                return True
            child = child.master
        return False
    
    def hide_dropdown_on_click_outside(self, event):
        """Hide dropdown when clicking outside of it"""
        widget = event.widget
        if self.add_account_dropdown_visible and self.add_account_dropdown is not None:
            if not self.is_child_of(widget, self.add_account_split_btn):
                try:
                    if not self.is_child_of(widget, self.add_account_dropdown):
                        self.hide_add_account_dropdown()
                except:
                    self.hide_add_account_dropdown()
        
        if self.join_place_dropdown_visible and self.join_place_dropdown is not None:
            if not self.is_child_of(widget, self.join_place_split_btn):
                try:
                    if not self.is_child_of(widget, self.join_place_dropdown):
                        self.hide_join_place_dropdown()
                except:
                    self.hide_join_place_dropdown()

    def toggle_join_place_dropdown(self):
        """Toggle the Join Place dropdown menu"""
        self.join_place_dropdown_visible = not self.join_place_dropdown_visible
        if self.join_place_dropdown_visible:
            self.show_join_place_dropdown()
        else:
            self.hide_join_place_dropdown()
    
    def on_join_place_split_click(self, event):
        """Handle clicks on the button: left click launches game, right click shows dropdown."""
        self.launch_game()
        return "break"
    
    def on_join_place_right_click(self, event):
        """Handle right click on the button: show dropdown menu."""
        self.toggle_join_place_dropdown()
        return "break"
    
    def on_join_place_hover(self, event):
        """Show tooltip when hovering over Join Place ID button"""
        if self.tooltip_timer:
            self.root.after_cancel(self.tooltip_timer)
        
        def show_tooltip():
            if self.tooltip:
                return
            
            x = event.widget.winfo_rootx() + event.widget.winfo_width() // 2
            y = event.widget.winfo_rooty() + event.widget.winfo_height() + 5
            
            self.tooltip = tk.Toplevel(self.root)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")
            
            label = tk.Label(
                self.tooltip,
                text="Right click to see more options",
                bg="#333333",
                fg="white",
                font=("Segoe UI", 9),
                padx=8,
                pady=4,
                relief="solid",
                borderwidth=1
            )
            label.pack()
            
            self.tooltip.update_idletasks()
            tooltip_width = self.tooltip.winfo_width()
            self.tooltip.wm_geometry(f"+{x - tooltip_width // 2}+{y}")
            
            if self.settings.get("enable_topmost", False):
                self.tooltip.attributes("-topmost", True)
        
        self.tooltip_timer = self.root.after(800, show_tooltip)
    
    def on_join_place_leave(self, event):
        """Hide tooltip when leaving Join Place ID button"""
        if self.tooltip_timer:
            self.root.after_cancel(self.tooltip_timer)
            self.tooltip_timer = None
        
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None
    
    def show_join_place_dropdown(self):
        """Show the Join Place dropdown menu"""
        if self.join_place_dropdown is not None:
            self.join_place_dropdown.destroy()
        
        self.join_place_dropdown = tk.Toplevel(self.root)
        self.join_place_dropdown.overrideredirect(True)
        self.join_place_dropdown.configure(bg=self.BG_MID, highlightthickness=1, highlightbackground="white")
        
        self.position_join_place_dropdown()
        
        join_user_btn = tk.Button(
            self.join_place_dropdown,
            text="Join User",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: [self.hide_join_place_dropdown(), self.join_user()]
        )
        join_user_btn.pack(fill="x", padx=2, pady=1)
        
        job_id_btn = tk.Button(
            self.join_place_dropdown,
            text="Job-ID",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: [self.hide_join_place_dropdown(), self.join_by_job_id()]
        )
        job_id_btn.pack(fill="x", padx=2, pady=1)
        
        small_server_btn = tk.Button(
            self.join_place_dropdown,
            text="Small Server",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: [self.hide_join_place_dropdown(), self.join_small_server()]
        )
        small_server_btn.pack(fill="x", padx=2, pady=1)
        
        self.position_join_place_dropdown()
        
        if self.settings.get("enable_topmost", False):
            self.join_place_dropdown.attributes("-topmost", True)
        
        self.join_place_dropdown.bind("<FocusOut>", lambda e: self.hide_join_place_dropdown())

    def position_join_place_dropdown(self):
        """Position the dropdown right under the split button and match its width."""
        try:
            if self.join_place_dropdown is None or not self.join_place_dropdown_visible:
                return
            self.root.update_idletasks()
            x = self.join_place_split_btn.winfo_rootx()
            y = self.join_place_split_btn.winfo_rooty() + self.join_place_split_btn.winfo_height()
            width = self.join_place_split_btn.winfo_width()
            req_h = self.join_place_dropdown.winfo_reqheight()
            self.join_place_dropdown.geometry(f"{width}x{req_h}+{x}+{y}")
            if self.settings.get("enable_topmost", False):
                self.join_place_dropdown.attributes("-topmost", True)
        except Exception:
            pass
    
    def hide_join_place_dropdown(self):
        """Hide the Join Place dropdown menu"""
        if self.join_place_dropdown is not None:
            self.join_place_dropdown.destroy()
            self.join_place_dropdown = None
        self.join_place_dropdown_visible = False

    def save_settings(self, force_immediate=False):
        """Save UI settings to file with debouncing"""
        if self._save_settings_timer is not None:
            try:
                self.root.after_cancel(self._save_settings_timer)
            except:
                pass
            self._save_settings_timer = None
        
        def do_save():
            temp_file = self.settings_file + ".tmp"
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(self.settings, f, indent=2)
                if os.path.exists(temp_file):
                    os.replace(temp_file, self.settings_file)
            except Exception as e:
                print(f"[ERROR] Failed to save settings: {e}")
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
            self._save_settings_timer = None
        
        if force_immediate:
            do_save()
        else:
            self._save_settings_timer = self.root.after(500, do_save)

    def _default_discord_integration_settings(self, mode):
        base = {
            "enabled": False,
            "enable_ping": False,
            "ping_user_id": "",
            "ping_on_error": True,
            "log_everything": False,
            "log_errors": True,
            "log_success": True,
            "log_warnings": True,
            "log_info": False,
            "log_auto_rejoin": True,
            "log_auto_rejoin_console": False,
            "screenshot_interval_minutes": 60,
            "screenshot_enabled": False,
        }
        if mode == "bot":
            base.update({
                "channel_id": None,
            })
        else:
            base.update({
                "url": "",
            })
        return base

    def _default_websocket_settings(self):
        return {
            "websocket_enabled": False,
            "websocket_port": 8765,
            "websocket_require_password": False,
        }

    def _ensure_websocket_settings_defaults(self):
        changed = False
        for key, value in self._default_websocket_settings().items():
            if key not in self.settings:
                self.settings[key] = value
                changed = True
        return changed

    def _ensure_discord_settings_defaults(self):
        changed = False
        old_mode = self.settings.get("discord_webhook", {}).pop("mode", None)
        if old_mode in ("webhook", "bot") and "discord_ui_mode" not in self.settings:
            self.settings["discord_ui_mode"] = old_mode
            changed = True
        elif old_mode is not None:
            changed = True

        self.settings.setdefault("discord_ui_mode", "webhook")
        default_console_filters = [
            "Got authentication ticket!",
            "You are on the latest version",
        ]
        console_filters = self.settings.get("console_filters")
        if not isinstance(console_filters, list):
            self.settings["console_filters"] = default_console_filters.copy()
            changed = True
        else:
            for value in default_console_filters:
                if value not in console_filters:
                    console_filters.append(value)
                    changed = True

        webhook_cfg = self.settings.setdefault("discord_webhook", {})

        for key, value in self._default_discord_integration_settings("webhook").items():
            webhook_cfg.setdefault(key, value)

        self.settings["discord_webhook"] = webhook_cfg
        return changed

    def _process_ui_task_queue(self):
        try:
            while True:
                func, args, kwargs, done_event, result_box = self._ui_task_queue.get_nowait()
                try:
                    result_box["value"] = func(*args, **kwargs)
                except Exception as exc:
                    result_box["error"] = exc
                finally:
                    if done_event is not None:
                        done_event.set()
        except queue.Empty:
            pass

        try:
            if self.root.winfo_exists():
                self.root.after(50, self._process_ui_task_queue)
        except Exception:
            pass

    def _run_on_ui_thread(self, func, *args, wait=True, timeout=30, **kwargs):
        if threading.current_thread() is threading.main_thread():
            return func(*args, **kwargs)

        done_event = threading.Event() if wait else None
        result_box = {"value": None, "error": None}
        self._ui_task_queue.put((func, args, kwargs, done_event, result_box))

        if not wait:
            return None

        if not done_event.wait(timeout):
            raise TimeoutError("UI task timed out")
        if result_box["error"] is not None:
            raise result_box["error"]
        return result_box["value"]

    def _get_websocket_password(self):
        try:
            return str(self.manager.get_secure_setting("websocket_password", "") or "")
        except Exception:
            return ""

    def _set_websocket_password(self, password):
        try:
            self.manager.set_secure_setting("websocket_password", str(password or ""))
            return True
        except Exception as exc:
            print(f"[ERROR] Failed to save websocket password: {exc}")
            return False

    def _get_websocket_port(self):
        try:
            return int(self.settings.get("websocket_port", 8765))
        except Exception:
            return 8765

    def _set_last_joined_user(self, username):
        self.settings["last_joined_user"] = username
        self.save_settings()

    def start_discord_bot(self):
        self.discord_bot.start()

    def stop_discord_bot(self):
        self.discord_bot.stop()

    def start_websocket_server(self):
        if self.websocket_thread and self.websocket_thread.is_alive():
            return

        if not self.settings.get("developer_mode", False):
            print("[WARNING] WebSocket server blocked: Developer Mode is disabled")
            return

        self.websocket_stop_event.clear()
        self.websocket_thread = threading.Thread(
            target=self._websocket_server_thread_main,
            daemon=True,
            name="WebSocketServer",
        )
        self.websocket_thread.start()

    def stop_websocket_server(self):
        self.websocket_stop_event.set()
        loop = self.websocket_loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(lambda: None)
            except Exception:
                pass

        thread = self.websocket_thread
        if thread and thread.is_alive():
            def _join_ws():
                thread.join(timeout=2)
            threading.Thread(target=_join_ws, daemon=True).start()

        self.websocket_thread = None
        self.websocket_loop = None
        self.websocket_running = False

    def restart_websocket_server(self):
        self.stop_websocket_server()
        if self.settings.get("websocket_enabled", False):
            self.start_websocket_server()

    def _websocket_server_thread_main(self):
        loop = asyncio.new_event_loop()
        self.websocket_loop = loop
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._websocket_server_main())
        except Exception as exc:
            print(f"[ERROR] WebSocket server crashed: {exc}")
        finally:
            self.websocket_running = False
            self.websocket_loop = None
            try:
                loop.close()
            except Exception:
                pass

    async def _websocket_server_main(self):
        host = "localhost"
        port = self._get_websocket_port()

        try:
            async with websockets.serve(self._websocket_client_handler, host, port):
                self.websocket_running = True
                print(f"[INFO] WebSocket server started at ws://{host}:{port}")
                while not self.websocket_stop_event.is_set():
                    await asyncio.sleep(0.2)
        except OSError as exc:
            self.websocket_running = False
            print(f"[ERROR] Failed to start WebSocket server on port {port}: {exc}")
        finally:
            if self.websocket_running:
                print("[INFO] WebSocket server stopped")
            self.websocket_running = False

    async def _websocket_client_handler(self, websocket):
        try:
            async for raw_message in websocket:
                response = self._websocket_execute_command(str(raw_message or ""))
                await websocket.send(json.dumps(response, ensure_ascii=False))
        except Exception as exc:
            print(f"[ERROR] WebSocket client handler error: {exc}")

    def _websocket_extract_command_with_auth(self, raw_message):
        message = str(raw_message or "").strip()
        require_password = bool(self.settings.get("websocket_require_password", False))

        if not require_password:
            return True, message, None

        stored_password = self._get_websocket_password()
        if not stored_password:
            return False, "", "Password is required but not set"

        if "|" not in message:
            return False, "", "Missing auth format. Use: AUTH <password> | <command>"

        auth_segment, command_segment = message.split("|", 1)
        auth_segment = auth_segment.strip()
        command_segment = command_segment.strip()

        try:
            auth_parts = shlex.split(auth_segment)
        except Exception:
            auth_parts = auth_segment.split()

        if len(auth_parts) < 2 or auth_parts[0].lower() != "auth":
            return False, "", "Missing auth format. Use: AUTH <password> | <command>"

        provided_password = " ".join(auth_parts[1:])
        if not secrets.compare_digest(provided_password, stored_password):
            return False, "", "Authentication failed"

        return True, command_segment, None

    def _websocket_execute_command(self, raw_message):
        ok, command_text, auth_error = self._websocket_extract_command_with_auth(raw_message)
        if not ok:
            return {"ok": False, "error": auth_error}

        if not command_text:
            return {"ok": False, "error": "Empty command"}

        try:
            payload = json.loads(command_text)
            if isinstance(payload, dict) and "action" in payload:
                action = str(payload["action"]).lower()
                
                if action == "join":
                    account = payload.get("account")
                    place_id = str(payload.get("place_id", "")).strip()
                    if not account:
                        return {"ok": False, "error": "Missing account name"}
                    if not place_id:
                        return {"ok": False, "error": "Missing place ID"}
                    if account not in self.manager.accounts:
                        return {"ok": False, "error": f"Account not found: {account}"}
                    
                    launcher_pref, custom_launcher_path = self._get_roblox_launcher_config()
                    launched = self.manager.launch_roblox(
                        username=account,
                        game_id=place_id,
                        launcher_preference=launcher_pref,
                        custom_launcher_path=custom_launcher_path
                    )
                    if launched:
                        return {"ok": True, "result": "Launched successfully"}
                    else:
                        return {"ok": False, "error": "Launch failed"}

                elif action == "kill":
                    account = payload.get("account")
                    if not account:
                        return {"ok": False, "error": "Missing account name"}
                    
                    resolved_pid = None
                    for entry in list(self.instances_data):
                        if entry.get("username") == account:
                            resolved_pid = entry.get("pid")
                            break
                    
                    if resolved_pid:
                        try:
                            import psutil
                            if psutil.pid_exists(resolved_pid):
                                subprocess.run(['taskkill', '/F', '/PID', str(resolved_pid)],
                                             capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
                                try:
                                    proc = psutil.Process(resolved_pid)
                                    proc.terminate()
                                except:
                                    pass
                                return {"ok": True, "result": "Process terminated successfully"}
                            else:
                                return {"ok": True, "result": "Session already inactive"}
                        except Exception as kill_err:
                            return {"ok": False, "error": f"Failed to terminate process: {kill_err}"}
                    else:
                        return {"ok": True, "result": "Session already inactive"}

                elif action == "status":
                    status_list = []
                    for entry in list(self.instances_data):
                        create_time = entry.get("create_time", 0.0)
                        uptime_str = "00:00:00"
                        if create_time:
                            try:
                                elapsed = int(time.time() - create_time)
                                h = elapsed // 3600
                                m = (elapsed % 3600) // 60
                                s = elapsed % 60
                                uptime_str = f"{h:02d}:{m:02d}:{s:02d}"
                            except:
                                pass
                        
                        status_list.append({
                            "account": entry.get("username", "Unknown"),
                            "pid": entry.get("pid"),
                            "uptime": uptime_str,
                            "place_id": entry.get("place_id", 0)
                        })
                    return {"ok": True, "result": status_list}
                    
                else:
                    return {"ok": False, "error": f"Unsupported action: {action}"}
        except Exception:
            pass

        try:
            parts = shlex.split(command_text)
        except Exception:
            parts = command_text.split()

        if not parts:
            return {"ok": False, "error": "Empty command"}

        action = parts[0].lower()

        try:
            if action == "ping":
                return {"ok": True, "result": "Pong"}

            if action == "getstatus":
                return self._websocket_command_get_status()

            if action == "launch":
                return self._websocket_command_launch(parts)

            if action == "joinuser":
                return self._websocket_command_join_user(parts)

            if action == "autorejoin":
                return self._websocket_command_auto_rejoin(parts)

            return {
                "ok": False,
                "error": "Unknown command",
                "supported": ["Launch", "JoinUser", "GetStatus", "Ping", "AutoRejoin"],
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _websocket_command_launch(self, parts):
        if len(parts) < 3:
            return {"ok": False, "error": "Usage: Launch <account_name> <place_id> [private_server_id] [job_id]"}

        account_name = parts[1]
        place_id = str(parts[2]).strip()
        private_server_id = str(parts[3]).strip() if len(parts) >= 4 else ""
        job_id = str(parts[4]).strip() if len(parts) >= 5 else ""

        if account_name not in self.manager.accounts:
            return {"ok": False, "error": f"Account not found: {account_name}"}
        if not place_id.isdigit():
            return {"ok": False, "error": "Place ID must be numeric"}

        launcher_pref, custom_launcher_path = self._get_roblox_launcher_config()
        launched = self.manager.launch_roblox(
            account_name,
            place_id,
            private_server_id,
            launcher_pref,
            job_id,
            custom_launcher_path,
        )

        if launched:
            try:
                self._run_on_ui_thread(self._set_last_joined_user, account_name, wait=False)
            except Exception:
                pass
            return {
                "ok": True,
                "result": {
                    "action": "Launch",
                    "account": account_name,
                    "place_id": place_id,
                    "private_server_id": private_server_id,
                    "job_id": job_id,
                },
            }
        return {"ok": False, "error": f"Failed to launch account: {account_name}"}

    def _websocket_command_join_user(self, parts):
        if len(parts) < 3:
            return {"ok": False, "error": "Usage: JoinUser <account_name> <user_to_join>"}

        account_name = parts[1]
        user_to_join = parts[2]

        if account_name not in self.manager.accounts:
            return {"ok": False, "error": f"Account not found: {account_name}"}

        user_id = RobloxAPI.get_user_id_from_username(user_to_join)
        if not user_id:
            return {"ok": False, "error": f"User not found: {user_to_join}"}

        account_data = self.manager.accounts.get(account_name)
        account_cookie = account_data.get("cookie") if isinstance(account_data, dict) else None
        if not account_cookie:
            return {"ok": False, "error": f"Missing cookie for account: {account_name}"}

        presence = RobloxAPI.get_player_presence(user_id, account_cookie)
        if not presence:
            return {"ok": False, "error": "Failed to fetch user presence"}
        if not presence.get("in_game"):
            return {
                "ok": False,
                "error": f"{user_to_join} is not currently in-game",
                "status": presence.get("last_location", "Unknown"),
            }

        place_id = str(presence.get("place_id", "") or "")
        game_id = str(presence.get("game_id", "") or "")
        if not place_id:
            return {"ok": False, "error": "Missing place_id in presence response"}

        launcher_pref, custom_launcher_path = self._get_roblox_launcher_config()
        launched = self.manager.launch_roblox(
            account_name,
            place_id,
            "",
            launcher_pref,
            game_id,
            custom_launcher_path,
        )

        if launched:
            try:
                self._run_on_ui_thread(self._set_last_joined_user, account_name, wait=False)
            except Exception:
                pass
            return {
                "ok": True,
                "result": {
                    "action": "JoinUser",
                    "account": account_name,
                    "target_user": user_to_join,
                    "place_id": place_id,
                    "job_id": game_id,
                },
            }
        return {"ok": False, "error": f"Failed to join user {user_to_join} with account {account_name}"}

    def _websocket_command_get_status(self):
        try:
            if not (self.instances_monitor_thread and self.instances_monitor_thread.is_alive()):
                self.start_instances_monitoring()
        except Exception:
            pass

        data = []
        try:
            for entry in list(self.instances_data):
                data.append({
                    "pid": entry.get("pid"),
                    "username": entry.get("username"),
                })
        except Exception:
            data = []

        return {"ok": True, "result": data}

    def _websocket_command_auto_rejoin(self, parts):
        if len(parts) < 3:
            return {"ok": False, "error": "Usage: AutoRejoin <start|stop> <account_name>"}

        mode = parts[1].lower()
        account_name = parts[2]

        if account_name not in self.manager.accounts:
            return {"ok": False, "error": f"Account not found: {account_name}"}

        if mode == "start":
            if account_name not in self.auto_rejoin_configs:
                return {"ok": False, "error": f"No auto-rejoin config for account: {account_name}"}
            self._match_pids_to_accounts([account_name])
            self.start_auto_rejoin_for_account(account_name)
            return {"ok": True, "result": {"action": "AutoRejoin", "mode": "start", "account": account_name}}

        if mode == "stop":
            self.stop_auto_rejoin_for_account(account_name)
            return {"ok": True, "result": {"action": "AutoRejoin", "mode": "stop", "account": account_name}}

        return {"ok": False, "error": "AutoRejoin mode must be 'start' or 'stop'"}

    def is_chrome_installed(self):
        try:
            candidates = []
            pf = os.environ.get('ProgramFiles')
            pfx86 = os.environ.get('ProgramFiles(x86)')
            localapp = os.environ.get('LOCALAPPDATA')
            if pf:
                candidates.append(os.path.join(pf, 'Google', 'Chrome', 'Application', 'chrome.exe'))
            if pfx86:
                candidates.append(os.path.join(pfx86, 'Google', 'Chrome', 'Application', 'chrome.exe'))
            if localapp:
                candidates.append(os.path.join(localapp, 'Google', 'Chrome', 'Application', 'chrome.exe'))

            return any(path and os.path.exists(path) for path in candidates)
        except Exception:
            return False

    def get_browser_path(self):
        """Get path to the selected browser (Chrome or Chromium)."""
        browser_type = self.settings.get("browser_type", "chrome")
        
        if browser_type == "chromium":
            chromium_path = os.path.join(self.data_folder, "Chromium", "chrome-win64", "chrome.exe")
            if os.path.exists(chromium_path):
                return chromium_path, "Chromium"
            browser_type = "chrome"
        
        if browser_type == "chrome":
            candidates = []
            pf = os.environ.get('ProgramFiles')
            pfx86 = os.environ.get('ProgramFiles(x86)')
            localapp = os.environ.get('LOCALAPPDATA')
            if pf:
                candidates.append(os.path.join(pf, 'Google', 'Chrome', 'Application', 'chrome.exe'))
            if pfx86:
                candidates.append(os.path.join(pfx86, 'Google', 'Chrome', 'Application', 'chrome.exe'))
            if localapp:
                candidates.append(os.path.join(localapp, 'Google', 'Chrome', 'Application', 'chrome.exe'))
            for path in candidates:
                if path and os.path.exists(path):
                    return path, "Google Chrome"
        
        return None, None

    def update_game_name_on_startup(self):
        """Check both Place ID and Private Server fields to update game name on startup"""
        place_id = self.place_entry.get().strip()
        private_server = self.private_server_entry.get().strip()

        if place_id:
            self.update_game_name()
        elif private_server:
            vip_match = re.search(r'roblox\.com/games/(\d+)', private_server)
            if vip_match:
                self.update_game_name_from_id(vip_match.group(1))
            else:
                share_match = re.search(r'roblox\.com/share\?[^#]*code=([A-Za-z0-9]+)', private_server)
                if share_match:
                    def _resolve_startup(ps=private_server):
                        ck = next((d.get('cookie') for d in self.manager.accounts.values() if isinstance(d, dict) and d.get('cookie')), None)
                        resolved_pid, _ = RobloxAPI.resolve_share_url(ps, cookie=ck)
                        if resolved_pid:
                            self.root.after(0, lambda: self.update_game_name_from_id(resolved_pid))
                    threading.Thread(target=_resolve_startup, daemon=True).start()

    def on_place_id_change(self, event=None):
        place_id = self.place_entry.get().strip()
        self.settings["last_place_id"] = place_id
        self.save_settings()
        self.update_game_name()

    def on_private_server_change(self, event=None):        
        private_server = self.private_server_entry.get().strip()
        place_id_input = self.place_entry.get().strip()

        self.settings["last_private_server"] = private_server
        self.save_settings()

        if not place_id_input and private_server:
            vip_match = re.search(r'roblox\.com/games/(\d+)', private_server)
            if vip_match:
                self.update_game_name_from_id(vip_match.group(1))
            else:
                share_match = re.search(r'roblox\.com/share\?[^#]*code=([A-Za-z0-9]+)', private_server)
                if share_match:
                    def _resolve_and_update(ps=private_server):
                        ck = next((d.get('cookie') for d in self.manager.accounts.values() if isinstance(d, dict) and d.get('cookie')), None)
                        resolved_pid, _ = RobloxAPI.resolve_share_url(ps, cookie=ck)
                        if resolved_pid:
                            self.root.after(0, lambda: self.update_game_name_from_id(resolved_pid))
                    threading.Thread(target=_resolve_and_update, daemon=True).start()
    
    def update_game_name_from_id(self, place_id):
        """Update game name label from a specific place ID (without reading from text box)"""
        if self._game_name_after_id is not None:
            try:
                self.root.after_cancel(self._game_name_after_id)
            except Exception:
                pass
            self._game_name_after_id = None

        def schedule_fetch():
            if not place_id or not place_id.isdigit():
                self.game_name_label.config(text="")
                return

            def worker(pid):
                name = RobloxAPI.get_game_name(pid)
                if name:
                    max_name_length = 20
                    if len(name) > max_name_length:
                        name = name[:max_name_length-2] + ".."
                    display_text = f"Current: {name}"
                else:
                    display_text = ""
                
                def update_label(text=display_text):
                    try:
                        self.game_name_label.config(text=text)
                    except:
                        pass
                
                self.root.after(0, update_label)

            threading.Thread(target=worker, args=(place_id,), daemon=True).start()

        self._game_name_after_id = self.root.after(350, schedule_fetch)
    

    def update_game_name(self):
        """Debounced, non-blocking update of the game name label"""
        if self._game_name_after_id is not None:
            try:
                self.root.after_cancel(self._game_name_after_id)
            except Exception:
                pass
            self._game_name_after_id = None

        def schedule_fetch():
            place_id = self.place_entry.get().strip()
            if not place_id or not place_id.isdigit():
                self.game_name_label.config(text="")
                return

            def worker(pid):
                name = RobloxAPI.get_game_name(pid)
                if name:
                    max_name_length = 20
                    if len(name) > max_name_length:
                        name = name[:max_name_length-2] + ".."
                    display_text = f"Current: {name}"
                else:
                    display_text = ""
                
                def update_label(text=display_text):
                    try:
                        self.game_name_label.config(text=text)
                    except:
                        pass
                
                self.root.after(0, update_label)

            threading.Thread(target=worker, args=(place_id,), daemon=True).start()

        self._game_name_after_id = self.root.after(350, schedule_fetch)

    def add_game_to_list(self, place_id, game_name, private_server=""):
        """Add a game to the saved list (max based on settings)"""
        for game in self.settings["game_list"]:
            if game["place_id"] == place_id and game.get("private_server", "") == private_server:
                return
        
        self.settings["game_list"].insert(0, {
            "place_id": place_id,
            "name": game_name,
            "private_server": private_server
        })
        
        max_games = self.settings.get("max_recent_games", 10)
        if len(self.settings["game_list"]) > max_games:
            self.settings["game_list"] = self.settings["game_list"][:max_games]
        
        self.save_settings()
        self.refresh_game_list()

    def refresh_game_list(self):
        """Refresh the game list display"""
        self.game_list.delete(0, tk.END)
        for game in self.settings["game_list"]:
            private_server = game.get("private_server", "")
            prefix = "[P] " if private_server else ""
            display_text = f"{prefix}{game['name']} ({game['place_id']})"
            self.game_list.insert(tk.END, display_text)

    def on_game_select(self, event=None):
        """Called when a game is selected from the list"""
        selection = self.game_list.curselection()
        if selection:
            index = selection[0]
            game = self.settings["game_list"][index]
            self.place_entry.delete(0, tk.END)
            self.place_entry.insert(0, game["place_id"])
            self.settings["last_place_id"] = game["place_id"]
            
            private_server = game.get("private_server", "")
            self.private_server_entry.delete(0, tk.END)
            self.private_server_entry.insert(0, private_server)
            self.settings["last_private_server"] = private_server
            
            self.save_settings()
            self.update_game_name()

    def delete_game_from_list(self):
        """Delete selected game from the list"""
        selection = self.game_list.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a game to delete.")
            return
        
        index = selection[0]
        game = self.settings["game_list"][index]
        confirm = messagebox.askyesno("Confirm Delete", f"Delete '{game['name']}' from list?")
        if confirm:
            self.settings["game_list"].pop(index)
            self.save_settings()
            self.refresh_game_list()
            messagebox.showinfo("Success", "Game removed from list!")

    def _get_groups(self):
        return self.settings.get("groups", {})

    def _save_groups(self, groups):
        self.settings["groups"] = groups
        self.settings["group_collapsed"] = list(self._collapsed_groups)
        self.save_settings()

    def _get_username_group(self, username):
        for gname, members in self._get_groups().items():
            if username in members:
                return gname
        return None

    def _add_account_to_group(self, username, group_name):
        groups = self._get_groups()
        if group_name not in groups:
            groups[group_name] = []
        for gn in list(groups):
            if gn != group_name and username in groups[gn]:
                groups[gn].remove(username)
        if username not in groups[group_name]:
            groups[group_name].append(username)
        self._save_groups(groups)
        self.refresh_accounts()

    def _remove_account_from_group(self, username):
        groups = self._get_groups()
        for gn in list(groups):
            if username in groups[gn]:
                groups[gn].remove(username)
        self._save_groups(groups)
        self.refresh_accounts()

    def _handle_group_header_click(self, index):
        if index < 0 or index >= len(self._list_row_map):
            return
        kind, name = self._list_row_map[index]
        if kind != "group_header":
            return
        if name in self._collapsed_groups:
            self._collapsed_groups.discard(name)
        else:
            self._collapsed_groups.add(name)
        self._save_groups(self._get_groups())
        self.refresh_accounts()

    def _build_group_header_text(self, group_name, member_count, collapsed):
        arrow = "v" if collapsed else "^"
        prefix = f" {group_name} ({member_count}) "

        try:
            lb_font = tkfont.Font(font=self.account_list.cget("font"))
            list_width = self.account_list.winfo_width()
            if list_width <= 1:
                list_width = 220
            usable = list_width - 4
            prefix_px = lb_font.measure(prefix)
            suffix_reserved = max(lb_font.measure(" v "), lb_font.measure(" ^ "))
            dash_px = lb_font.measure("\u2500")
            remaining = usable - prefix_px - suffix_reserved
            if remaining > 0 and dash_px > 0:
                n_dashes = remaining // dash_px
            else:
                n_dashes = 3
        except Exception:
            n_dashes = 10

        dash_char = "\u2500"
        dashes = dash_char * max(3, n_dashes)
        return f"{prefix}{dashes} {arrow} "

    def _show_group_context_menu(self, event, group_name):
        """Right-click menu on a group header."""
        if hasattr(self, 'account_context_menu') and self.account_context_menu is not None:
            try: self.account_context_menu.destroy()
            except: pass

        menu = tk.Toplevel(self.root)
        menu.overrideredirect(True)
        menu.configure(bg=self.BG_MID, highlightthickness=1, highlightbackground="white")
        self.account_context_menu = menu

        def _btn(text, cmd):
            b = tk.Button(menu, text=text, anchor="w", relief="flat",
                          bg=self.BG_MID, fg=self.FG_TEXT,
                          activebackground=self.BG_LIGHT, activeforeground=self.FG_TEXT,
                          font=("Segoe UI", 9), bd=0, highlightthickness=0,
                          command=lambda: [self.hide_account_context_menu(), cmd()])
            b.pack(fill="x", padx=2, pady=1)

        _btn("Rename Group", lambda: self._rename_group_dialog(group_name))
        _btn("Delete Group", lambda: self._delete_group(group_name))

        menu.geometry(f"+{event.x_root}+{event.y_root}")
        menu.update_idletasks()
        if self.settings.get("enable_topmost", False):
            menu.attributes("-topmost", True)
        menu.bind("<FocusOut>", lambda e: self.hide_account_context_menu())
        self.root.bind("<Button-1>", lambda e: self.hide_account_context_menu(), add="+")

    def _create_group_dialog(self):
        """Dialog to create a new group."""
        dlg = tk.Toplevel(self.root)
        self.apply_window_icon(dlg)
        dlg.title("Create Group")
        dlg.geometry("300x120")
        dlg.configure(bg=self.BG_DARK)
        dlg.resizable(False, False)
        dlg.transient(self.root)

        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 300) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 120) // 2
        dlg.geometry(f"+{x}+{y}")

        if self.settings.get("enable_topmost", False):
            dlg.attributes("-topmost", True)

        ttk.Label(dlg, text="Group Name:", style="Dark.TLabel").pack(padx=10, pady=(10, 2), anchor="w")
        entry = ttk.Entry(dlg, style="Dark.TEntry")
        entry.pack(fill="x", padx=10)
        entry.focus_set()

        def do_create(e=None):
            name = entry.get().strip()
            if not name:
                return
            groups = self._get_groups()
            if name in groups:
                messagebox.showwarning("Exists", f"Group '{name}' already exists.", parent=dlg)
                return
            groups[name] = []
            self._save_groups(groups)
            dlg.destroy()
            self.refresh_accounts()

        entry.bind("<Return>", do_create)
        ttk.Button(dlg, text="Create", style="Dark.TButton", command=do_create).pack(pady=10)

    def _rename_group_dialog(self, old_name):
        """Dialog to rename a group."""
        dlg = tk.Toplevel(self.root)
        self.apply_window_icon(dlg)
        dlg.title("Rename Group")
        dlg.geometry("300x120")
        dlg.configure(bg=self.BG_DARK)
        dlg.resizable(False, False)
        dlg.transient(self.root)

        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 300) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 120) // 2
        dlg.geometry(f"+{x}+{y}")

        if self.settings.get("enable_topmost", False):
            dlg.attributes("-topmost", True)

        ttk.Label(dlg, text="New Name:", style="Dark.TLabel").pack(padx=10, pady=(10, 2), anchor="w")
        entry = ttk.Entry(dlg, style="Dark.TEntry")
        entry.pack(fill="x", padx=10)
        entry.insert(0, old_name)
        entry.select_range(0, tk.END)
        entry.focus_set()

        def do_rename(e=None):
            new_name = entry.get().strip()
            if not new_name or new_name == old_name:
                dlg.destroy()
                return
            groups = self._get_groups()
            if new_name in groups:
                messagebox.showwarning("Exists", f"Group '{new_name}' already exists.", parent=dlg)
                return
            members = groups.pop(old_name, [])
            groups[new_name] = members
            if old_name in self._collapsed_groups:
                self._collapsed_groups.discard(old_name)
                self._collapsed_groups.add(new_name)
            self._save_groups(groups)
            dlg.destroy()
            self.refresh_accounts()

        entry.bind("<Return>", do_rename)
        ttk.Button(dlg, text="Rename", style="Dark.TButton", command=do_rename).pack(pady=10)

    def _delete_group(self, group_name):
        """Delete a group"""
        if not messagebox.askyesno("Delete Group", f"Delete group '{group_name}'?\nAccounts will be ungrouped."):
            return
        groups = self._get_groups()
        groups.pop(group_name, None)
        self._collapsed_groups.discard(group_name)
        self._save_groups(groups)
        self.refresh_accounts()

    def _on_account_list_scroll(self, first, last):
        if hasattr(self, "account_list_scrollbar") and self.account_list_scrollbar:
            try:
                self.account_list_scrollbar.set(first, last)
            except Exception:
                pass
        self._schedule_active_instance_indicator_sync()

    def _schedule_active_instance_indicator_sync(self):
        if self._active_instance_indicator_sync_after is not None:
            try:
                self.root.after_cancel(self._active_instance_indicator_sync_after)
            except Exception:
                pass
        self._active_instance_indicator_sync_after = self.root.after(0, self._sync_active_instance_indicators)

    def _clear_active_instance_indicators(self):
        if self._active_instance_indicator_sync_after is not None:
            try:
                self.root.after_cancel(self._active_instance_indicator_sync_after)
            except Exception:
                pass
            self._active_instance_indicator_sync_after = None

        for widget in list(self._active_instance_indicators.values()):
            try:
                widget.destroy()
            except Exception:
                pass
        self._active_instance_indicators = {}

    def _sync_active_instance_indicators(self):
        self._active_instance_indicator_sync_after = None

        if not hasattr(self, "account_list") or not self.account_list.winfo_exists():
            return

        self._clear_active_instance_indicators()

        if not self.settings.get("active_instances_monitoring", False):
            return

        active_usernames = getattr(self, "_active_instance_usernames", set()) or set()
        if not active_usernames:
            return

        try:
            self.account_list.update_idletasks()
        except Exception:
            pass

        dot_color = "#3DDC84"
        dot_outline = "#2FAF67"
        normal_bg = self.account_list.cget("bg")
        selected_bg = self.account_list.cget("selectbackground")

        for index, (kind, username) in enumerate(self._list_row_map):
            if kind != "account" or username.lower() not in active_usernames:
                continue

            bbox = self.account_list.bbox(index)
            if not bbox:
                continue

            x, y, width, height = bbox
            row_bg = selected_bg if self.account_list.selection_includes(index) else normal_bg
            dot = tk.Canvas(
                self.account_list,
                width=8,
                height=8,
                bg=row_bg,
                highlightthickness=0,
                bd=0,
            )
            dot.create_oval(0, 0, 7, 7, fill=dot_color, outline=dot_outline)
            dot.place(x=4, y=y + max(0, (height - 8) // 2))
            self._active_instance_indicators[username] = dot

    def refresh_accounts(self):
        """Refresh the account list"""
        needs_rerender = self.account_list.winfo_width() <= 1

        self._clear_active_instance_indicators()

        self.account_list.delete(0, tk.END)
        self._list_row_map = []
        groups = self._get_groups()

        if self.settings.get("active_instances_monitoring", False):
            try:
                self._active_instance_usernames = set([u.lower() for u in self._get_active_instance_usernames()])
            except Exception:
                self._active_instance_usernames = set()
        else:
            self._active_instance_usernames = set()

        grouped_usernames = set()
        for members in groups.values():
            grouped_usernames.update(members)

        for username, data in self.manager.accounts.items():
            if username in grouped_usernames:
                continue
            self._insert_account_row(username, data)

        for gname, members in groups.items():
            collapsed = gname in self._collapsed_groups
            visible_members = [u for u in members if u in self.manager.accounts]
            header_text = self._build_group_header_text(gname, len(visible_members), collapsed)
            idx = self.account_list.size()
            self.account_list.insert(tk.END, header_text)
            self._list_row_map.append(("group_header", gname))
            self.account_list.itemconfig(
                idx,
                fg=self.FG_ACCENT,
                bg=self.BG_MID,
                selectbackground=self.BG_MID,
                selectforeground=self.FG_ACCENT,
            )
            if not collapsed:
                for uname in visible_members:
                    self._insert_account_row(uname, self.manager.accounts[uname])

        last_joined = self.settings.get("last_joined_user", "")
        if last_joined:
            for i, (kind, val) in enumerate(self._list_row_map):
                if kind == "account" and val == last_joined:
                    self.account_list.selection_clear(0, tk.END)
                    self.account_list.selection_set(i)
                    self.account_list.see(i)
                    break

        self._schedule_active_instance_indicator_sync()

        if needs_rerender:
            self.root.after(50, self.refresh_accounts)

    def _insert_account_row(self, username, data):
        """Insert a single account row into the Listbox and _list_row_map."""
        note = data.get('note', '') if isinstance(data, dict) else ''
        cookie_valid = self.cookie_status.get(username)
        
        is_active = (self.settings.get("active_instances_monitoring", False) and
                    getattr(self, '_active_instance_usernames', set()) and 
                    username.lower() in self._active_instance_usernames)
        
        aging_indicator = ""
        if isinstance(data, dict) and cookie_valid is not False:
            last_use_str = data.get('last_use')
            if last_use_str:
                try:
                    last_use_time = time.strptime(last_use_str, '%Y-%m-%d %H:%M:%S')
                    idle_days = (time.time() - time.mktime(last_use_time)) / 86400.0
                    if idle_days >= 20:
                        if idle_days < 25:
                            aging_indicator = "🟡 "
                        elif idle_days < 30:
                            aging_indicator = "🟠 "
                        else:
                            aging_indicator = "🔴 "
                except Exception:
                    pass

        if cookie_valid is False:
            base_text = f"\u26a0 {username}"
        else:
            base_text = f"{aging_indicator}{username}"
        if note:
            base_text += f" \u2022 {note}"
        
        if is_active:
            display_text = f"    {base_text}"
        else:
            display_text = base_text
        
        idx = self.account_list.size()
        self.account_list.insert(tk.END, display_text)
        self._list_row_map.append(("account", username))
        if cookie_valid is False:
            self.account_list.itemconfig(idx, fg="#FFB347")

    def on_account_list_hover(self, event):
        """Show tooltip when hovering over an expired account row"""
        index = self.account_list.nearest(event.y)
        
        if index < 0 or index >= self.account_list.size():
            self.hide_account_tooltip()
            return
        
        if index == self.account_tooltip_last_index:
            return
        
        self.hide_account_tooltip()
        self.account_tooltip_last_index = index
        
        display_text = self.account_list.get(index)
        if not display_text.startswith('\u26a0 '):
            return
        
        username = self.extract_username_from_display(display_text)
        
        def create_tooltip():
            if self.account_tooltip:
                return
            
            x_pos = event.x_root + 15
            y_pos = event.y_root + 15
            
            self.account_tooltip = tk.Toplevel(self.root)
            self.account_tooltip.wm_overrideredirect(True)
            self.account_tooltip.wm_geometry(f"+{x_pos}+{y_pos}")
            
            label = tk.Label(
                self.account_tooltip,
                text=f"Cookie expired for '{username}'.\nPlease remove this account and add it again.",
                bg=self.BG_DARK,
                fg=self.FG_TEXT,
                font=(self.FONT_FAMILY, 9),
                padx=8,
                pady=4,
                relief="solid",
                borderwidth=1
            )
            label.pack()
            
            if self.settings.get("enable_topmost", False):
                self.account_tooltip.attributes("-topmost", True)
        
        self.account_tooltip_timer = self.root.after(500, create_tooltip)
    
    def on_account_list_leave(self, event):
        """Hide tooltip when leaving the account list"""
        self.hide_account_tooltip()
    
    def hide_account_tooltip(self):
        """Hide the account list tooltip"""
        if self.account_tooltip_timer:
            self.root.after_cancel(self.account_tooltip_timer)
            self.account_tooltip_timer = None
        
        if self.account_tooltip:
            self.account_tooltip.destroy()
            self.account_tooltip = None
        
        self.account_tooltip_last_index = None
    
    def extract_username_from_display(self, display_text):
        """Extract username from display text (handles indicators like ⚠, ●, 🟡, 🟠, and 🔴)"""
        username_part = display_text.split(' • ')[0]
        
        username_part = username_part.strip()
        if username_part.startswith('● '):
            username_part = username_part[2:]
        if username_part.startswith('⚠ '):
            username_part = username_part[2:]
        for emoji in ['🟡', '🟠', '🔴']:
            if username_part.startswith(emoji + ' '):
                username_part = username_part[len(emoji)+1:]
            elif username_part.startswith(emoji):
                username_part = username_part[len(emoji):]
        
        return username_part.strip()
    
    def _send_webhook(self, url, content):
        def _post():
            try:
                requests.post(url, json={"content": content}, timeout=5)
            except Exception as e:
                print(f"[ERROR] Failed to send webhook: {e}")
        threading.Thread(target=_post, daemon=True).start()

    def _send_webhook_embed(self, url, title, description, color, ping_user_id=None):
        def _post():
            try:
                payload = {
                    "content": f"<@{ping_user_id}>" if ping_user_id else "",
                    "embeds": [{
                        "title": title,
                        "description": description,
                        "color": color,
                        "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
                    }],
                    "attachments": []
                }
                requests.post(url, json=payload, timeout=5)
            except Exception as e:
                print(f"[ERROR] Failed to send webhook embed: {e}")
        threading.Thread(target=_post, daemon=True).start()

    def _maybe_send_webhook_embed(self, title, description, color, ping_user_id=None):
        try:
            webhook_cfg = self.settings.get("discord_webhook", {})
            url = str(webhook_cfg.get("url", "") or "").strip()
            if webhook_cfg.get("enabled") and url:
                self._send_webhook_embed(url, title, description, color, ping_user_id=ping_user_id)
        except Exception:
            pass

    def _get_webhook_cfg(self):
        return self.settings.get("discord_webhook", {})

    def _webhook_enabled(self):
        cfg = self._get_webhook_cfg()
        return bool(cfg.get("enabled") and str(cfg.get("url", "") or "").strip())

    def _webhook_screenshot_enabled(self):
        cfg = self._get_webhook_cfg()
        return bool(cfg.get("screenshot_enabled"))

    def _webhook_screenshot_interval_minutes(self):
        cfg = self._get_webhook_cfg()
        try:
            return max(1, int(cfg.get("screenshot_interval_minutes", 60)))
        except Exception:
            return 60

    def _maybe_log_message(self, message: str):
        try:
            if not self._webhook_enabled():
                return
            url = str(self._get_webhook_cfg().get("url", "") or "").strip()
            if not url:
                return
            self._send_webhook_embed(url, "Log", f"```{message}```", 0x5865F2)
        except Exception:
            pass

    def _capture_screenshot_png(self):
        tmp_path = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            tmp_path = tmp.name
            tmp.close()

            ps = (
                "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
                "$s=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                "$b=New-Object System.Drawing.Bitmap($s.Width,$s.Height); "
                "$g=[System.Drawing.Graphics]::FromImage($b); "
                "$g.CopyFromScreen($s.Location,[System.Drawing.Point]::Empty,$s.Size); "
                f"$b.Save('{tmp_path}',[System.Drawing.Imaging.ImageFormat]::Png); "
                "$g.Dispose();$b.Dispose()"
            )
            result = subprocess.run(
                ["powershell", "-NonInteractive", "-Command", ps],
                capture_output=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode("utf-8", errors="ignore") if isinstance(result.stderr, bytes) else result.stderr)
            with open(tmp_path, 'rb') as f:
                return f.read()
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def _send_webhook_screenshot(self, url, caption=""):
        try:
            image_bytes = self._capture_screenshot_png()
            if not image_bytes:
                return

            def _post():
                try:
                    with BytesIO(image_bytes) as image_stream:
                        image_stream.seek(0)
                        requests.post(
                            url,
                            data={"content": caption},
                            files={"file": ("screenshot.png", image_stream, "image/png")},
                            timeout=10,
                        )
                except Exception as e:
                    print(f"[ERROR] Webhook screenshot send failed: {e}")

            threading.Thread(target=_post, daemon=True).start()
        except Exception as e:
            print(f"[ERROR] Screenshot send failed: {e}")

    def _get_roblox_hwnds_from_pids(self, pids):
        hwnds = []
        def _cb(hwnd, _):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    _, wpid = win32process.GetWindowThreadProcessId(hwnd)
                    if wpid in pids:
                        title = win32gui.GetWindowText(hwnd)
                        if title:
                            hwnds.append(hwnd)
            except Exception:
                pass
            return True
        win32gui.EnumWindows(_cb, None)
        return hwnds

    def _get_active_instance_usernames(self):
        """Return a list of usernames that correspond to currently running Roblox instances.

        Uses existing PID -> user id helpers and RobloxAPI username lookup. Results are
        de-duplicated and returned as a list of lowercase usernames for comparison.
        """
        res = []
        try:
            pids = sorted(self._get_roblox_pids())
            used = set()
            for pid in pids:
                try:
                    user_id, _ = self._get_user_id_from_pid(pid, used)
                    if user_id:
                        uid = int(user_id)
                        uname = self.instances_cache.get("user_id_to_username", {}).get(uid)
                        if not uname:
                            try:
                                uname = RobloxAPI.get_username_from_user_id(uid) or None
                            except Exception:
                                uname = None
                            if uname:
                                self.instances_cache.setdefault("user_id_to_username", {})[uid] = uname
                        if uname:
                            res.append(str(uname))
                except Exception:
                    continue
        except Exception:
            return []
        seen = set()
        out = []
        for u in res:
            key = u.lower()
            if key not in seen:
                seen.add(key)
                out.append(u)
        return out

    def _tile_roblox_windows(self):
        pids = self._get_roblox_pids()
        if not pids:
            return
        hwnds = self._get_roblox_hwnds_from_pids(pids)
        n = len(hwnds)
        if n == 0:
            return
        try:
            screen_w = ctypes.windll.user32.GetSystemMetrics(0)
            screen_h = ctypes.windll.user32.GetSystemMetrics(1)
            cols = math.ceil(math.sqrt(n))
            rows = math.ceil(n / cols)
            win_w = screen_w // cols
            win_h = screen_h // rows
            for i, hwnd in enumerate(hwnds):
                col = i % cols
                row = i // cols
                x = col * win_w
                y = row * win_h
                try:
                    win32gui.ShowWindow(hwnd, 9)
                    win32gui.MoveWindow(hwnd, x, y, win_w, win_h, True)
                except Exception as e:
                    print(f"[ERROR] Could not move window {hwnd}: {e}")
            print(f"[INFO] Tiled {n} Roblox window(s) in a {cols}×{rows} grid.")
        except Exception as e:
            print(f"[ERROR] Error tiling windows: {e}")

    def _tile_roblox_windows_after_launch(self):
        prev_count = len(self._get_roblox_pids())
        deadline = time.time() + 45
        while time.time() < deadline:
            time.sleep(3)
            curr_count = len(self._get_roblox_pids())
            if curr_count > prev_count:
                time.sleep(6)
                break
        self._tile_roblox_windows()

    def _save_cookie_status(self, username, is_valid):
        """Update cookie status in memory and persist to accounts file"""
        self.cookie_status[username] = is_valid
        if username in self.manager.accounts and isinstance(self.manager.accounts[username], dict):
            self.manager.accounts[username]['cookie_valid'] = is_valid

    def _silent_check_cookies(self):
        """Trigger a background silent cookie check. Safe to call from any thread."""
        if getattr(self, '_cookie_check_running', False):
            return
        threading.Thread(target=self._silent_check_cookies_worker, daemon=True).start()

    def _silent_check_cookies_worker(self):
        """Check all accounts not already known invalid."""
        if getattr(self, '_cookie_check_running', False):
            return
        self._cookie_check_running = True
        try:
            accounts = [u for u in list(self.manager.accounts)
                        if self.cookie_status.get(u) is not False]
            if not accounts:
                return
            changed = False
            for username in accounts:
                try:
                    is_valid = self.manager.validate_account(username)
                    self._save_cookie_status(username, is_valid)
                    changed = True
                except Exception as e:
                    print(f"[ERROR] Cookie check failed for {username}: {e}")
            if changed:
                self.manager.save_accounts()
                self.root.after(0, self.refresh_accounts)
        finally:
            self._cookie_check_running = False

    def auto_cookie_refresh_heartbeat(self):
        """Heartbeat to periodically refresh cookies for idle accounts to prevent expiration"""
        def run_refresh():
            try:
                refreshed_any = False
                for username, account_data in list(self.manager.accounts.items()):
                    if not isinstance(account_data, dict):
                        continue
                        
                    no_refresh = account_data.get("no_cookie_refresh", "false") == "true"
                    if no_refresh:
                        continue
                    
                    last_use_str = account_data.get("last_use")
                    last_refresh_str = account_data.get("last_attempted_refresh")
                    
                    last_use_time = None
                    if last_use_str:
                        try:
                            last_use_time = time.strptime(last_use_str, '%Y-%m-%d %H:%M:%S')
                        except:
                            pass
                    
                    last_refresh_time = None
                    if last_refresh_str:
                        try:
                            last_refresh_time = time.strptime(last_refresh_str, '%Y-%m-%d %H:%M:%S')
                        except:
                            pass
                    
                    now = time.time()
                    last_use_epoch = time.mktime(last_use_time) if last_use_time else now
                    last_refresh_epoch = time.mktime(last_refresh_time) if last_refresh_time else 0.0
                    
                    idle_days = (now - last_use_epoch) / 86400.0
                    days_since_refresh = (now - last_refresh_epoch) / 86400.0
                    
                    if idle_days > 20 and days_since_refresh >= 7:
                        print(f"[Heartbeat] Account '{username}' is idle ({idle_days:.1f} days) and due for cookie rotation...")
                        account_data["last_attempted_refresh"] = time.strftime('%Y-%m-%d %H:%M:%S')
                        self.manager.save_accounts()
                        
                        success, new_cookie = self.manager.rotate_cookie_session(username)
                        if success:
                            self._save_cookie_status(username, True)
                            print(f"[Heartbeat] Successfully rotated and refreshed session cookie for: {username}")
                            refreshed_any = True
                        else:
                            print(f"[Heartbeat] Failed to rotate session cookie for: {username}")
                        
                        time.sleep(5)
                
                if refreshed_any:
                    self.root.after(0, self.refresh_accounts)
            except Exception as e:
                print(f"[Heartbeat Error] Error running auto cookie refresh: {e}")
            finally:
                self.root.after(300000, self.auto_cookie_refresh_heartbeat)

        threading.Thread(target=run_refresh, daemon=True).start()
    
    def on_drag_start(self, event):
        """Initiate drag - store position and wait for hold"""
        widget = event.widget
        index = widget.nearest(event.y)
        
        if self.drag_data["hold_timer"]:
            self.root.after_cancel(self.drag_data["hold_timer"])
        
        if index >= 0:
            if index < len(self._list_row_map) and self._list_row_map[index][0] == "group_header":
                widget.selection_clear(0, tk.END)
                try:
                    lb_font = tkfont.Font(font=widget.cget("font"))
                    arrow_zone = max(lb_font.measure(" v "), lb_font.measure(" ^ ")) + 4
                    list_width = widget.winfo_width()
                    if event.x >= list_width - arrow_zone - 4:
                        self._handle_group_header_click(index)
                    else:
                        group_name = self._list_row_map[index][1]
                        for i, (kind, val) in enumerate(self._list_row_map):
                            if kind == "account" and self._get_username_group(val) == group_name:
                                widget.selection_set(i)
                except Exception:
                    self._handle_group_header_click(index)
                return

            self.drag_data["index"] = index
            self.drag_data["item"] = widget.get(index)
            self.drag_data["start_x"] = event.x
            self.drag_data["start_y"] = event.y
            self.drag_data["dragging"] = False
            
            if not self.settings.get("enable_multi_select", False):
                widget.selection_clear(0, tk.END)
                widget.selection_set(index)
            
            self.drag_data["hold_timer"] = self.root.after(500, lambda: self.activate_drag(event))
    
    def activate_drag(self, event):
        """Activate dragging after hold timer"""
        self.drag_data["dragging"] = True
        self.drag_data["hold_timer"] = None
        
        if not self.drag_indicator:
            self.drag_indicator = tk.Toplevel(self.root)
            self.drag_indicator.overrideredirect(True)
            self.drag_indicator.attributes("-alpha", 0.7)
            self.drag_indicator.attributes("-topmost", True)
            
            label = tk.Label(
                self.drag_indicator,
                text=self.drag_data["item"],
                bg=self.BG_LIGHT,
                fg=self.FG_TEXT,
                font=("Segoe UI", 10),
                padx=10,
                pady=5,
                relief="raised",
                borderwidth=2
            )
            label.pack()
            
            x = self.root.winfo_pointerx() + 10
            y = self.root.winfo_pointery() + 10
            self.drag_indicator.geometry(f"+{x}+{y}")
    
    def on_drag_motion(self, event):
        """Handle drag motion, show indicator and highlight drop position"""
        if self.drag_data["hold_timer"] and self.drag_data["index"] is not None:
            dx = abs(event.x - self.drag_data["start_x"])
            dy = abs(event.y - self.drag_data["start_y"])
            if dx > 5 or dy > 5:
                self.root.after_cancel(self.drag_data["hold_timer"])
                self.drag_data["hold_timer"] = None
        
        if not self.drag_data["dragging"] or self.drag_data["index"] is None:
            return
        
        widget = event.widget
        
        if self.drag_indicator:
            x = event.x_root + 10
            y = event.y_root + 10
            self.drag_indicator.geometry(f"+{x}+{y}")
        
        index = widget.nearest(event.y)
        if index >= 0:
            if not self.settings.get("enable_multi_select", False):
                widget.selection_clear(0, tk.END)
            widget.selection_set(index)
    
    def on_drag_release(self, event):
        """Release drag and reorder accounts"""
        try:
            if self.drag_data["hold_timer"]:
                self.root.after_cancel(self.drag_data["hold_timer"])
                self.drag_data["hold_timer"] = None
            
            if not self.drag_data["dragging"] or self.drag_data["index"] is None:
                return
            
            widget = event.widget
            drop_index = widget.nearest(event.y)
            drag_index = self.drag_data["index"]
            
            if drop_index >= 0 and drag_index != drop_index:
                if drop_index < len(self._list_row_map) and self._list_row_map[drop_index][0] == "group_header":
                    group_name = self._list_row_map[drop_index][1]
                    if drag_index < len(self._list_row_map) and self._list_row_map[drag_index][0] == "account":
                        username = self._list_row_map[drag_index][1]
                        self._add_account_to_group(username, group_name)
                    return

                ordered_usernames = list(self.manager.accounts.keys())
                
                if drag_index < len(self._list_row_map) and self._list_row_map[drag_index][0] == "account":
                    drag_username = self._list_row_map[drag_index][1]
                else:
                    return
                
                if drag_username not in ordered_usernames:
                    return
                old_pos = ordered_usernames.index(drag_username)
                ordered_usernames.pop(old_pos)
                
                if drop_index < len(self._list_row_map) and self._list_row_map[drop_index][0] == "account":
                    drop_username = self._list_row_map[drop_index][1]
                    if drop_username in ordered_usernames:
                        new_pos = ordered_usernames.index(drop_username)
                        ordered_usernames.insert(new_pos, drag_username)
                    else:
                        ordered_usernames.append(drag_username)
                else:
                    ordered_usernames.append(drag_username)
                
                new_accounts = {}
                for uname in ordered_usernames:
                    new_accounts[uname] = self.manager.accounts[uname]
                
                self.manager.accounts = new_accounts
                self.manager.save_accounts()
                
                self.refresh_accounts()
                
                if not self.settings.get("enable_multi_select", False):
                    widget.selection_clear(0, tk.END)
                    widget.selection_set(drop_index)
        finally:
            if self.drag_indicator:
                self.drag_indicator.destroy()
                self.drag_indicator = None
            
            self.drag_data = {
                "item": None, 
                "index": None, 
                "start_x": 0, 
                "start_y": 0,
                "dragging": False,
                "hold_timer": None
            }
    
    def get_selected_username(self):
        """Get the currently selected username"""
        selection = self.account_list.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an account first.")
            return None
        
        idx = selection[0]
        if idx < len(self._list_row_map) and self._list_row_map[idx][0] == "group_header":
            group_name = self._list_row_map[idx][1]
            for kind, val in self._list_row_map:
                if kind == "account" and self._get_username_group(val) == group_name:
                    return val
            messagebox.showwarning("Empty Group", f"Group '{group_name}' has no accounts.")
            return None
        
        display_text = self.account_list.get(idx)
        username = self.extract_username_from_display(display_text)
        return username
    
    def get_selected_usernames(self):
        """Get all selected usernames (for multi-select mode)"""
        selections = self.account_list.curselection()
        if not selections:
            messagebox.showwarning("No Selection", "Please select at least one account first.")
            return []
        
        usernames = []
        seen = set()
        for index in selections:
            if index >= len(self._list_row_map):
                continue
            kind, val = self._list_row_map[index]
            if kind == "group_header":
                group_name = val
                for k2, v2 in self._list_row_map:
                    if k2 == "account" and self._get_username_group(v2) == group_name and v2 not in seen:
                        usernames.append(v2)
                        seen.add(v2)
            else:
                if val not in seen:
                    display_text = self.account_list.get(index)
                    username = self.extract_username_from_display(display_text)
                    usernames.append(username)
                    seen.add(username)
        return usernames

    def add_account(self):
        """
        Add a new account using browser automation
        """
        browser_path, browser_name = self.get_browser_path()
        
        if not browser_path:
            messagebox.showwarning(
                "Browser Required",
                "Add Account requires a browser.\n\n"
                "Please either:\n"
                "• Install Google Chrome, or\n"
                "• Download Chromium in Settings → Tools → Browser Engine"
            )
            return

        messagebox.showinfo("Add Account", f"Browser ({browser_name}) will open for account login.\nPlease log in and wait for the process to complete.")
        
        def add_account_thread():
            """
            Thread function to add account without blocking UI
            """
            try:
                success = self.manager.add_account(1, "https://www.roblox.com/login", "", browser_path)
                self.root.after(0, lambda: self._add_account_complete(success))
            except Exception as e:
                self.root.after(0, lambda: self._add_account_error(str(e)))
        
        thread = threading.Thread(target=add_account_thread, daemon=True)
        thread.start()
    
    def _add_account_complete(self, success):
        """
        Called when account addition completes (on main thread)
        """
        if success:
            self.refresh_accounts()
            messagebox.showinfo("Success", "Account added successfully!")
        else:
            messagebox.showerror("Error", "Failed to add account.\nPlease make sure you completed the login process.")
    
    def _add_account_error(self, error_msg):
        """
        Called when account addition encounters an error (on main thread)
        """
        messagebox.showerror("Error", f"Failed to add account: {error_msg}")
    
    def import_cookie(self):
        """
        Import an account using a .ROBLOSECURITY cookie
        """
        import_window = tk.Toplevel(self.root)
        self.apply_window_icon(import_window)
        import_window.title("Import Cookie")
        import_window.geometry("450x250")
        import_window.configure(bg=self.BG_DARK)
        import_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 450) // 2
        y = main_y + (main_height - 250) // 2
        import_window.geometry(f"450x250+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            import_window.attributes("-topmost", True)
        
        import_window.transient(self.root)
        import_window.grab_set()
        
        main_frame = ttk.Frame(import_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Import Account from Cookie",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 15))
        
        ttk.Label(main_frame, text="Cookie(s)", style="Dark.TLabel").pack(anchor="w", pady=(0, 5))
        
        cookie_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        cookie_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        cookie_text = tk.Text(
            cookie_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Segoe UI", 9),
            height=5,
            wrap="word"
        )
        cookie_text.pack(side="left", fill="both", expand=True)
        
        cookie_scrollbar = ttk.Scrollbar(cookie_frame, command=cookie_text.yview)
        cookie_scrollbar.pack(side="right", fill="y")
        cookie_text.config(yscrollcommand=cookie_scrollbar.set)
        
        def do_import():
            cookie_input = cookie_text.get("1.0", "end-1c").strip()
            
            if not cookie_input:
                messagebox.showwarning("Missing Information", "Please enter the cookie(s).")
                return
            
            cookies = []
            if "_|WARNING:-" in cookie_input:
                parts = cookie_input.split("_|WARNING:-")
                for part in parts:
                    if part.strip():
                        cookies.append("_|WARNING:-" + part.strip())
            else:
                cookies = [cookie_input]
            
            imported_count = 0
            failed_count = 0
            imported_accounts = []
            
            for cookie in cookies:
                try:
                    success, username = self.manager.import_cookie_account(cookie)
                    if success:
                        imported_count += 1
                        imported_accounts.append(username)
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    print(f"[ERROR] Failed to import cookie: {e}")
            
            self.refresh_accounts()
            
            if imported_count > 0:
                if imported_count == 1:
                    messagebox.showinfo("Success", f"Account '{imported_accounts[0]}' imported successfully!")
                else:
                    messagebox.showinfo("Success", f"Successfully imported {imported_count} account(s)!\n\n{', '.join(imported_accounts)}")
                import_window.destroy()
            
            if failed_count > 0:
                if imported_count == 0:
                    messagebox.showerror("Error", f"Failed to import {failed_count} cookie(s). Please check the cookies.")
                else:
                    messagebox.showwarning("Partial Success", f"Imported {imported_count} account(s), but {failed_count} failed.")
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Import",
            style="Dark.TButton",
            command=do_import
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=import_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    def javascript_import(self):
        """
        Launch multiple Chrome instances with custom Javascript execution
        """
        amount_window = tk.Toplevel(self.root)
        self.apply_window_icon(amount_window)
        amount_window.title("Javascript Import - Amount")
        amount_window.geometry("350x150")
        amount_window.configure(bg=self.BG_DARK)
        amount_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 350) // 2
        y = main_y + (main_height - 150) // 2
        amount_window.geometry(f"350x150+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            amount_window.attributes("-topmost", True)
        
        amount_window.transient(self.root)
        
        main_frame = ttk.Frame(amount_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Amount to open (max 10):",
            style="Dark.TLabel",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        amount_entry = ttk.Entry(main_frame, style="Dark.TEntry")
        amount_entry.pack(fill="x", pady=(0, 15))
        amount_entry.insert(0, "1")
        amount_entry.focus_set()
        
        def proceed_to_website():
            try:
                amount = int(amount_entry.get().strip())
                if amount < 1 or amount > 10:
                    messagebox.showwarning("Invalid Amount", "Please enter a number between 1 and 10.")
                    return
                amount_window.destroy()
                self.javascript_import_website(amount)
            except ValueError:
                messagebox.showwarning("Invalid Input", "Please enter a valid number.")
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Yes",
            style="Dark.TButton",
            command=proceed_to_website
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=amount_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
    
    def javascript_import_website(self, amount):
        """
        Get website URL for Javascript import
        """
        website_window = tk.Toplevel(self.root)
        self.apply_window_icon(website_window)
        website_window.title("Javascript Import - Website")
        website_window.geometry("450x150")
        website_window.configure(bg=self.BG_DARK)
        website_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 450) // 2
        y = main_y + (main_height - 150) // 2
        website_window.geometry(f"450x150+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            website_window.attributes("-topmost", True)
        
        website_window.transient(self.root)
        
        main_frame = ttk.Frame(website_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Website link to launch:",
            style="Dark.TLabel",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        website_entry = ttk.Entry(main_frame, style="Dark.TEntry")
        website_entry.pack(fill="x", pady=(0, 15))
        website_entry.insert(0, "https://www.roblox.com/CreateAccount")
        website_entry.focus_set()
        
        def proceed_to_javascript():
            website = website_entry.get().strip()
            if not website:
                messagebox.showwarning("Missing Information", "Please enter a website URL.")
                return
            if not website.startswith(('http://', 'https://')):
                messagebox.showwarning("Invalid URL", "Please enter a valid URL starting with http:// or https://")
                return
            website_window.destroy()
            self.javascript_import_code(amount, website)
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Yes",
            style="Dark.TButton",
            command=proceed_to_javascript
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=website_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
    
    def javascript_import_code(self, amount, website):
        """
        Get Javascript code to execute and launch Chrome instances
        """
        js_window = tk.Toplevel(self.root)
        self.apply_window_icon(js_window)
        js_window.title("Javascript Import - Code")
        js_window.geometry("500x300")
        js_window.configure(bg=self.BG_DARK)
        js_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 500) // 2
        y = main_y + (main_height - 300) // 2
        js_window.geometry(f"500x300+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            js_window.attributes("-topmost", True)
        
        js_window.transient(self.root)
        
        main_frame = ttk.Frame(js_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Javascript:",
            style="Dark.TLabel",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        js_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        js_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        js_text = tk.Text(
            js_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Consolas", 9),
            height=10,
            wrap="word"
        )
        js_text.pack(side="left", fill="both", expand=True)
        
        js_scrollbar = ttk.Scrollbar(js_frame, command=js_text.yview)
        js_scrollbar.pack(side="right", fill="y")
        js_text.config(yscrollcommand=js_scrollbar.set)
        js_text.focus_set()
        
        def execute_javascript():
            javascript = js_text.get("1.0", "end-1c").strip()
            if not javascript:
                messagebox.showwarning("Missing Information", "Please enter Javascript code.")
                return
            js_window.destroy()
            self.launch_javascript_browsers(amount, website, javascript)
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Yes",
            style="Dark.TButton",
            command=execute_javascript
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=js_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
    
    def launch_javascript_browsers(self, amount, website, javascript):
        """
        Launch account addition with Javascript execution
        """
        browser_path, browser_name = self.get_browser_path()
        
        if not browser_path:
            messagebox.showwarning(
                "Browser Required",
                "Javascript Import requires a browser.\n\n"
                "Please either:\n"
                "• Install Google Chrome, or\n"
                "• Download Chromium in Settings → Tools → Browser Engine"
            )
            return

        def launch_thread():
            try:
                success = self.manager.add_account(amount, website, javascript, browser_path)
                
                if success:
                    self.root.after(0, lambda: [
                        self.refresh_accounts(),
                        messagebox.showinfo(
                            "Success",
                            f"Account(s) added successfully with Javascript execution!"
                        )
                    ])
                else:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        "Failed to add accounts. Please check the console for details."
                    ))
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "Error",
                    f"Failed to launch browsers: {str(e)}"
                ))
        
        thread = threading.Thread(target=launch_thread, daemon=True)
        thread.start()

    def remove_account(self):
        """Remove the selected account(s)"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
            
            if len(usernames) == 1:
                confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{usernames[0]}'?")
            else:
                confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {len(usernames)} accounts?\n\n" + "\n".join(usernames))
            
            if confirm:
                for username in usernames:
                    self.manager.delete_account(username)
                self.refresh_accounts()
                messagebox.showinfo("Success", f"{len(usernames)} account(s) deleted successfully!")
        else:
            username = self.get_selected_username()
            if username:
                confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{username}'?")
                if confirm:
                    self.manager.delete_account(username)
                    self.refresh_accounts()
                    messagebox.showinfo("Success", f"Account '{username}' deleted successfully!")

    def validate_account(self):
        """Validate the selected account"""
        username = self.get_selected_username()
        if username:
            is_valid = self.manager.validate_account(username)
            if is_valid:
                messagebox.showinfo("Validation", f"Account '{username}' is valid! ✓")
            else:
                messagebox.showwarning("Validation", f"Account '{username}' is invalid or expired.")
    
    def edit_account_note(self):
        """Edit note for the selected account(s)"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
            
            if len(usernames) == 1:
                username = usernames[0]
                current_note = self.manager.get_account_note(username)
                title_text = f"Edit Note - {username}"
            else:
                username = None
                current_note = ""
                title_text = f"Edit Note - {len(usernames)} accounts"
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]
            current_note = self.manager.get_account_note(username)
            title_text = f"Edit Note - {username}"
        
        note_window = tk.Toplevel(self.root)
        self.apply_window_icon(note_window)
        note_window.title(title_text)
        note_window.geometry("450x220")
        note_window.configure(bg=self.BG_DARK)
        note_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 450) // 2
        y = main_y + (main_height - 220) // 2
        note_window.geometry(f"450x220+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            note_window.attributes("-topmost", True)
        
        note_window.transient(self.root)
        note_window.grab_set()
        
        main_frame = ttk.Frame(note_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        if len(usernames) == 1:
            label_text = f"Edit note for '{usernames[0]}'"
        else:
            label_text = f"Edit note for {len(usernames)} accounts"
        
        ttk.Label(
            main_frame,
            text=label_text,
            style="Dark.TLabel",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        ttk.Label(main_frame, text="Note:", style="Dark.TLabel").pack(anchor="w", pady=(0, 5))
        
        note_text = tk.Text(
            main_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Segoe UI", 9),
            height=3,
            wrap="word"
        )
        note_text.pack(fill="both", expand=True, pady=(0, 15))
        note_text.insert("1.0", current_note)
        note_text.focus_set()
        
        def save_note():
            new_note = note_text.get("1.0", "end-1c").strip()
            for uname in usernames:
                self.manager.set_account_note(uname, new_note)
            self.refresh_accounts()
            if len(usernames) == 1:
                messagebox.showinfo("Success", f"Note updated for '{usernames[0]}'!")
            else:
                messagebox.showinfo("Success", f"Note updated for {len(usernames)} accounts!")
            note_window.destroy()
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Save",
            style="Dark.TButton",
            command=save_note
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=note_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    def show_account_context_menu(self, event):
        """Show context menu on right-click"""
        index = self.account_list.nearest(event.y)

        if index >= 0:
            bbox = self.account_list.bbox(index)
            if bbox is None or event.y > bbox[1] + bbox[3]:
                index = -1

        if index < 0 or index >= len(self._list_row_map):
            self._show_empty_context_menu(event)
            return

        kind, val = self._list_row_map[index]

        if kind == "group_header":
            self._show_group_context_menu(event, val)
            return

        self.account_list.selection_clear(0, tk.END)
        self.account_list.selection_set(index)
        self.account_list.activate(index)
        
        username = val
        account = self.manager.accounts.get(username)
        
        if not account:
            return
        
        if not isinstance(account, dict):
            return
        
        user_id = account.get('user_id', 0)
        password = account.get('password', '')
        
        if hasattr(self, 'account_context_menu') and self.account_context_menu is not None:
            try:
                self.account_context_menu.destroy()
            except:
                pass
        
        self.account_context_menu = tk.Toplevel(self.root)
        self.account_context_menu.overrideredirect(True)
        self.account_context_menu.configure(bg=self.BG_MID, highlightthickness=1, highlightbackground="white")
        
        def copy_to_clipboard(text):
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(str(text), win32clipboard.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
            except Exception:
                self.root.clipboard_clear()
                self.root.clipboard_append(str(text))
                self.root.update()
            self.hide_account_context_menu()
        
        def hide_menu():
            self.hide_account_context_menu()
        
        username_btn = tk.Button(
            self.account_context_menu,
            text=f"Copy Username",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=lambda: copy_to_clipboard(username)
        )
        username_btn.pack(fill="x", padx=2, pady=1)
        
        if user_id:
            userid_btn = tk.Button(
                self.account_context_menu,
                text=f"Copy User ID",
                anchor="w",
                relief="flat",
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                activebackground=self.BG_LIGHT,
                activeforeground=self.FG_TEXT,
                font=("Segoe UI", 9),
                bd=0,
                highlightthickness=0,
                command=lambda: copy_to_clipboard(user_id)
            )
        else:
            userid_btn = tk.Button(
                self.account_context_menu,
                text=f"Copy User ID",
                anchor="w",
                relief="flat",
                bg=self.BG_MID,
                fg="#666666",
                font=("Segoe UI", 9),
                bd=0,
                highlightthickness=0,
                state="disabled"
            )
        userid_btn.pack(fill="x", padx=2, pady=1)
        
        if password:
            password_btn = tk.Button(
                self.account_context_menu,
                text=f"Copy Password",
                anchor="w",
                relief="flat",
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                activebackground=self.BG_LIGHT,
                activeforeground=self.FG_TEXT,
                font=("Segoe UI", 9),
                bd=0,
                highlightthickness=0,
                command=lambda: copy_to_clipboard(password)
            )
        else:
            password_btn = tk.Button(
                self.account_context_menu,
                text=f"Copy Password",
                anchor="w",
                relief="flat",
                bg=self.BG_MID,
                fg="#666666",
                font=("Segoe UI", 9),
                bd=0,
                highlightthickness=0,
                state="disabled"
            )
        password_btn.pack(fill="x", padx=2, pady=1)
        
        try:
            if self.settings.get("developer_mode", False) and self.settings.get("enable_copy_cookie", False):
                account_cookie_val = account.get('cookie') if isinstance(account, dict) else None
                if account_cookie_val:
                    cookie_btn = tk.Button(
                        self.account_context_menu,
                        text=f"Copy Cookie",
                        anchor="w",
                        relief="flat",
                        bg=self.BG_MID,
                        fg=self.FG_TEXT,
                        activebackground=self.BG_LIGHT,
                        activeforeground=self.FG_TEXT,
                        font=("Segoe UI", 9),
                        bd=0,
                        highlightthickness=0,
                        command=lambda c=account_cookie_val: copy_to_clipboard(c)
                    )
                else:
                    cookie_btn = tk.Button(
                        self.account_context_menu,
                        text=f"Copy Cookie",
                        anchor="w",
                        relief="flat",
                        bg=self.BG_MID,
                        fg="#666666",
                        font=("Segoe UI", 9),
                        bd=0,
                        highlightthickness=0,
                        state="disabled"
                    )
                cookie_btn.pack(fill="x", padx=2, pady=1)
        except Exception:
            pass

        separator = tk.Frame(self.account_context_menu, height=1, bg="#666666")
        separator.pack(fill="x", padx=2, pady=2)
        
        def check_single_cookie():
            self.hide_account_context_menu()
            print(f"[INFO] Checking cookie for {username}...")
            
            def check_thread():
                try:
                    is_valid = self.manager.validate_account(username)
                    self._save_cookie_status(username, is_valid)
                    self.manager.save_accounts()
                    self.root.after(0, lambda: self.refresh_accounts())
                    
                    if is_valid:
                        self.root.after(0, lambda: messagebox.showinfo(
                            "Cookie Valid",
                            f"Cookie for '{username}' is valid!"
                        ))
                    else:
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Cookie Expired",
                            f"⚠ Cookie for '{username}' is expired or invalid!"
                        ))
                except Exception as e:
                    print(f"[ERROR] Failed to check cookie: {e}")
                    self._save_cookie_status(username, None)
                    self.manager.save_accounts()
                    self.root.after(0, lambda: messagebox.showerror(
                        "Check Failed",
                        f"Failed to check cookie for '{username}':\\n{str(e)}"
                    ))
            
            thread = threading.Thread(target=check_thread, daemon=True)
            thread.start()
        
        check_cookie_btn = tk.Button(
            self.account_context_menu,
            text="Check Cookie",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=check_single_cookie
        )
        check_cookie_btn.pack(fill="x", padx=2, pady=1)

        def force_refresh_cookie():
            self.hide_account_context_menu()
            print(f"[INFO] Manually rotating/refreshing cookie session for {username}...")
            
            def refresh_thread():
                try:
                    success, new_cookie = self.manager.rotate_cookie_session(username)
                    if success:
                        self._save_cookie_status(username, True)
                        self.root.after(0, self.refresh_accounts)
                        self.root.after(0, lambda: messagebox.showinfo(
                            "Success",
                            f"Successfully rotated and refreshed session cookie for '{username}'!"
                        ))
                    else:
                        self.root.after(0, lambda: messagebox.showerror(
                            "Refresh Failed",
                            f"Failed to rotate cookie session for '{username}'.\n\nThe account may be expired or Roblox servers rejected the request."
                        ))
                except Exception as e:
                    print(f"[ERROR] Failed to rotate cookie: {e}")
                    self.root.after(0, lambda: messagebox.showerror(
                        "Refresh Failed",
                        f"Error during cookie session rotation for '{username}':\n{str(e)}"
                    ))
            
            threading.Thread(target=refresh_thread, daemon=True).start()

        force_refresh_btn = tk.Button(
            self.account_context_menu,
            text="Force Cookie Refresh",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=force_refresh_cookie
        )
        force_refresh_btn.pack(fill="x", padx=2, pady=1)

        no_refresh_status = account.get('no_cookie_refresh', 'false') == 'true'
        toggle_text = "Enable Auto Refresh" if no_refresh_status else "Disable Auto Refresh"
        
        def toggle_auto_refresh():
            self.hide_account_context_menu()
            new_val = 'false' if no_refresh_status else 'true'
            self.manager.accounts[username]['no_cookie_refresh'] = new_val
            self.manager.save_accounts()
            print(f"[INFO] Set auto cookie refresh to {new_val} for {username}")
            self.refresh_accounts()
            
        toggle_refresh_btn = tk.Button(
            self.account_context_menu,
            text=toggle_text,
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=toggle_auto_refresh
        )
        toggle_refresh_btn.pack(fill="x", padx=2, pady=1)
        
        def edit_proxy():
            self.hide_account_context_menu()
            from tkinter import simpledialog
            curr_proxy = self.manager.get_account_proxy(username)
            ans = simpledialog.askstring(
                "Set Account Proxy",
                f"Enter SOCKS5/HTTP proxy for '{username}'\n(Format: host:port or user:pass@host:port, or leave blank to clear):",
                initialvalue=curr_proxy
            )
            if ans is not None:
                self.manager.set_account_proxy(username, ans.strip())
                self.refresh_accounts()
                messagebox.showinfo("Success", f"Proxy updated successfully for '{username}'!")

        proxy_btn = tk.Button(
            self.account_context_menu,
            text="Set/Edit Proxy",
            anchor="w",
            relief="flat",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            command=edit_proxy
        )
        proxy_btn.pack(fill="x", padx=2, pady=1)
        
        group_sep = tk.Frame(self.account_context_menu, height=1, bg="#666666")
        group_sep.pack(fill="x", padx=2, pady=2)

        current_group = self._get_username_group(username)

        if current_group:
            remove_grp_btn = tk.Button(
                self.account_context_menu,
                text=f"Remove from \"{current_group}\"",
                anchor="w", relief="flat",
                bg=self.BG_MID, fg=self.FG_TEXT,
                activebackground=self.BG_LIGHT, activeforeground=self.FG_TEXT,
                font=("Segoe UI", 9), bd=0, highlightthickness=0,
                command=lambda: [self.hide_account_context_menu(), self._remove_account_from_group(username)]
            )
            remove_grp_btn.pack(fill="x", padx=2, pady=1)

        create_grp_btn = tk.Button(
            self.account_context_menu,
            text="Create Group",
            anchor="w", relief="flat",
            bg=self.BG_MID, fg=self.FG_TEXT,
            activebackground=self.BG_LIGHT, activeforeground=self.FG_TEXT,
            font=("Segoe UI", 9), bd=0, highlightthickness=0,
            command=lambda: [self.hide_account_context_menu(), self._create_group_dialog()]
        )
        create_grp_btn.pack(fill="x", padx=2, pady=1)

        self.account_context_menu.geometry(f"+{event.x_root}+{event.y_root}")
        self.account_context_menu.update_idletasks()
        
        if self.settings.get("enable_topmost", False):
            self.account_context_menu.attributes("-topmost", True)
        
        self.account_context_menu.bind("<FocusOut>", lambda e: self.hide_account_context_menu())
        self.root.bind("<Button-1>", lambda e: self.hide_account_context_menu(), add="+")
    
    def hide_account_context_menu(self):
        """Hide the account context menu"""
        if hasattr(self, 'account_context_menu') and self.account_context_menu is not None:
            try:
                self.account_context_menu.destroy()
            except:
                pass
            self.account_context_menu = None

    def _show_empty_context_menu(self, event):
        if hasattr(self, 'account_context_menu') and self.account_context_menu is not None:
            try: self.account_context_menu.destroy()
            except: pass

        menu = tk.Toplevel(self.root)
        menu.overrideredirect(True)
        menu.configure(bg=self.BG_MID, highlightthickness=1, highlightbackground="white")
        self.account_context_menu = menu

        btn = tk.Button(menu, text="Create Group", anchor="w", relief="flat",
                        bg=self.BG_MID, fg=self.FG_TEXT,
                        activebackground=self.BG_LIGHT, activeforeground=self.FG_TEXT,
                        font=("Segoe UI", 9), bd=0, highlightthickness=0,
                        command=lambda: [self.hide_account_context_menu(), self._create_group_dialog()])
        btn.pack(fill="x", padx=2, pady=1)

        menu.geometry(f"+{event.x_root}+{event.y_root}")
        menu.update_idletasks()
        if self.settings.get("enable_topmost", False):
            menu.attributes("-topmost", True)
        menu.bind("<FocusOut>", lambda e: self.hide_account_context_menu())
        self.root.bind("<Button-1>", lambda e: self.hide_account_context_menu(), add="+")

    def launch_home(self):
        """Launch Roblox application to home page with the selected account(s) logged in (non-blocking)"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
            if len(usernames) >= 3:
                confirm = messagebox.askyesno(
                    "Confirm Launch",
                    f"Are you sure you want to launch {len(usernames)} Roblox instances to home?\n\nThis will open multiple Roblox windows."
                )
                if not confirm:
                    return
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]

        def worker(selected_usernames):
            launcher_pref, custom_launcher_path = self._get_roblox_launcher_config()
            success_count = 0
            failed_launch = False
            for uname in selected_usernames:
                try:
                    if self.manager.launch_roblox(uname, "", "", launcher_pref, "", custom_launcher_path):
                        success_count += 1
                    else:
                        failed_launch = True
                except Exception as e:
                    print(f"[ERROR] Failed to launch Roblox home for {uname}: {e}")
            if failed_launch:
                self._silent_check_cookies()
            
            if success_count > 1 and self.settings.get("auto_tile_windows", False):
                threading.Thread(target=self._tile_roblox_windows_after_launch, daemon=True).start()

            def on_done():
                if success_count > 0:
                    self.settings["last_joined_user"] = selected_usernames[-1]
                    self.save_settings()
                    if not self.settings.get("disable_launch_popup", False):
                        if len(selected_usernames) == 1:
                            messagebox.showinfo("Success", "Roblox is launching to home! Check your desktop.")
                        else:
                            messagebox.showinfo("Success", f"Roblox is launching to home for {success_count} account(s)! Check your desktop.")
                else:
                    messagebox.showerror("Error", "Failed to launch Roblox.")
            
            self.root.after(0, on_done)

        threading.Thread(target=worker, args=(usernames,), daemon=True).start()

    def launch_game(self):
        """Launch Roblox game with the selected account(s)"""
        
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]

        game_id_input = self.place_entry.get().strip()
        private_server_input = self.private_server_entry.get().strip()

        if game_id_input:
            if not game_id_input.isdigit():
                messagebox.showerror("Invalid Input", "Place ID must be a valid number.")
                return
            game_id = game_id_input
        elif private_server_input:
            vip_pid = re.search(r'roblox\.com/games/(\d+)', private_server_input)
            game_id = vip_pid.group(1) if vip_pid else ""
        else:
            messagebox.showwarning("Missing Info", "Please enter a Place ID or paste a VIP server / share link in the Private Server field.")
            return

        private_server = private_server_input 

        if self.settings.get("confirm_before_launch", False):
            game_name = RobloxAPI.get_game_name(game_id)
            if not game_name:
                game_name = f"Place {game_id}"
            if len(usernames) == 1:
                confirm = messagebox.askyesno("Confirm Launch", f"Are you sure you want to join {game_name}?")
            else:
                confirm = messagebox.askyesno("Confirm Launch", f"Are you sure you want to join {game_name} with {len(usernames)} accounts?")
            if not confirm:
                return

        def worker(selected_usernames, pid, psid):
            launcher_pref, custom_launcher_path = self._get_roblox_launcher_config()
            success_count = 0
            failed_launch = False
            for i, uname in enumerate(selected_usernames):
                try:
                    if self.manager.launch_roblox(uname, pid, psid, launcher_pref, "", custom_launcher_path):
                        success_count += 1
                    else:
                        failed_launch = True
                except Exception as e:
                    print(f"[ERROR] Failed to launch game for {uname}: {e}")
                if i < len(selected_usernames) - 1:
                    time.sleep(2)
            if failed_launch:
                self._silent_check_cookies()

            if success_count > 1 and self.settings.get("auto_tile_windows", False):
                threading.Thread(target=self._tile_roblox_windows_after_launch, daemon=True).start()

            def on_done():
                if success_count > 0:
                    self.settings["last_joined_user"] = selected_usernames[-1]
                    self.save_settings()
                    gname = RobloxAPI.get_game_name(pid)
                    if gname:
                        self.add_game_to_list(pid, gname, psid)
                    else:
                        self.add_game_to_list(pid, f"Place {pid}", psid)
                    if not self.settings.get("disable_launch_popup", False):
                        if len(selected_usernames) == 1:
                            messagebox.showinfo("Success", "Roblox is launching! Check your desktop.")
                        else:
                            messagebox.showinfo("Success", f"Roblox is launching for {success_count} account(s)! Check your desktop.")
                else:
                    messagebox.showerror("Error", "Failed to launch Roblox.")

            self.root.after(0, on_done)

        threading.Thread(target=worker, args=(usernames, game_id, private_server), daemon=True).start()

    def open_auto_rejoin(self):
        """Open the auto-rejoin management window (like favorites window)"""
        auto_rejoin_window = tk.Toplevel(self.root)
        self.apply_window_icon(auto_rejoin_window)
        auto_rejoin_window.title("Auto-Rejoin")
        auto_rejoin_window.configure(bg=self.BG_DARK)
        auto_rejoin_window.resizable(False, False)
        
        self.root.update_idletasks()
        
        saved_pos = self.settings.get('auto_rejoin_window_position')
        if saved_pos and saved_pos.get('x') is not None and saved_pos.get('y') is not None:
            x = saved_pos['x']
            y = saved_pos['y']
        else:
            x = self.root.winfo_x() + 50
            y = self.root.winfo_y() + 50
        auto_rejoin_window.geometry(f"450x400+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            auto_rejoin_window.attributes("-topmost", True)
        
        auto_rejoin_window.transient(self.root)
        auto_rejoin_window.focus_force()
        
        main_frame = ttk.Frame(auto_rejoin_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        header_row = ttk.Frame(main_frame, style="Dark.TFrame")
        header_row.pack(fill="x", pady=(0, 10))
        ttk.Label(
            header_row,
            text="Auto-Rejoin Accounts",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(side="left")

        list_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        rejoin_list = tk.Listbox(
            list_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            highlightthickness=0,
            border=0,
            font=("Segoe UI", 9),
            selectmode=tk.EXTENDED
        )
        rejoin_list.grid(row=0, column=0, sticky="nsew")
        
        v_scrollbar = ttk.Scrollbar(list_frame, command=rejoin_list.yview, orient="vertical")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        rejoin_list.config(yscrollcommand=v_scrollbar.set)
        
        def refresh_rejoin_list():
            rejoin_list.delete(0, tk.END)
            for account, config in self.auto_rejoin_configs.items():
                is_active = account in self.auto_rejoin_threads and self.auto_rejoin_threads[account].is_alive()
                status = "[ACTIVE]" if is_active else "[INACTIVE]"
                place_id = config.get('place_id', 'Unknown')
                display = f"{account} - {status} - Place: {place_id}"
                rejoin_list.insert(tk.END, display)
        refresh_rejoin_list()

        ttk.Label(
            main_frame,
            text="Tip: Hold Ctrl/Shift to select multiple accounts",
            style="Dark.TLabel",
            font=("Segoe UI", 8)
        ).pack(anchor="w", pady=(0, 8))

        def _get_selected_rejoin_accounts():
            selected_indices = rejoin_list.curselection()
            if not selected_indices:
                return []
            accounts_list = list(self.auto_rejoin_configs.keys())
            selected_accounts = []
            for idx in selected_indices:
                if 0 <= idx < len(accounts_list):
                    selected_accounts.append(accounts_list[idx])
            return selected_accounts
        
        btn_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        btn_frame.pack(fill="x")
        
        def add_auto_rejoin():
            """Open dialog to add a new auto-rejoin account"""
            add_window = tk.Toplevel(auto_rejoin_window)
            self.apply_window_icon(add_window)
            add_window.title("Add Auto-Rejoin")
            add_window.configure(bg=self.BG_DARK)
            add_window.resizable(False, False)
            
            auto_rejoin_window.update_idletasks()
            x = auto_rejoin_window.winfo_x() + 50
            y = auto_rejoin_window.winfo_y() + 50
            add_window.geometry(f"400x470+{x}+{y}")
            
            if self.settings.get("enable_topmost", False):
                add_window.attributes("-topmost", True)
            
            add_window.transient(auto_rejoin_window)
            add_window.focus_force()
            
            form_frame = ttk.Frame(add_window, style="Dark.TFrame")
            form_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            checkbox_style = ttk.Style()
            checkbox_style.configure(
                "Dark.TCheckbutton",
                background=self.BG_DARK,
                foreground=self.FG_TEXT,
                font=("Segoe UI", 10)
            )
            
            ttk.Label(form_frame, text="Account(s) - Hold Ctrl to select multiple:", style="Dark.TLabel").pack(anchor="w")
            
            account_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            account_frame.pack(fill="both", expand=True, pady=(0, 10))
            
            account_listbox = tk.Listbox(
                account_frame,
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                selectbackground=self.FG_ACCENT,
                highlightthickness=0,
                border=1,
                font=("Segoe UI", 9),
                selectmode=tk.EXTENDED,
                height=6
            )
            account_listbox.pack(side="left", fill="both", expand=True)
            
            account_scrollbar = ttk.Scrollbar(account_frame, command=account_listbox.yview)
            account_scrollbar.pack(side="right", fill="y")
            account_listbox.config(yscrollcommand=account_scrollbar.set)
            
            for account in sorted(self.manager.accounts.keys()):
                account_listbox.insert(tk.END, account)
            
            ttk.Label(form_frame, text="Place ID:", style="Dark.TLabel").pack(anchor="w")
            place_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            place_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Private Server ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            private_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            private_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Job ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            job_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            job_entry.pack(fill="x", pady=(0, 10))
            
            interval_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            interval_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(interval_frame, text="Check Interval (seconds):", style="Dark.TLabel").pack(side="left")
            interval_spinbox = ttk.Spinbox(interval_frame, from_=5, to=300, increment=5, width=8)
            interval_spinbox.set(10)
            interval_spinbox.pack(side="left", padx=(10, 0))
            
            retry_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            retry_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(retry_frame, text="Max Rejoin Attempts:", style="Dark.TLabel").pack(side="left")
            retry_spinbox = ttk.Spinbox(retry_frame, from_=1, to=50, increment=1, width=8)
            retry_spinbox.set(5)
            retry_spinbox.pack(side="left", padx=(10, 0))
            
            check_presence_var = tk.BooleanVar(value=True)
            check_presence_check = ttk.Checkbutton(form_frame, text="Check if player is in target PlaceID", style="Dark.TCheckbutton", variable=check_presence_var)
            check_presence_check.pack(anchor="w", pady=(0, 10))

            check_internet_var = tk.BooleanVar(value=True)
            check_internet_check = ttk.Checkbutton(
                form_frame,
                text="Check internet connection before launching",
                style="Dark.TCheckbutton",
                variable=check_internet_var,
            )
            check_internet_check.pack(anchor="w", pady=(0, 10))
            
            def save_and_add():
                selected_indices = account_listbox.curselection()
                if not selected_indices:
                    messagebox.showwarning("Missing Info", "Please select at least one account.")
                    return
                
                selected_accounts = [account_listbox.get(i) for i in selected_indices]
                
                place_id = place_entry.get().strip()
                if not place_id:
                    messagebox.showwarning("Missing Info", "Please enter a Place ID.")
                    return
                if not place_id.isdigit():
                    messagebox.showerror("Invalid Input", "Place ID must be a valid number.")
                    return
                
                job_id = job_entry.get().strip()
                
                config = {
                    'place_id': place_id,
                    'private_server': private_entry.get().strip(),
                    'job_id': job_id,
                    'check_interval': int(interval_spinbox.get()),
                    'max_retries': int(retry_spinbox.get()),
                    'check_presence': check_presence_var.get(),
                    'check_internet_before_launch': check_internet_var.get()
                }
                
                for account in selected_accounts:
                    self.auto_rejoin_configs[account] = config.copy()
                
                self.settings['auto_rejoin_configs'] = self.auto_rejoin_configs
                self.save_settings()
                
                add_window.destroy()
                refresh_rejoin_list()
                
                if len(selected_accounts) == 1:
                    messagebox.showinfo("Success", f"Added auto-rejoin for {selected_accounts[0]}!")
                else:
                    messagebox.showinfo("Success", f"Added auto-rejoin for {len(selected_accounts)} accounts:\n{', '.join(selected_accounts)}")
                
                auto_rejoin_window.lift()
                auto_rejoin_window.focus_force()
            
            button_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            button_frame.pack(fill="x", pady=(10, 0))
            
            ttk.Button(button_frame, text="Save", style="Dark.TButton", command=save_and_add).pack(side="left", fill="x", expand=True, padx=(0, 5))
            ttk.Button(button_frame, text="Cancel", style="Dark.TButton", command=add_window.destroy).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        def edit_auto_rejoin():
            """Edit selected auto-rejoin config"""
            selected_accounts = _get_selected_rejoin_accounts()
            if not selected_accounts:
                messagebox.showwarning("No Selection", "Please select an account to edit.")
                return
            if len(selected_accounts) > 1:
                messagebox.showwarning("Multiple Selected", "Please select only one account to edit.")
                return
            
            account = selected_accounts[0]
            config = self.auto_rejoin_configs[account]
            
            edit_window = tk.Toplevel(auto_rejoin_window)
            self.apply_window_icon(edit_window)
            edit_window.title("Edit Auto-Rejoin")
            edit_window.configure(bg=self.BG_DARK)
            edit_window.resizable(False, False)
            
            auto_rejoin_window.update_idletasks()
            x = auto_rejoin_window.winfo_x() + 50
            y = auto_rejoin_window.winfo_y() + 50
            edit_window.geometry(f"400x430+{x}+{y}")
            
            if self.settings.get("enable_topmost", False):
                edit_window.attributes("-topmost", True)
            
            edit_window.transient(auto_rejoin_window)
            edit_window.focus_force()
            
            form_frame = ttk.Frame(edit_window, style="Dark.TFrame")
            form_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            checkbox_style = ttk.Style()
            checkbox_style.configure(
                "Dark.TCheckbutton",
                background=self.BG_DARK,
                foreground=self.FG_TEXT,
                font=("Segoe UI", 10)
            )
            
            ttk.Label(form_frame, text=f"Account: {account}", style="Dark.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 10))
            
            ttk.Label(form_frame, text="Place ID:", style="Dark.TLabel").pack(anchor="w")
            place_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            place_entry.insert(0, config.get('place_id', ''))
            place_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Private Server ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            private_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            private_entry.insert(0, config.get('private_server', ''))
            private_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Job ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            job_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            job_entry.insert(0, config.get('job_id', ''))
            job_entry.pack(fill="x", pady=(0, 10))
            
            interval_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            interval_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(interval_frame, text="Check Interval (seconds):", style="Dark.TLabel").pack(side="left")
            interval_spinbox = ttk.Spinbox(interval_frame, from_=5, to=300, increment=5, width=8)
            interval_spinbox.set(config.get('check_interval', 10))
            interval_spinbox.pack(side="left", padx=(10, 0))
            
            retry_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            retry_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(retry_frame, text="Max Rejoin Attempts:", style="Dark.TLabel").pack(side="left")
            retry_spinbox = ttk.Spinbox(retry_frame, from_=1, to=50, increment=1, width=8)
            retry_spinbox.set(config.get('max_retries', 5))
            retry_spinbox.pack(side="left", padx=(10, 0))
            
            check_presence_var = tk.BooleanVar(value=config.get('check_presence', True))
            check_presence_check = ttk.Checkbutton(form_frame, text="Check if player is in target PlaceID", style="Dark.TCheckbutton", variable=check_presence_var)
            check_presence_check.pack(anchor="w", pady=(0, 10))

            check_internet_var = tk.BooleanVar(value=config.get('check_internet_before_launch', True))
            check_internet_check = ttk.Checkbutton(
                form_frame,
                text="Check internet connection before launching",
                style="Dark.TCheckbutton",
                variable=check_internet_var,
            )
            check_internet_check.pack(anchor="w", pady=(0, 10))
            
            def save_edit():
                place_id = place_entry.get().strip()
                if not place_id:
                    messagebox.showwarning("Missing Info", "Please enter a Place ID.")
                    return
                if not place_id.isdigit():
                    messagebox.showerror("Invalid Input", "Place ID must be a valid number.")
                    return
                
                job_id = job_entry.get().strip()
                
                self.auto_rejoin_configs[account] = {
                    'place_id': place_id,
                    'private_server': private_entry.get().strip(),
                    'job_id': job_id,
                    'check_interval': int(interval_spinbox.get()),
                    'max_retries': int(retry_spinbox.get()),
                    'check_presence': check_presence_var.get(),
                    'check_internet_before_launch': check_internet_var.get()
                }
                
                self.settings['auto_rejoin_configs'] = self.auto_rejoin_configs
                self.save_settings()
                
                edit_window.destroy()
                refresh_rejoin_list()
                auto_rejoin_window.lift()
                auto_rejoin_window.focus_force()
            
            button_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            button_frame.pack(fill="x", pady=(10, 0))
            
            ttk.Button(button_frame, text="Save", style="Dark.TButton", command=save_edit).pack(side="left", fill="x", expand=True, padx=(0, 5))
            ttk.Button(button_frame, text="Cancel", style="Dark.TButton", command=edit_window.destroy).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        def remove_auto_rejoin():
            """Remove selected auto-rejoin config(s)"""
            selected_accounts = _get_selected_rejoin_accounts()
            if not selected_accounts:
                messagebox.showwarning("No Selection", "Please select account(s) to remove.")
                return

            if len(selected_accounts) == 1:
                confirm_msg = f"Remove auto-rejoin for {selected_accounts[0]}?"
            else:
                confirm_msg = f"Remove auto-rejoin for {len(selected_accounts)} selected accounts?"

            if messagebox.askyesno("Confirm", confirm_msg):
                for account in selected_accounts:
                    self.stop_auto_rejoin_for_account(account)
                    if account in self.auto_rejoin_configs:
                        del self.auto_rejoin_configs[account]
                self.settings['auto_rejoin_configs'] = self.auto_rejoin_configs
                self.save_settings()
                refresh_rejoin_list()
        
        def start_selected():
            """Start auto-rejoin for selected account(s)"""
            selected_accounts = _get_selected_rejoin_accounts()
            if not selected_accounts:
                messagebox.showwarning("No Selection", "Please select account(s) to start.")
                return

            self._match_pids_to_accounts(selected_accounts)

            for account in selected_accounts:
                self.start_auto_rejoin_for_account(account)

            auto_rejoin_window.after(500, refresh_rejoin_list)
            if len(selected_accounts) == 1:
                account = selected_accounts[0]
                self._maybe_send_webhook_embed(
                    "Auto Rejoin — Started",
                    f"Monitoring **{account}** on place `{self.auto_rejoin_configs[account].get('place_id', '?')}`.",
                    0x2ECC71
                )
                messagebox.showinfo("Started", f"Auto-rejoin started for {account}!")
            else:
                lines = "\n".join(
                    f"- **{acc}** on place `{self.auto_rejoin_configs[acc].get('place_id', '?')}`"
                    for acc in selected_accounts
                )
                self._maybe_send_webhook_embed(
                    "Auto Rejoin — Started",
                    f"Monitoring {len(selected_accounts)} account(s):\n{lines}",
                    0x2ECC71
                )
                messagebox.showinfo("Started", f"Auto-rejoin started for {len(selected_accounts)} account(s)!")
        
        def stop_selected():
            """Stop auto-rejoin for selected account(s)"""
            selected_accounts = _get_selected_rejoin_accounts()
            if not selected_accounts:
                messagebox.showwarning("No Selection", "Please select account(s) to stop.")
                return

            for account in selected_accounts:
                self.stop_auto_rejoin_for_account(account)
            refresh_rejoin_list()
            if len(selected_accounts) == 1:
                messagebox.showinfo("Stopped", f"Auto-rejoin stopped for {selected_accounts[0]}!")
            else:
                messagebox.showinfo("Stopped", f"Auto-rejoin stopped for {len(selected_accounts)} account(s)!")
        
        def start_all():
            """Start auto-rejoin for all accounts"""
            accounts = list(self.auto_rejoin_configs.keys())

            self._match_pids_to_accounts(accounts)

            if accounts:
                lines = "\n".join(
                    f"- **{acc}** on place `{self.auto_rejoin_configs[acc].get('place_id', '?')}`"
                    for acc in accounts
                )
                self._maybe_send_webhook_embed(
                    "Auto Rejoin — Started",
                    f"Monitoring {len(accounts)} account(s):\n{lines}",
                    0x2ECC71
                )

            for account in accounts:
                self.start_auto_rejoin_for_account(account)

            auto_rejoin_window.after(500, refresh_rejoin_list)
            messagebox.showinfo("Started", f"Auto-rejoin started for all {len(accounts)} account(s)!")
        
        def stop_all():
            """Stop auto-rejoin for all accounts"""
            for account in list(self.auto_rejoin_threads.keys()):
                self.stop_auto_rejoin_for_account(account)
            refresh_rejoin_list()
            messagebox.showinfo("Stopped", "Auto-rejoin stopped for all accounts!")
        
        def on_auto_rejoin_close():
            """Save window position before closing"""
            self.settings['auto_rejoin_window_position'] = {
                'x': auto_rejoin_window.winfo_x(),
                'y': auto_rejoin_window.winfo_y()
            }
            self.save_settings()
            auto_rejoin_window.destroy()
        
        auto_rejoin_window.protocol("WM_DELETE_WINDOW", on_auto_rejoin_close)
        
        row1_frame = ttk.Frame(btn_frame, style="Dark.TFrame")
        row1_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Button(row1_frame, text="Add", style="Dark.TButton", command=add_auto_rejoin).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(row1_frame, text="Edit", style="Dark.TButton", command=edit_auto_rejoin).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row1_frame, text="Remove", style="Dark.TButton", command=remove_auto_rejoin).pack(side="left", fill="x", expand=True, padx=(2, 0))
        
        row2_frame = ttk.Frame(btn_frame, style="Dark.TFrame")
        row2_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Button(row2_frame, text="Start Selected", style="Dark.TButton", command=start_selected).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(row2_frame, text="Stop Selected", style="Dark.TButton", command=stop_selected).pack(side="left", fill="x", expand=True, padx=(2, 0))
        
        row3_frame = ttk.Frame(btn_frame, style="Dark.TFrame")
        row3_frame.pack(fill="x")
        
        ttk.Button(row3_frame, text="Start All", style="Dark.TButton", command=start_all).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(row3_frame, text="Stop All", style="Dark.TButton", command=stop_all).pack(side="left", fill="x", expand=True, padx=(2, 0))

    def join_user(self):
        """Join a user's current game"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]
        
        join_window = tk.Toplevel(self.root)
        self.apply_window_icon(join_window)
        join_window.title("Join User")
        join_window.geometry("450x220")
        join_window.configure(bg=self.BG_DARK)
        join_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 450) // 2
        y = main_y + (main_height - 220) // 2
        join_window.geometry(f"450x220+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            join_window.attributes("-topmost", True)
        
        join_window.transient(self.root)
        join_window.grab_set()
        
        main_frame = ttk.Frame(join_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Join User's Game",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        ttk.Label(
            main_frame,
            text="⚠️ User must have their joins enabled!",
            style="Dark.TLabel",
            font=("Segoe UI", 9, "italic"),
            foreground="#FFA500"
        ).pack(anchor="w", pady=(0, 10))
        
        ttk.Label(main_frame, text="Username to join:", style="Dark.TLabel").pack(anchor="w", pady=(0, 5))
        
        username_entry = ttk.Entry(main_frame, style="Dark.TEntry")
        username_entry.pack(fill="x", pady=(0, 15))
        username_entry.focus_set()
        
        def do_join():
            target_username = username_entry.get().strip()
            
            if not target_username:
                messagebox.showwarning("Missing Information", "Please enter a username.")
                return
            
            join_window.destroy()
            
            def worker(selected_usernames, target_user):
                
                user_id = RobloxAPI.get_user_id_from_username(target_user)
                if not user_id:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        f"User '{target_user}' not found."
                    ))
                    return
                
                account_cookie = self.manager.accounts.get(selected_usernames[0])
                if isinstance(account_cookie, dict):
                    account_cookie = account_cookie.get('cookie')
                
                if not account_cookie:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        "Failed to get account cookie."
                    ))
                    return
                
                presence = RobloxAPI.get_player_presence(user_id, account_cookie)
                
                if not presence:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        f"Failed to get presence for '{target_user}'. Please try again."
                    ))
                    return
                
                if not presence.get('in_game'):
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Not In Game",
                        f"'{target_user}' is not currently in a game.\n\nStatus: {presence.get('last_location', 'Unknown')}"
                    ))
                    return
                
                place_id = str(presence.get('place_id', ''))
                game_id = str(presence.get('game_id', ''))
                
                if not place_id:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        f"Could not get game info for '{target_user}'."
                    ))
                    return
                
                launcher_pref, custom_launcher_path = self._get_roblox_launcher_config()
                success_count = 0
                
                for uname in selected_usernames:
                    try:
                        if self.manager.launch_roblox(uname, place_id, "", launcher_pref, game_id, custom_launcher_path):
                            success_count += 1
                    except Exception as e:
                        print(f"[ERROR] Failed to launch game for {uname}: {e}")
                
                def on_done():
                    if success_count > 0:
                        game_name = RobloxAPI.get_game_name(place_id)
                        if game_name:
                            self.add_game_to_list(place_id, game_name, "")
                        else:
                            self.add_game_to_list(place_id, f"Place {place_id}", "")
                        
                        if len(selected_usernames) == 1:
                            messagebox.showinfo(
                                "Success",
                                f"Joining '{target_user}' in their game! Check your desktop."
                            )
                        else:
                            messagebox.showinfo(
                                "Success",
                                f"Joining '{target_user}' with {success_count} account(s)! Check your desktop."
                            )
                    else:
                        messagebox.showerror("Error", "Failed to launch Roblox.")
                
                self.root.after(0, on_done)
            
            threading.Thread(target=worker, args=(usernames, target_username), daemon=True).start()
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Join",
            style="Dark.TButton",
            command=do_join
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=join_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    def join_by_job_id(self):
        """Join a game by Job ID"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]
        
        job_id_window = tk.Toplevel(self.root)
        self.apply_window_icon(job_id_window)
        job_id_window.title("Join by Job-ID")
        job_id_window.geometry("450x220")
        job_id_window.configure(bg=self.BG_DARK)
        job_id_window.resizable(False, False)
        
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - 450) // 2
        y = main_y + (main_height - 220) // 2
        job_id_window.geometry(f"450x220+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            job_id_window.attributes("-topmost", True)
        
        job_id_window.transient(self.root)
        job_id_window.grab_set()
        
        main_frame = ttk.Frame(job_id_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(
            main_frame,
            text="Join by Job-ID",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        ttk.Label(main_frame, text="Job-ID:", style="Dark.TLabel").pack(anchor="w", pady=(0, 5))
        
        job_id_entry = ttk.Entry(main_frame, style="Dark.TEntry")
        job_id_entry.pack(fill="x", pady=(0, 15))
        job_id_entry.focus_set()
        
        def do_join_job():
            place_id = self.place_entry.get().strip()
            if not place_id:
                messagebox.showwarning("Missing Information", "Please enter a Place ID first.")
                return
            
            job_id = job_id_entry.get().strip()
            if not job_id:
                messagebox.showwarning("Missing Information", "Please enter a Job-ID.")
                return
            
            job_id_window.destroy()
            
            def worker(selected_usernames, pid, jid):
                launcher_pref, custom_launcher_path = self._get_roblox_launcher_config()
                success_count = 0
                
                for uname in selected_usernames:
                    try:
                        if self.manager.launch_roblox(uname, pid, "", launcher_pref, jid, custom_launcher_path):
                            success_count += 1
                    except Exception as e:
                        print(f"[ERROR] Failed to launch game for {uname}: {e}")
                
                def on_done():
                    if success_count > 0:
                        game_name = RobloxAPI.get_game_name(pid)
                        if game_name:
                            self.add_game_to_list(pid, game_name, "")
                        else:
                            self.add_game_to_list(pid, f"Place {pid}", "")
                        
                        messagebox.showinfo(
                            "Success",
                            f"Joining Job-ID {jid} with {success_count} account(s)! Check your desktop."
                        )
                    else:
                        messagebox.showerror("Error", "Failed to launch Roblox.")
                
                self.root.after(0, on_done)
            
            threading.Thread(target=worker, args=(usernames, place_id, job_id), daemon=True).start()
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Join",
            style="Dark.TButton",
            command=do_join_job
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Cancel",
            style="Dark.TButton",
            command=job_id_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    def join_small_server(self):
        """Join the smallest available server for a given place ID"""
        if self.settings.get("enable_multi_select", False):
            usernames = self.get_selected_usernames()
            if not usernames:
                return
        else:
            username = self.get_selected_username()
            if not username:
                return
            usernames = [username]
        
        place_id = self.place_entry.get().strip()
        if not place_id:
            messagebox.showwarning("Missing Information", "Please enter a Place ID first.")
            return
        
        try:
            int(place_id)
        except ValueError:
            messagebox.showerror("Invalid Input", "Place ID must be a valid number.")
            return
        
        def worker(selected_usernames, pid):
            print(f"[INFO] Searching for smallest server in place {pid}...")
            game_id = RobloxAPI.get_smallest_server(pid)
            
            if not game_id:
                self.root.after(0, lambda: messagebox.showerror(
                    "Error",
                    f"Could not find any available servers for place {pid}.\n\nPlease try again later or check the Place ID."
                ))
                return
            
            print(f"[SUCCESS] Found smallest server: {game_id}")
            
            launcher_pref, custom_launcher_path = self._get_roblox_launcher_config()
            success_count = 0
            
            for uname in selected_usernames:
                try:
                    if self.manager.launch_roblox(uname, pid, "", launcher_pref, game_id, custom_launcher_path):
                        success_count += 1
                except Exception as e:
                    print(f"[ERROR] Failed to launch game for {uname}: {e}")
            
            def on_done():
                if success_count > 0:
                    game_name = RobloxAPI.get_game_name(pid)
                    if game_name:
                        self.add_game_to_list(pid, game_name, "")
                    else:
                        self.add_game_to_list(pid, f"Place {pid}", "")
                    
                    if len(selected_usernames) == 1:
                        messagebox.showinfo(
                            "Success",
                            f"Joining smallest server! Check your desktop."
                        )
                    else:
                        messagebox.showinfo(
                            "Success",
                            f"Joining smallest server with {success_count} account(s)! Check your desktop."
                        )
                else:
                    messagebox.showerror("Error", "Failed to launch Roblox.")
            
            self.root.after(0, on_done)
        
        threading.Thread(target=worker, args=(usernames, place_id), daemon=True).start()

    def _close_roblox_handles(self, handle_path):
        try:
            pids = []
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'].lower() == 'robloxplayerbeta.exe':
                        pids.append(str(proc.info['pid']))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if not pids:
                return True
            
            for pid in pids:
                try:
                    cmd = f'"{handle_path}" -accepteula -p {pid} -a'
                    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        stdin=subprocess.DEVNULL, text=True, shell=True, timeout=5)
                    
                    for line in proc.stdout.splitlines():
                        if "ROBLOX_singletonEvent" in line:
                            m = re.search(r'([0-9A-F]+):\s.*ROBLOX_singletonEvent', line, re.IGNORECASE)
                            if m:
                                handle_id = m.group(1)
                                close_cmd = f'"{handle_path}" -accepteula -p {pid} -c {handle_id} -y'
                                subprocess.run(close_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            stdin=subprocess.DEVNULL, shell=True, timeout=5)
                                print(f"[INFO] Closed ROBLOX_singletonEvent handle for PID:{pid}")
                                break
                except Exception as e:
                    print(f"[WARNING] Could not close handle for PID:{pid} - {str(e)}")
            
            return True
        except Exception as e:
            print(f"[WARNING] Error closing handles: {str(e)}")
            return False

    def _handle64_monitor_thread(self):
        target = "robloxplayerbeta.exe"
        known = set()
        
        while self.handle64_monitoring and self.handle64_path:
            try:
                current = set()
                for p in psutil.process_iter(["pid", "name"]):
                    if p.info["name"] and p.info["name"].lower() == target:
                        pid = p.info["pid"]
                        if self._is_valid_roblox_game_client(pid, target):
                            current.add(pid)
                
                new = current - known
                if new:
                    threading.Thread(target=self._handle64_close_handles, args=(list(new),), daemon=True).start()
                    known |= new
                    for pid in new:
                        print(f"[INFO] Roblox process created PID:{pid}")
                
                known -= (known - current)
                
                time.sleep(0.4)
                    
            except Exception as e:
                print(f"[WARNING] Handle64 monitor error: {str(e)}")
                time.sleep(1.0)

    def _handle64_close_handles(self, new_pids):
        """Closes ROBLOX_singletonEvent handles for the given PIDs using handle64.exe"""
        HANDLE = self.handle64_path
        
        for pid in new_pids:
            handle_value = None
            handle_found = False
            try:
                for attempt in range(5):
                    cmd = f'"{HANDLE}" -accepteula -p {pid} -a'
                    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        stdin=subprocess.DEVNULL, text=True, shell=True)
                    lines = proc.stdout.splitlines()
                    for line in lines:
                        if "ROBLOX_singletonEvent" in line:
                            m = re.search(r"([0-9A-F]+):.*ROBLOX_singletonEvent", line, re.IGNORECASE)
                            if m:
                                handle_value = m.group(1)
                                break
                            else:
                                possible = re.findall(r"\b[0-9A-F]{4,}\b", line)
                                if possible:
                                    handle_value = possible[0]
                                    break
                    if handle_value:
                        handle_found = True
                        break
                    time.sleep(1)
                if not handle_value:
                    print(f"[ERROR] Handle not closed for PID:{pid}")
                if handle_found:
                    subprocess.run(f'"{HANDLE}" -accepteula -p {pid} -c {handle_value} -y',
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, shell=True)
                    print(f"[SUCCESS] Closed handle event for PID:{pid}")
            except Exception:
                print(f"[ERROR] Handle not closed for PID:{pid}")

    def _download_handle64_exe(self, local_path):
        """Download handle64.exe from Sysinternals and extract it"""
        try:
            handle_url = "https://download.sysinternals.com/files/Handle.zip"
            handle_exe_name = "handle64.exe" if platform.architecture()[0] == "64bit" else "handle.exe"
            
            with tempfile.TemporaryDirectory() as tmpdirname:
                zip_path = os.path.join(tmpdirname, "Handle.zip")
                
                urlretrieve(handle_url, zip_path)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extract(handle_exe_name, tmpdirname)
                    extracted_path = os.path.join(tmpdirname, handle_exe_name)
                    shutil.move(extracted_path, local_path)
            
            return True
        except Exception as e:
            print(f"[ERROR] Failed to download handle64.exe: {str(e)}")
            return False

    def _find_handle64_exe(self):
        """Find handle64.exe in AccountManagerData, same directory as executable, or 'tools' subfolder"""
        try:
            handle_path = os.path.join(self.data_folder, 'handle64.exe')
            if os.path.exists(handle_path):
                print(f"[INFO] Found handle64.exe at: {handle_path}")
                return handle_path
            
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            handle_path = os.path.join(base_dir, 'handle64.exe')
            if os.path.exists(handle_path):
                print(f"[INFO] Found handle64.exe at: {handle_path}")
                return handle_path
            
            handle_path = os.path.join(base_dir, 'handle', 'handle64.exe')
            if os.path.exists(handle_path):
                print(f"[INFO] Found handle64.exe at: {handle_path}")
                return handle_path
            
            print(f"[WARNING] handle64.exe not found in: {self.data_folder}, {base_dir}, or {os.path.join(base_dir, 'handle')}")
            return None
        except Exception as e:
            print(f"[WARNING] Error finding handle64.exe: {str(e)}")
            return None

    def enable_multi_roblox(self):
        """Enable Multi Roblox + 773 fix"""
        
        if self.multi_roblox_handle is not None:
            self.disable_multi_roblox()
        
        try:
            selected_method = self.settings.get("multi_roblox_method", "default")
            use_handle64 = selected_method == "handle64"
            
            if use_handle64:
                try:
                    is_admin = ctypes.windll.shell32.IsUserAnAdmin()
                except:
                    is_admin = False
                
                if not is_admin:
                    print("[WARNING] Not running as admin! Prompting user.")
                    want_admin = messagebox.askyesno(
                        "Admin Required",
                        "handle64 mode requires administrator privileges.\n\n"
                        "The app is NOT running as admin.\n\n"
                        "Do you want to relaunch as administrator?\n\n"
                        "Click Yes to restart as admin, or No to fall back to the Default method."
                    )
                    if want_admin:
                        print("[INFO] Relaunching as administrator...")
                        try:
                            params = " ".join(f'"{a}"' for a in sys.argv[1:])
                            ctypes.windll.shell32.ShellExecuteW(
                                None, "runas", sys.executable, params, None, 1
                            )
                        except Exception as e:
                            print(f"[ERROR] Failed to relaunch as admin: {e}")
                            messagebox.showerror("Error", f"Failed to relaunch as administrator:\n{e}")
                        self.root.after(500, self.root.destroy)
                        return False
                    else:
                        print("[INFO] User declined admin, switching to Default method.")
                        self.settings["multi_roblox_method"] = "default"
                        self.save_settings()
                        use_handle64 = False
                
                if use_handle64:
                    handle64_path = self._find_handle64_exe()
                    if handle64_path:
                        print("[INFO] handle64.exe found. Using advanced multi-roblox mode.")
                        self.handle64_path = handle64_path
                        
                        self.handle64_monitoring = True
                        self.handle64_monitor_thread = threading.Thread(
                            target=self._handle64_monitor_thread,
                            daemon=True
                        )
                        self.handle64_monitor_thread.start()
                        print("[INFO] Handle64 monitor started.")
                    else:
                        print("[INFO] handle64.exe not found. Falling back to default method.")
                        use_handle64 = False
            
            if not use_handle64:
                print("[INFO] Using default multi-roblox mode.")
                roblox_running = False
                for proc in psutil.process_iter(['name']):
                    try:
                        if proc.info['name'].lower() == 'robloxplayerbeta.exe':
                            roblox_running = True
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                if roblox_running:
                    response = messagebox.askquestion(
                        "Roblox Already Running",
                        "A Roblox instance is already running.\n\n"
                        "To use Multi Roblox, you need to close all instances first.\n\n"
                        "Do you want to close all Roblox instances now?",
                        icon='warning'
                    )
                    
                    if response == 'yes':
                        subprocess.run(['taskkill', '/F', '/IM', 'RobloxPlayerBeta.exe'], 
                                     capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
                        time.sleep(1)
                        messagebox.showinfo("Success", "All Roblox instances have been closed.")
                    else:
                        return False
            
            mutex = None
            if not use_handle64:
                mutex = win32event.CreateMutex(None, True, "ROBLOX_singletonEvent")
                print("[INFO] Multi Roblox activated (mutex mode).")
                
                if win32api.GetLastError() == 183:
                    print("[INFO] Mutex already exists. Took ownership.")
            else:
                print("[INFO] Multi Roblox activated (handle64 mode).")
            
            cookies_path = os.path.join(
                os.getenv('LOCALAPPDATA'),
                r'Roblox\LocalStorage\RobloxCookies.dat'
            )
            
            cookie_file = None
            if os.path.exists(cookies_path):
                try:
                    cookie_file = open(cookies_path, 'r+b')
                    msvcrt.locking(cookie_file.fileno(), msvcrt.LK_NBLCK, os.path.getsize(cookies_path))
                    print("[SUCCESS] Error 773 fix applied.")
                except OSError:
                    print("[WARNING] Could not lock RobloxCookies.dat. It may already be locked.")
            else:
                print("[INFO] Cookies file not found. 773 fix skipped.")

            self.multi_roblox_handle = {'mutex': mutex, 'file': cookie_file}
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to enable Multi Roblox: {str(e)}")
            return False
    
    def disable_multi_roblox(self):
        """Disable Multi Roblox and release resources"""
        try:
            if self.handle64_monitoring:
                self.handle64_monitoring = False
                thread = self.handle64_monitor_thread
                if thread:
                    def _join_handle():
                        thread.join(timeout=2.0)
                    threading.Thread(target=_join_handle, daemon=True).start()
                self.handle64_monitor_thread = None
                self.handle64_path = None
                print("[INFO] Handle64 monitor stopped.")
            
            if self.multi_roblox_handle:
                if self.multi_roblox_handle.get('file'):
                    try:
                        cookie_file = self.multi_roblox_handle['file']
                        cookies_path = os.path.join(
                            os.getenv('LOCALAPPDATA'),
                            r'Roblox\LocalStorage\RobloxCookies.dat'
                        )
                        if os.path.exists(cookies_path):
                            try:
                                msvcrt.locking(cookie_file.fileno(), msvcrt.LK_UNLCK, os.path.getsize(cookies_path))
                                print("[SUCCESS] Cookie file unlocked.")
                            except Exception as unlock_error:
                                print(f"[ERROR] Failed to unlock cookie file: {unlock_error}")
                        cookie_file.close()
                    except Exception as file_error:
                        print(f"[ERROR] Failed to close cookie file: {file_error}")
                
                if self.multi_roblox_handle.get('mutex'):
                    try:
                        mutex_handle = self.multi_roblox_handle['mutex']
                        win32event.ReleaseMutex(mutex_handle)
                        win32api.CloseHandle(mutex_handle)
                        print("[SUCCESS] Multi Roblox mutex released and closed.")
                    except Exception as mutex_error:
                        print(f"[ERROR] Failed to release mutex: {mutex_error}")
                
                self.multi_roblox_handle = None
        except Exception as e:
            print(f"[ERROR] Error disabling Multi Roblox: {e}")
    
    def initialize_multi_roblox(self):
        """Initialize Multi Roblox on startup if enabled in settings"""
        success = self.enable_multi_roblox()
        if not success:
            self.settings["enable_multi_roblox"] = False
            self.save_settings()

    def open_multi_roblox_method_settings(self):
        """Open Multi Roblox method selection window"""
        method_window = tk.Toplevel(self.root)
        self.apply_window_icon(method_window)
        method_window.title("Multi Roblox Method Settings")
        method_window.geometry("400x330")
        method_window.configure(bg=self.BG_DARK)
        method_window.resizable(False, False)
        method_window.transient(self.root)
        
        if self.settings.get("enable_topmost", False):
            method_window.attributes("-topmost", True)
        
        method_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (method_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (method_window.winfo_height() // 2)
        method_window.geometry(f"+{x}+{y}")
        
        current_method = self.settings.get("multi_roblox_method", "default")
        method_var = tk.StringVar(value=current_method)
        
        handle64_path = os.path.join(self.data_folder, "handle64.exe")
        handle64_exists = os.path.exists(handle64_path)
        
        container = ttk.Frame(method_window, style="Dark.TFrame")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        header_frame = ttk.Frame(container, style="Dark.TFrame")
        header_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(
            header_frame,
            text="Select Multi Roblox Method",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text="Choose how to enable multiple Roblox instances",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(2, 0))
        
        separator = ttk.Frame(container, style="Dark.TFrame", height=1)
        separator.pack(fill="x", pady=(0, 15))
        separator.configure(relief="solid", borderwidth=1)
        
        methods_frame = ttk.Frame(container, style="Dark.TFrame")
        methods_frame.pack(fill="both", expand=True)
        
        tooltip_window = None
        tooltip_timer = None
        
        def show_tooltip(event, text):
            """Show tooltip with the same style as existing tooltips"""
            nonlocal tooltip_window, tooltip_timer
            
            if tooltip_timer:
                method_window.after_cancel(tooltip_timer)
            
            def create_tooltip():
                nonlocal tooltip_window
                if tooltip_window:
                    return
                
                x_pos = event.x_root
                y_pos = event.y_root + 20
                
                tooltip_window = tk.Toplevel(method_window)
                tooltip_window.wm_overrideredirect(True)
                tooltip_window.wm_geometry(f"+{x_pos}+{y_pos}")
                
                label = tk.Label(
                    tooltip_window,
                    text=text,
                    bg="#333333",
                    fg="white",
                    font=(self.FONT_FAMILY, 9),
                    padx=8,
                    pady=4,
                    relief="solid",
                    borderwidth=1
                )
                label.pack()
                
                if self.settings.get("enable_topmost", False):
                    tooltip_window.attributes("-topmost", True)
            
            tooltip_timer = method_window.after(500, create_tooltip)
        
        def hide_tooltip(event=None):
            """Hide tooltip"""
            nonlocal tooltip_window, tooltip_timer
            
            if tooltip_timer:
                method_window.after_cancel(tooltip_timer)
                tooltip_timer = None
            
            if tooltip_window:
                tooltip_window.destroy()
                tooltip_window = None
        
        radio_style = ttk.Style()
        radio_style.configure(
            "Dark.TRadiobutton",
            background=self.BG_DARK,
            foreground=self.FG_TEXT,
            font=(self.FONT_FAMILY, 10)
        )
        radio_style.map(
            "Dark.TRadiobutton",
            background=[("active", self.BG_DARK)],
            foreground=[("active", self.FG_TEXT)]
        )
        
        default_radio = ttk.Radiobutton(
            methods_frame,
            text="Default Method",
            variable=method_var,
            value="default",
            style="Dark.TRadiobutton"
        )
        default_radio.pack(anchor="w", pady=(0, 8))
        default_radio.bind("<Enter>", lambda e: show_tooltip(e, "Pre-create mutex. Requires closing\nexisting Roblox instances first."))
        default_radio.bind("<Leave>", hide_tooltip)
        
        handle_radio = ttk.Radiobutton(
            methods_frame,
            text="Handle64 Method (Advanced)",
            variable=method_var,
            value="handle64",
            style="Dark.TRadiobutton"
        )
        handle_radio.pack(anchor="w", pady=(0, 15))
        handle_radio.bind("<Enter>", lambda e: show_tooltip(e, "Uses handle64.exe to close handles.\nAllows multi-roblox with running instances.\nRequires administrator permission!"))
        handle_radio.bind("<Leave>", hide_tooltip)
        
        status_frame = tk.Frame(
            methods_frame,
            bg=self.BG_MID,
            relief="solid",
            borderwidth=1
        )
        status_frame.pack(fill="x", pady=(0, 10))
        
        status_inner = tk.Frame(status_frame, bg=self.BG_MID)
        status_inner.pack(fill="x", padx=10, pady=8)
        
        tk.Label(
            status_inner,
            text="handle64.exe Status:",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=(self.FONT_FAMILY, 9),
            anchor="w"
        ).pack(side="left")
        
        status_text = "✓ Installed" if handle64_exists else "✗ Not Installed"
        status_color = "#90EE90" if handle64_exists else "#FFB6C1"
        
        status_label = tk.Label(
            status_inner,
            text=status_text,
            bg=self.BG_MID,
            fg=status_color,
            font=(self.FONT_FAMILY, 9, "bold"),
            anchor="e"
        )
        status_label.pack(side="right")
        
        download_btn = None
        if not handle64_exists:
            def download_handle64():
                """Download handle64.exe"""
                download_btn.config(state="disabled", text="Downloading...")
                method_window.update()
                
                success = self._download_handle64_exe(handle64_path)
                
                if success:
                    messagebox.showinfo("Success", "handle64.exe downloaded successfully!")
                    status_label.config(text="✓ Installed", fg="#90EE90")
                    download_btn.config(state="disabled", text="✓ Downloaded")
                else:
                    messagebox.showerror("Download Failed", "Failed to download handle64.exe. Check your internet connection.")
                    download_btn.config(state="normal", text="Download handle64.exe")
            
            download_btn = ttk.Button(
                methods_frame,
                text="Download handle64.exe",
                style="Dark.TButton",
                command=download_handle64
            )
            download_btn.pack(fill="x", pady=(0, 15))
        
        btn_container = ttk.Frame(container, style="Dark.TFrame")
        btn_container.pack(fill="x", pady=(15, 0))
        
        def save_method():
            selected = method_var.get()
            if selected == "handle64" and not os.path.exists(handle64_path):
                messagebox.showwarning(
                    "handle64 Not Available",
                    "Please download handle64.exe first."
                )
                return
            
            was_active = self.multi_roblox_handle is not None
            
            if was_active:
                old_method = self.settings.get("multi_roblox_method", "default")
                if old_method != selected:
                    print(f"[INFO] Switching multi-roblox from {old_method} to {selected}")
                    self.disable_multi_roblox()
            
            self.settings["multi_roblox_method"] = selected
            try:
                with open(self.settings_file, 'w') as f:
                    json.dump(self.settings, f, indent=2)
            except Exception as e:
                print(f"[ERROR] Failed to save settings: {e}")
            
            if was_active:
                success = self.enable_multi_roblox()
                if not success:
                    messagebox.showerror("Error", "Failed to restart Multi Roblox with new method.")
                    method_window.destroy()
                    return
            
            actual_method = self.settings.get("multi_roblox_method", "default")
            messagebox.showinfo("Success", f"Multi Roblox method set to: {actual_method.title()}")
            method_window.destroy()
        
        save_btn = ttk.Button(
            btn_container,
            text="Save",
            style="Dark.TButton",
            command=save_method
        )
        save_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        cancel_btn = ttk.Button(
            btn_container,
            text="Cancel",
            style="Dark.TButton",
            command=method_window.destroy
        )
        cancel_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))


    def _run_encryption_switch(self):
        """Run the encryption method switch process"""
        
        current_accounts = self.manager.accounts.copy()
        
        self.manager.encryption_config.reset_encryption()
        self.manager.encryptor = None
        self.manager.accounts = current_accounts
        self.manager.save_accounts()
        
        self.root.destroy()
        
        setup_ui = EncryptionSetupUI()
        result = setup_ui.setup_encryption_ui()
        
        if setup_ui.should_exit:
            sys.exit(0)
        
        
        try:
            new_method = setup_ui.encryption_config.get_encryption_method()
            
            if new_method == 'password':
                if result is None:
                    raise ValueError("Password setup failed - no password returned")
                new_manager = RobloxAccountManager(password=result)
            else:
                new_manager = RobloxAccountManager()
            
            new_manager.save_accounts()
            
            messagebox.showinfo("Success", "Encryption method switched successfully!\nYour accounts have been re-encrypted.")
            
            new_root = tk.Tk()
            app = AccountManagerUI(new_root, new_manager)
            new_root.mainloop()
            
        except Exception as e:
            print(f"[ERROR] Failed to switch encryption: {e}")
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to switch encryption: {e}")
            sys.exit(1)

    def open_settings(self):
        """Open the Settings window"""
        if hasattr(self, 'settings_window') and self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus()
            return
        
        settings_window = tk.Toplevel(self.root)
        self.apply_window_icon(settings_window)
        self.settings_window = settings_window
        settings_window.title("Settings")
        settings_window.configure(bg=self.BG_DARK)
        settings_window.resizable(True, True)
        
        settings_window.transient(self.root)
        
        def on_close():
            self.settings_window = None
            settings_window.destroy()
        
        def on_settings_close():
            """Save window position before closing"""
            save_current_theme = getattr(self, "_theme_editor_save_current_config", None)
            if callable(save_current_theme):
                try:
                    save_current_theme()
                except Exception as exc:
                    print(f"[ERROR] Failed to save current theme config on close: {exc}")

            self.settings['settings_window_position'] = {
                'x': settings_window.winfo_x(),
                'y': settings_window.winfo_y()
            }
            self.save_settings()
            self.settings_window = None
            settings_window.destroy()
        
        settings_window.protocol("WM_DELETE_WINDOW", on_settings_close)
        
        if self.settings.get("enable_topmost", False):
            settings_window.attributes("-topmost", True)
        
        self.root.update_idletasks()
        
        settings_width = 380
        settings_height = 560
        
        saved_pos = self.settings.get('settings_window_position')
        if saved_pos and saved_pos.get('x') is not None and saved_pos.get('y') is not None:
            x = saved_pos['x']
            y = saved_pos['y']
        else:
            main_x = self.root.winfo_x()
            main_y = self.root.winfo_y()
            main_width = self.root.winfo_width()
            main_height = self.root.winfo_height()
            x = main_x + (main_width - settings_width) // 2
            y = main_y + (main_height - settings_height) // 2
        
        settings_window.geometry(f"{settings_width}x{settings_height}+{x}+{y}")
        
        tabs = ttk.Notebook(settings_window)
        tabs.pack(fill=tk.BOTH, expand=True)
        
        general_tab = ttk.Frame(tabs, style="Dark.TFrame")
        tabs.add(general_tab, text="General")
        
        themes_tab = ttk.Frame(tabs, style="Dark.TFrame")
        tabs.add(themes_tab, text="Themes")
        
        roblox_tab = ttk.Frame(tabs, style="Dark.TFrame")
        tabs.add(roblox_tab, text="Roblox")
        
        tool_tab = ttk.Frame(tabs, style="Dark.TFrame")
        tabs.add(tool_tab, text="Tool")
        
        discord_tab = ttk.Frame(tabs, style="Dark.TFrame")
        tabs.add(discord_tab, text="Discord")
        
        developer_tab = ttk.Frame(tabs, style="Dark.TFrame")
        tabs.add(developer_tab, text="Developer")
        
        dev_frame = ttk.Frame(developer_tab, style="Dark.TFrame")
        dev_frame.pack(fill="both", expand=True, padx=20, pady=15)

        ttk.Label(
            dev_frame,
            text="Developer",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w", pady=(0, 2))

        ttk.Label(
            dev_frame,
            text="Developer options are dangerous. Use only if you \nknow what you're doing",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(0, 10))

        sep = ttk.Frame(dev_frame, style="Dark.TFrame", height=1)
        sep.pack(fill="x", pady=(0, 8))
        sep.configure(relief="solid", borderwidth=1)

        dev_mode_var = tk.BooleanVar(value=self.settings.get("developer_mode", False))
        copy_cookie_var = tk.BooleanVar(value=self.settings.get("enable_copy_cookie", False))
        ws_enabled_var = tk.BooleanVar(value=self.settings.get("websocket_enabled", False))
        ws_port_var = tk.StringVar(value=str(self.settings.get("websocket_port", 8765)))
        ws_require_password_var = tk.BooleanVar(value=self.settings.get("websocket_require_password", False))
        ws_password_var = tk.StringVar(value="")

        def _save_dev_mode():
            self.settings["developer_mode"] = dev_mode_var.get()
            if not dev_mode_var.get():
                copy_cookie_var.set(False)
                self.settings["enable_copy_cookie"] = False
                ws_enabled_var.set(False)
                self.settings["websocket_enabled"] = False
                self.stop_websocket_server()
            self.save_settings()
            _update_dev_controls()

        def _save_copy_cookie():
            self.settings["enable_copy_cookie"] = copy_cookie_var.get()
            self.save_settings()

        def _save_ws_enabled():
            self.settings["websocket_enabled"] = ws_enabled_var.get()
            self.save_settings()
            if ws_enabled_var.get():
                self.start_websocket_server()
            else:
                self.stop_websocket_server()
            _update_dev_controls()

        def _apply_ws_port():
            port_text = ws_port_var.get().strip()
            try:
                port = int(port_text)
            except Exception:
                messagebox.showerror("Invalid Port", "WebSocket port must be a number.", parent=settings_window)
                return

            if port < 1 or port > 65535:
                messagebox.showerror("Invalid Port", "WebSocket port must be between 1 and 65535.", parent=settings_window)
                return

            self.settings["websocket_port"] = port
            ws_port_var.set(str(port))
            self.save_settings()
            if ws_enabled_var.get():
                self.restart_websocket_server()
            print(f"[INFO] WebSocket port set to {port}")

        def _save_ws_require_password():
            self.settings["websocket_require_password"] = ws_require_password_var.get()
            self.save_settings()
            _update_dev_controls()

        def _set_ws_password():
            password = ws_password_var.get()
            if not password.strip():
                messagebox.showwarning("Missing Password", "Please enter a password.", parent=settings_window)
                return

            if self._set_websocket_password(password):
                ws_password_var.set("")
                messagebox.showinfo("Saved", "WebSocket password has been updated.", parent=settings_window)
            else:
                messagebox.showerror("Error", "Failed to save WebSocket password.", parent=settings_window)

        def _update_dev_controls():
            state = "normal" if dev_mode_var.get() else "disabled"
            try:
                copy_check.config(state=state)
            except Exception:
                pass
            for widget in (ws_enabled_check, ws_port_entry, ws_port_set_btn, ws_require_password_check, ws_password_entry, ws_password_set_btn):
                try:
                    widget.config(state=state)
                except Exception:
                    pass

            ws_detail_state = "normal" if (dev_mode_var.get() and ws_enabled_var.get()) else "disabled"
            for widget in (ws_port_entry, ws_port_set_btn, ws_require_password_check):
                try:
                    widget.config(state=ws_detail_state)
                except Exception:
                    pass

            ws_password_state = "normal" if (dev_mode_var.get() and ws_enabled_var.get() and ws_require_password_var.get()) else "disabled"
            for widget in (ws_password_entry, ws_password_set_btn):
                try:
                    widget.config(state=ws_password_state)
                except Exception:
                    pass

        dev_check = ttk.Checkbutton(
            dev_frame,
            text="Enable Developer Mode",
            variable=dev_mode_var,
            style="Dark.TCheckbutton",
            command=_save_dev_mode
        )
        dev_check.pack(anchor="w", pady=2)

        copy_check = ttk.Checkbutton(
            dev_frame,
            text="Enable Copy Cookie",
            variable=copy_cookie_var,
            style="Dark.TCheckbutton",
            command=_save_copy_cookie
        )
        copy_check.pack(anchor="w", pady=2)

        ws_sep = ttk.Frame(dev_frame, style="Dark.TFrame", height=1)
        ws_sep.pack(fill="x", pady=(8, 8))
        ws_sep.configure(relief="solid", borderwidth=1)

        ttk.Label(
            dev_frame,
            text="WebSocket Server",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 10, "bold")
        ).pack(anchor="w", pady=(0, 2))

        ttk.Label(
            dev_frame,
            text="Control RAM from local WebSocket clients.",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(0, 6))

        ws_enabled_check = ttk.Checkbutton(
            dev_frame,
            text="Enable WebSocket",
            variable=ws_enabled_var,
            style="Dark.TCheckbutton",
            command=_save_ws_enabled
        )
        ws_enabled_check.pack(anchor="w", pady=(0, 4))

        ws_port_row = ttk.Frame(dev_frame, style="Dark.TFrame")
        ws_port_row.pack(fill="x", pady=(0, 4))
        ttk.Label(ws_port_row, text="Port:", style="Dark.TLabel", font=(self.FONT_FAMILY, 9)).pack(side="left")
        ws_port_entry = ttk.Entry(ws_port_row, textvariable=ws_port_var, width=10, style="Dark.TEntry")
        ws_port_entry.pack(side="left", padx=(6, 6))
        ws_port_set_btn = ttk.Button(ws_port_row, text="Set", style="Dark.TButton", command=_apply_ws_port)
        ws_port_set_btn.pack(side="left")

        ws_require_password_check = ttk.Checkbutton(
            dev_frame,
            text="Request require password",
            variable=ws_require_password_var,
            style="Dark.TCheckbutton",
            command=_save_ws_require_password
        )
        ws_require_password_check.pack(anchor="w", pady=(0, 4))

        ws_password_row = ttk.Frame(dev_frame, style="Dark.TFrame")
        ws_password_row.pack(fill="x", pady=(0, 2))
        ws_password_entry = ttk.Entry(ws_password_row, textvariable=ws_password_var, show="*", style="Dark.TEntry")
        ws_password_entry.pack(side="left", fill="x", expand=True)
        ws_password_set_btn = ttk.Button(ws_password_row, text="Set", style="Dark.TButton", command=_set_ws_password)
        ws_password_set_btn.pack(side="left", padx=(6, 0))
        _update_dev_controls()
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background=self.BG_DARK, borderwidth=0)
        style.configure('TNotebook.Tab', background=self.BG_MID, foreground=self.FG_TEXT, font=(self.FONT_FAMILY, max(8, self.FONT_SIZE - 1)), focuscolor='none')
        style.map('TNotebook.Tab', background=[('selected', self.BG_LIGHT)], focuscolor=[('!focus', 'none')])
        
        main_frame = ttk.Frame(general_tab, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        topmost_var = tk.BooleanVar(value=self.settings.get("enable_topmost", False))
        multi_roblox_var = tk.BooleanVar(value=self.settings.get("enable_multi_roblox", False))
        confirm_launch_var = tk.BooleanVar(value=self.settings.get("confirm_before_launch", False))
        multi_select_var = tk.BooleanVar(value=self.settings.get("enable_multi_select", False))
        
        checkbox_style = ttk.Style()
        checkbox_style.configure(
            "Dark.TCheckbutton",
            background=self.BG_DARK,
            foreground=self.FG_TEXT,
            font=(self.FONT_FAMILY, self.FONT_SIZE)
        )
        
        def auto_save_setting(setting_name, var):
            def save():
                self.settings[setting_name] = var.get()
                
                if setting_name == "enable_topmost":
                    self.root.attributes("-topmost", var.get())
                    settings_window.attributes("-topmost", var.get())
                
                self.save_settings()
            return save
        
        def on_multi_roblox_toggle():
            if multi_roblox_var.get():
                success = self.enable_multi_roblox()
                if not success:
                    multi_roblox_var.set(False)
                    self.settings["enable_multi_roblox"] = False
                else:
                    self.settings["enable_multi_roblox"] = True
            else:
                self.disable_multi_roblox()
                self.settings["enable_multi_roblox"] = False
            
            self.save_settings()
        
        def on_multi_select_toggle():
            self.settings["enable_multi_select"] = multi_select_var.get()
            if multi_select_var.get():
                self.account_list.config(selectmode=tk.EXTENDED)
            else:
                self.account_list.config(selectmode=tk.SINGLE)
            self.save_settings()
        
        topmost_check = ttk.Checkbutton(
            main_frame,
            text="Enable Topmost",
            variable=topmost_var,
            style="Dark.TCheckbutton",
            command=auto_save_setting("enable_topmost", topmost_var)
        )
        topmost_check.pack(anchor="w", pady=2)
        self.topmost_check = topmost_check

        multi_roblox_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        multi_roblox_frame.pack(anchor="w", fill="x", pady=2)

        multi_roblox_check = ttk.Checkbutton(
            multi_roblox_frame,
            text="Enable Multi Roblox + 773 fix",
            variable=multi_roblox_var,
            style="Dark.TCheckbutton",
            command=on_multi_roblox_toggle
        )
        multi_roblox_check.pack(side="left", anchor="w")
        self.multi_roblox_check = multi_roblox_check

        def open_method_settings():
            """Open Multi Roblox method selection window"""
            self.open_multi_roblox_method_settings()

        settings_btn = tk.Button(
            multi_roblox_frame,
            text="⚙️",
            bg=self.BG_DARK,
            fg=self.FG_TEXT,
            font=("Segoe UI", 10),
            relief="flat",
            bd=0,
            cursor="hand2",
            command=open_method_settings,
            padx=5
        )
        settings_btn.pack(side="right", padx=(5, 0))
        self.settings_btn = settings_btn

        confirm_check = ttk.Checkbutton(
            main_frame,
            text="Confirm Before Launch",
            variable=confirm_launch_var,
            style="Dark.TCheckbutton",
            command=auto_save_setting("confirm_before_launch", confirm_launch_var)
        )
        confirm_check.pack(anchor="w", pady=2)
        self.confirm_check = confirm_check

        multi_select_check = ttk.Checkbutton(
            main_frame,
            text="Multi Select (Ctrl + Click)",
            variable=multi_select_var,
            style="Dark.TCheckbutton",
            command=on_multi_select_toggle
        )
        multi_select_check.pack(anchor="w", pady=2)
        self.multi_select_check = multi_select_check

        disable_launch_popup_var = tk.BooleanVar(value=self.settings.get("disable_launch_popup", False))
        disable_launch_popup_check = ttk.Checkbutton(
            main_frame,
            text="Disable Launch Success Popup",
            variable=disable_launch_popup_var,
            style="Dark.TCheckbutton",
            command=auto_save_setting("disable_launch_popup", disable_launch_popup_var)
        )
        disable_launch_popup_check.pack(anchor="w", pady=2)
        self.disable_launch_popup_check = disable_launch_popup_check

        auto_tile_windows_var = tk.BooleanVar(value=self.settings.get("auto_tile_windows", False))
        auto_tile_check = ttk.Checkbutton(
            main_frame,
            text="Auto Tile Windows",
            variable=auto_tile_windows_var,
            style="Dark.TCheckbutton",
            command=auto_save_setting("auto_tile_windows", auto_tile_windows_var)
        )
        auto_tile_check.pack(anchor="w", pady=2)
        self.auto_tile_check = auto_tile_check

        def is_start_menu_shortcut_present():
            """Check if Start Menu shortcut exists"""
            start_menu = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
            shortcut_path = os.path.join(start_menu, "Roblox Account Manager.lnk")
            return os.path.exists(shortcut_path)

        def toggle_start_menu_shortcut():
            """Create or remove Start Menu shortcut"""
            start_menu = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
            shortcut_path = os.path.join(start_menu, "Roblox Account Manager.lnk")

            if start_menu_var.get():
                try:
                    exe_path = os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else sys.argv[0])
                    if not getattr(sys, 'frozen', False):
                        exe_path = os.path.abspath(sys.argv[0])

                    ps_script = f'''
                    $WshShell = New-Object -comObject WScript.Shell
                    $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
                    $Shortcut.TargetPath = "{exe_path}"
                    $Shortcut.WorkingDirectory = "{os.path.dirname(exe_path)}"
                    $Shortcut.Description = "Roblox Account Manager"
                    $Shortcut.Save()
                    '''
                    subprocess.run(["powershell", "-Command", ps_script], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    print("[INFO] Start Menu shortcut created")
                except Exception as e:
                    print(f"[ERROR] Failed to create Start Menu shortcut: {e}")
                    start_menu_var.set(False)
            else:
                try:
                    if os.path.exists(shortcut_path):
                        os.remove(shortcut_path)
                        print("[INFO] Start Menu shortcut removed")
                except Exception as e:
                    print(f"[ERROR] Failed to remove Start Menu shortcut: {e}")

        start_menu_var = tk.BooleanVar(value=is_start_menu_shortcut_present())
        start_menu_check = ttk.Checkbutton(
            main_frame,
            text="Add to Start Menu",
            variable=start_menu_var,
            style="Dark.TCheckbutton",
            command=toggle_start_menu_shortcut
        )
        start_menu_check.pack(anchor="w", pady=2)
        self.start_menu_check = start_menu_check

        max_games_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        max_games_frame.pack(fill="x", pady=2)

        ttk.Label(
            max_games_frame,
            text="Max Recent Games:",
            style="Dark.TLabel",
            font=("Segoe UI", 10)
        ).pack(side="left")

        max_games_var = tk.IntVar(value=self.settings.get("max_recent_games", 10))

        def on_max_games_change():
            try:
                new_value = max_games_var.get()
                self.settings["max_recent_games"] = new_value
                self.save_settings()
                if len(self.settings["game_list"]) > new_value:
                    self.settings["game_list"] = self.settings["game_list"][:new_value]
                    self.save_settings()
                    self.refresh_game_list()
            except:
                pass

        max_games_spinner = tk.Spinbox(
            max_games_frame,
            from_=5,
            to=50,
            textvariable=max_games_var,
            width=8,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            buttonbackground=self.BG_LIGHT,
            font=(self.FONT_FAMILY, 9),
            command=on_max_games_change,
            readonlybackground=self.BG_MID,
            selectbackground=self.FG_ACCENT,
            selectforeground=self.FG_TEXT,
            insertbackground=self.FG_TEXT,
            relief="flat",
            borderwidth=1,
            highlightthickness=0
        )
        max_games_spinner.pack(side="right")
        self.max_games_spinner = max_games_spinner

        max_games_spinner.bind("<KeyRelease>", lambda e: on_max_games_change())
        max_games_spinner.bind("<FocusOut>", lambda e: on_max_games_change())

        ttk.Label(main_frame, text="", style="Dark.TLabel").pack(pady=3)
        
        console_button = ttk.Button(
            main_frame,
            text="Console Output",
            style="Dark.TButton",
            command=self.open_console_window
        )
        console_button.pack(fill="x", pady=(0, 5))
        
        close_button = ttk.Button(
            main_frame,
            text="Close",
            style="Dark.TButton",
            command=settings_window.destroy
        )
        close_button.pack(fill="x", pady=(5, 5))
        
        is_unstable = bool(re.search(r'(alpha|beta)', self.APP_VERSION, re.IGNORECASE))
        version_text = f"Version: {self.APP_VERSION}"
        if is_unstable:
            version_text += "\nThis is an unstable version"
        
        version_label = ttk.Label(
            main_frame,
            text=version_text,
            style="Dark.TLabel",
            font=("Segoe UI", 9)
        )
        version_label.pack(anchor="e", pady=(6, 0))
        
        roblox_frame = ttk.Frame(roblox_tab, style="Dark.TFrame")
        roblox_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        def open_launcher_selection():
            launcher_window = tk.Toplevel(settings_window)
            launcher_window.title("Roblox Launcher")
            launcher_window.geometry("420x360")
            launcher_window.configure(bg=self.BG_DARK)
            launcher_window.resizable(False, False)
            launcher_window.transient(settings_window)
            launcher_window.grab_set()
            self.apply_window_icon(launcher_window)
            
            if self.settings.get("enable_topmost", False):
                launcher_window.attributes("-topmost", True)
            
            launcher_window.update_idletasks()
            x = settings_window.winfo_x() + (settings_window.winfo_width() // 2) - (launcher_window.winfo_width() // 2)
            y = settings_window.winfo_y() + (settings_window.winfo_height() // 2) - (launcher_window.winfo_height() // 2)
            launcher_window.geometry(f"+{x}+{y}")
            
            container = ttk.Frame(launcher_window, style="Dark.TFrame")
            container.pack(fill="both", expand=True, padx=20, pady=20)
            
            header_frame = ttk.Frame(container, style="Dark.TFrame")
            header_frame.pack(fill="x", pady=(0, 15))
            
            ttk.Label(
                header_frame,
                text="Select a Launcher",
                style="Dark.TLabel",
                font=(self.FONT_FAMILY, 11, "bold")
            ).pack(anchor="w")
            
            ttk.Label(
                header_frame,
                text="Choose how to launch Roblox games",
                style="Dark.TLabel",
                font=(self.FONT_FAMILY, 8)
            ).pack(anchor="w", pady=(2, 0))
            
            separator = ttk.Frame(container, style="Dark.TFrame", height=1)
            separator.pack(fill="x", pady=(0, 15))
            separator.configure(relief="solid", borderwidth=1)
            
            current_launcher = self.settings.get("roblox_launcher", "default")
            launcher_var = tk.StringVar(value=current_launcher)
            custom_launcher_path_var = tk.StringVar(value=str(self.settings.get("custom_roblox_launcher_path", "") or "").strip())
            
            radio_style = ttk.Style()
            radio_style.configure(
                "Dark.TRadiobutton",
                background=self.BG_DARK,
                foreground=self.FG_TEXT,
                font=(self.FONT_FAMILY, 9)
            )
            radio_style.map(
                "Dark.TRadiobutton",
                background=[('active', self.BG_DARK)],
                foreground=[('active', self.FG_TEXT)]
            )
            
            launchers_frame = ttk.Frame(container, style="Dark.TFrame")
            launchers_frame.pack(fill="both", expand=True)
            
            launchers = [
                ("Default", "default"),
                ("Bloxstrap", "bloxstrap"),
                ("Fishstrap", "fishstrap"),
                ("Froststrap", "froststrap"),
                ("Voidstrap", "voidstrap"),
                ("Roblox Client", "client"),
                ("Custom", "custom"),
            ]

            custom_launcher_display_var = tk.StringVar()

            def _format_custom_launcher_path_display(path, max_len=56):
                norm = str(path or "").strip().replace("\\", "/")
                if not norm:
                    return ""
                if len(norm) <= max_len:
                    return norm

                lower_norm = norm.lower()
                marker = "/appdata/local/"
                if marker in lower_norm:
                    marker_index = lower_norm.index(marker)
                    prefix = "C:/Users/..." if lower_norm.startswith("c:/users/") else (norm[:10] + "...")
                    tail = norm[marker_index:]
                    available = max_len - len(prefix)
                    if available <= 3:
                        return (prefix[:max_len - 3] + "...") if max_len > 3 else prefix[:max_len]
                    if len(tail) > available:
                        tail = tail[:available - 3] + "..."
                    return prefix + tail

                start_len = max(10, int(max_len * 0.35))
                end_len = max(12, max_len - start_len - 3)
                return f"{norm[:start_len]}...{norm[-end_len:]}"

            def _refresh_custom_launcher_path_display(*_):
                custom_launcher_display_var.set(
                    _format_custom_launcher_path_display(custom_launcher_path_var.get())
                )

            custom_launcher_path_var.trace_add("write", _refresh_custom_launcher_path_display)
            _refresh_custom_launcher_path_display()
            
            for name, value in launchers:
                row = ttk.Frame(launchers_frame, style="Dark.TFrame")
                row.pack(fill="x", pady=3)

                rb = ttk.Radiobutton(
                    row,
                    text=name,
                    variable=launcher_var,
                    value=value,
                    style="Dark.TRadiobutton"
                )
                rb.pack(side="left", anchor="w")

                if value == "custom":
                    def browse_custom_launcher():
                        selected_path = filedialog.askopenfilename(
                            title="Select Custom Roblox Launcher (.exe)",
                            filetypes=[("Executable Files", "*.exe")],
                        )
                        if not selected_path:
                            return
                        custom_launcher_path_var.set(selected_path)
                        launcher_var.set("custom")

                    ttk.Button(
                        row,
                        text="Browse .exe",
                        style="Dark.TButton",
                        command=browse_custom_launcher,
                    ).pack(side="right")

                    ttk.Label(
                        row,
                        textvariable=custom_launcher_display_var,
                        style="Dark.TLabel",
                        font=(self.FONT_FAMILY, 8),
                    ).pack(side="left", fill="x", expand=True, padx=(8, 6))
            
            def save_and_close():
                selected = launcher_var.get()
                custom_path = custom_launcher_path_var.get().strip()

                if selected == "custom":
                    if not custom_path:
                        messagebox.showwarning("Custom Launcher Required", "Please choose a custom launcher .exe file.", parent=launcher_window)
                        return
                    if not custom_path.lower().endswith(".exe"):
                        messagebox.showwarning("Invalid File", "Custom launcher must be an .exe file.", parent=launcher_window)
                        return
                    if not os.path.isfile(custom_path):
                        messagebox.showwarning("File Not Found", "Selected custom launcher file was not found.", parent=launcher_window)
                        return

                self.settings["roblox_launcher"] = selected
                self.settings["custom_roblox_launcher_path"] = custom_path
                self.save_settings()
                launcher_window.destroy()
            
            ttk.Button(
                container,
                text="Close",
                style="Dark.TButton",
                command=save_and_close
            ).pack(fill="x", pady=(15, 0))
        
        launcher_btn = ttk.Button(
            roblox_frame,
            text="Roblox Launcher",
            style="Dark.TButton",
            command=open_launcher_selection
        )
        launcher_btn.pack(fill="x", pady=(0, 5))
        
        def force_close_roblox():
            confirm = messagebox.askyesno(
                "Confirm Force Close",
                "Are you sure you want to force close all Roblox instances?"
            )
            if not confirm:
                return

            try:
                result = subprocess.run(
                    ['taskkill', '/F', '/IM', 'RobloxPlayerBeta.exe'],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                if result.returncode == 0:
                    messagebox.showinfo("Success", "All Roblox instances have been closed.")
                else:
                    messagebox.showinfo("Info", "No Roblox instances were found running.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to close Roblox: {e}")
        
        force_close_btn = ttk.Button(
            roblox_frame,
            text="Force Close All Roblox",
            style="Dark.TButton",
            command=force_close_roblox
        )
        force_close_btn.pack(fill="x", pady=(0, 5))
        
        rename_var = tk.BooleanVar(value=self.settings.get("rename_roblox_windows", False))
        
        def on_rename_toggle():
            enabled = rename_var.get()
            self.settings["rename_roblox_windows"] = enabled
            self.save_settings()
            
            if enabled:
                self.start_rename_monitoring()
            else:
                self.stop_rename_monitoring()
        
        ttk.Checkbutton(
            roblox_frame,
            text="Rename Roblox Windows",
            variable=rename_var,
            style="Dark.TCheckbutton",
            command=on_rename_toggle
        ).pack(anchor="w", pady=(0, 10))
        
        anti_afk_btn = ttk.Button(
            roblox_frame,
            text="Anti-AFK",
            style="Dark.TButton",
            command=self.open_anti_afk_window
        )
        anti_afk_btn.pack(fill="x", pady=(10, 5))
        self.anti_afk_btn = anti_afk_btn

        optimize_ram_var = tk.BooleanVar(value=self.settings.get("optimize_roblox_ram", False))
        optimize_ram_limit_var = tk.IntVar(value=int(self.settings.get("optimize_roblox_ram_limit_mb", 750)))

        def on_optimize_ram_toggle():
            enabled = optimize_ram_var.get()
            self.settings["optimize_roblox_ram"] = enabled
            try:
                self.settings["optimize_roblox_ram_limit_mb"] = max(1, int(optimize_ram_limit_var.get()))
            except Exception:
                self.settings["optimize_roblox_ram_limit_mb"] = 750
            self.save_settings()
            if enabled:
                self.start_optimize_roblox_ram()
            else:
                self.stop_optimize_roblox_ram()

        optimize_ram_check = ttk.Checkbutton(
            roblox_frame,
            text="Boost Roblox Ram (may cause crash)",
            variable=optimize_ram_var,
            style="Dark.TCheckbutton",
            command=on_optimize_ram_toggle
        )
        optimize_ram_check.pack(anchor="w", pady=(0, 10))
        self.optimize_ram_check = optimize_ram_check

        graphics_opt_var = tk.BooleanVar(value=self.settings.get("graphics_optimizer_enabled", False))

        def on_graphics_opt_toggle():
            enabled = graphics_opt_var.get()
            self.settings["graphics_optimizer_enabled"] = enabled
            self.save_settings()
            from classes.roblox_api import RobloxAPI
            RobloxAPI.apply_graphics_optimization(enabled)

        graphics_opt_check = ttk.Checkbutton(
            roblox_frame,
            text="Graphics Optimizer (Extreme Low CPU/RAM Mode)",
            variable=graphics_opt_var,
            style="Dark.TCheckbutton",
            command=on_graphics_opt_toggle
        )
        graphics_opt_check.pack(anchor="w", pady=(0, 10))
        self.graphics_opt_check = graphics_opt_check

        optimize_ram_limit_row = ttk.Frame(roblox_frame, style="Dark.TFrame")
        optimize_ram_limit_row.pack(fill="x", pady=(0, 4))

        optimize_ram_limit_label = ttk.Label(
            optimize_ram_limit_row,
            text="Low Ram Limit (MB):",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        )
        optimize_ram_limit_label.pack(side="left")

        optimize_ram_limit_entry = tk.Spinbox(
            optimize_ram_limit_row,
            from_=100,
            to=4096,
            increment=25,
            textvariable=optimize_ram_limit_var,
            width=8,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            buttonbackground=self.BG_LIGHT,
            font=(self.FONT_FAMILY, 9),
            readonlybackground=self.BG_MID,
            disabledbackground=self.BG_MID,
            disabledforeground=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            selectforeground=self.FG_TEXT,
            insertbackground=self.FG_TEXT,
            relief="flat",
            borderwidth=1,
            highlightthickness=0,
        )
        optimize_ram_limit_entry.pack(side="right")

        optimize_ram_tooltip = None

        def show_optimize_ram_tooltip(_event=None):
            nonlocal optimize_ram_tooltip
            if optimize_ram_tooltip:
                return
            optimize_ram_tooltip = tk.Toplevel(self.root)
            optimize_ram_tooltip.wm_overrideredirect(True)
            if self.settings.get("enable_topmost", False):
                try:
                    optimize_ram_tooltip.attributes("-topmost", True)
                except Exception:
                    pass
            tooltip_label = tk.Label(
                optimize_ram_tooltip,
                text="Low ram limit can increase the CPU of the program, reccomended value is 750 mb",
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                font=(self.FONT_FAMILY, max(8, self.FONT_SIZE - 1)),
                padx=8,
                pady=4,
                relief="solid",
                borderwidth=1,
                highlightbackground=self.BG_LIGHT,
                highlightcolor=self.BG_LIGHT,
            )
            tooltip_label.pack()
            optimize_ram_tooltip.update_idletasks()
            x = optimize_ram_limit_entry.winfo_rootx()
            y = optimize_ram_limit_entry.winfo_rooty() + optimize_ram_limit_entry.winfo_height() + 5
            optimize_ram_tooltip.wm_geometry(f"+{x}+{y}")

        def hide_optimize_ram_tooltip(_event=None):
            nonlocal optimize_ram_tooltip
            if optimize_ram_tooltip:
                try:
                    optimize_ram_tooltip.destroy()
                except Exception:
                    pass
                optimize_ram_tooltip = None

        optimize_ram_limit_label.bind("<Enter>", show_optimize_ram_tooltip)
        optimize_ram_limit_label.bind("<Leave>", hide_optimize_ram_tooltip)
        optimize_ram_limit_entry.bind("<Enter>", show_optimize_ram_tooltip)
        optimize_ram_limit_entry.bind("<Leave>", hide_optimize_ram_tooltip)

        self.optimize_ram_limit_entry = optimize_ram_limit_entry

        def save_optimize_ram_limit(*_):
            try:
                self.settings["optimize_roblox_ram_limit_mb"] = max(1, int(optimize_ram_limit_var.get()))
            except Exception:
                self.settings["optimize_roblox_ram_limit_mb"] = 750
            self.save_settings()

        optimize_ram_limit_entry.bind("<KeyRelease>", save_optimize_ram_limit)
        optimize_ram_limit_entry.bind("<FocusOut>", save_optimize_ram_limit)

        def update_optimize_ram_controls():
            state = "normal" if optimize_ram_var.get() else "disabled"
            optimize_ram_limit_entry.config(state=state)

        update_optimize_ram_controls()

        def on_optimize_ram_toggle_wrapper():
            update_optimize_ram_controls()
            on_optimize_ram_toggle()

        if self.settings.get("anti_afk_enabled", False):
            self.root.after(1000, self.start_anti_afk)

        if self.settings.get("optimize_roblox_ram", False):
            self.root.after(1200, self.start_optimize_roblox_ram)

        optimize_ram_check.config(command=on_optimize_ram_toggle_wrapper)

        if self.settings.get("rename_roblox_windows", False):
            self.root.after(1000, self.start_rename_monitoring)
        
        if self.settings.get("active_instances_monitoring", False):
            self.root.after(1500, self.start_instances_monitoring)
        
        themes_frame = ttk.Frame(themes_tab, style="Dark.TFrame")
        themes_frame.pack(fill="both", expand=True, padx=20, pady=15)

        theme_state = {
            "loaded_theme_name": self.settings.get("selected_theme", "Dark"),
            "base_theme_data": None,
            "theme_is_dirty": False,
            "suspend_dirty_events": False,
        }

        theme_title_var = tk.StringVar(value=f"Theme: {theme_state['loaded_theme_name']}")
        theme_selector_var = tk.StringVar()
        theme_status_var = tk.StringVar(value="")

        theme_catalog = {}

        def set_theme_title(text):
            theme_title_var.set(f"Theme: {text}")

        def refresh_theme_catalog(preferred_name=None):
            nonlocal theme_catalog
            theme_catalog = self.theme_manager.get_available_themes()
            theme_names = sorted(theme_catalog.keys(), key=str.lower)
            theme_selector["values"] = theme_names

            target = preferred_name or theme_state["loaded_theme_name"]
            if target not in theme_catalog:
                for name in theme_names:
                    if name.lower() == str(target).lower():
                        target = name
                        break
            if target not in theme_catalog and theme_names:
                target = theme_names[0]

            theme_selector_var.set(target or "")

        header_row = ttk.Frame(themes_frame, style="Dark.TFrame")
        header_row.pack(fill="x", pady=(0, 8))

        ttk.Label(
            header_row,
            textvariable=theme_title_var,
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 10, "bold")
        ).pack(side="left")

        def open_theme_manager_from_settings():
            self.open_theme_manager(parent=settings_window, on_themes_changed=lambda preferred=None: refresh_theme_catalog(preferred))

        ttk.Button(
            header_row,
            text="Themes",
            style="Dark.TButton",
            command=open_theme_manager_from_settings
        ).pack(side="right")

        selector_row = ttk.Frame(themes_frame, style="Dark.TFrame")
        selector_row.pack(fill="x", pady=(0, 8))

        ttk.Label(
            selector_row,
            text="Load Theme:",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        ).pack(side="left", padx=(0, 6))

        theme_selector = ttk.Combobox(
            selector_row,
            textvariable=theme_selector_var,
            state="readonly",
            width=28
        )
        theme_selector.pack(side="left", fill="x", expand=True)

        editor_box_height = 220
        editor_shell = tk.Frame(
            themes_frame,
            bg=self.BG_MID,
            relief="solid",
            borderwidth=1,
            height=editor_box_height,
        )
        editor_shell.pack(fill="x", expand=False, pady=(0, 8))
        editor_shell.pack_propagate(False)
        self.theme_editor_shell = editor_shell

        editor_area = tk.Frame(editor_shell, bg=self.BG_MID)
        editor_area.pack(fill="both", expand=True, padx=8, pady=8)
        self.theme_editor_area = editor_area

        editor_scrollbar = tk.Scrollbar(editor_area, orient="vertical")
        editor_scrollbar.pack(side="left", fill="y", padx=(0, 8))
        editor_scrollbar.config(width=10)

        editor_canvas = tk.Canvas(
            editor_area,
            bg=self.BG_MID,
            highlightthickness=0,
            yscrollcommand=editor_scrollbar.set,
            height=editor_box_height,
        )
        editor_canvas.pack(side="left", fill="both", expand=True)
        editor_scrollbar.config(command=editor_canvas.yview)
        self.theme_editor_canvas = editor_canvas

        editor_content = tk.Frame(editor_canvas, bg=self.BG_MID)
        editor_window = editor_canvas.create_window((0, 0), window=editor_content, anchor="nw")
        self.theme_editor_content = editor_content
        self.theme_editor_widgets = []

        style = ttk.Style()
        style.configure(
            "ThemeEditor.TCombobox",
            fieldbackground=self.BG_MID,
            background=self.BG_MID,
            foreground=self.FG_TEXT,
            arrowcolor=self.FG_TEXT,
            bordercolor=self.BG_LIGHT,
            lightcolor=self.BG_LIGHT,
            darkcolor=self.BG_LIGHT,
            relief="flat",
        )

        def _sync_editor_scrollregion(_event=None):
            editor_canvas.configure(scrollregion=editor_canvas.bbox("all"))

        def _sync_editor_width(event):
            editor_canvas.itemconfigure(editor_window, width=event.width)

        editor_content.bind("<Configure>", _sync_editor_scrollregion)
        editor_canvas.bind("<Configure>", _sync_editor_width)

        def _scroll_editor(event):
            editor_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        def _bind_mousewheel_recursive(widget):
            widget.bind("<MouseWheel>", _scroll_editor)
            for child in widget.winfo_children():
                _bind_mousewheel_recursive(child)

        def _refresh_editor_mousewheel_bindings(*_):
            _bind_mousewheel_recursive(editor_shell)

        editor_shell.bind("<Enter>", _refresh_editor_mousewheel_bindings)
        editor_shell.bind("<Leave>", lambda _event: editor_canvas.unbind_all("<MouseWheel>"))

        current_theme_config = self._load_current_theme_config()
        initial_theme_name = self.settings.get("selected_theme", "Dark")
        if current_theme_config:
            initial_theme_name = str(current_theme_config.get("source_theme", initial_theme_name) or initial_theme_name)

        theme_state = {
            "loaded_theme_name": initial_theme_name,
            "base_theme_name": initial_theme_name,
            "base_theme_data": None,
            "theme_is_dirty": False,
            "suspend_dirty_events": False,
        }

        color_keys = [
            ("bg_dark", "Background Dark"),
            ("bg_mid", "Background Mid"),
            ("bg_light", "Background Light"),
            ("fg_text", "Text Color"),
            ("fg_accent", "Accent Color"),
        ]

        color_vars = {key: tk.StringVar() for key, _ in color_keys}
        self.theme_color_vars = color_vars

        font_field_defaults = {
            "family": self.theme_manager.DEFAULT_THEME["fonts"]["family"],
            "size_base": str(self.theme_manager.DEFAULT_THEME["fonts"]["size_base"]),
        }
        font_vars = {key: tk.StringVar(value=value) for key, value in font_field_defaults.items()}

        def _validated_font_size(text_value, fallback):
            try:
                return max(6, min(36, int(str(text_value).strip())))
            except Exception:
                return fallback

        def get_editor_theme_data():
            data = self._deepcopy_theme_data(theme_state["base_theme_data"] or self.theme_manager.DEFAULT_THEME)
            colors = data.setdefault("colors", {})
            fonts = data.setdefault("fonts", {})

            for key, _label in color_keys:
                colors[key] = self._normalize_hex_color(color_vars[key].get(), self.theme_manager.DEFAULT_THEME["colors"].get(key, "#000000"))

            fonts["family"] = font_vars["family"].get().strip() or self.theme_manager.DEFAULT_THEME["fonts"]["family"]
            fonts["size_base"] = _validated_font_size(font_vars["size_base"].get(), 10)

            return data

        def theme_data_matches_base(current_data):
            base_data = theme_state["base_theme_data"] or self.theme_manager.DEFAULT_THEME
            current_colors = current_data.get("colors", {})
            base_colors = base_data.get("colors", {})
            current_fonts = current_data.get("fonts", {})
            base_fonts = base_data.get("fonts", {})
            for key, _label in color_keys:
                if self._normalize_hex_color(current_colors.get(key), "") != self._normalize_hex_color(base_colors.get(key), ""):
                    return False
            for key in ("family", "size_base"):
                if str(current_fonts.get(key, "")).strip() != str(base_fonts.get(key, "")).strip():
                    return False
            return True

        def update_theme_title_from_state(current_data=None):
            if theme_state["theme_is_dirty"]:
                set_theme_title("Custom")
                return
            loaded_name = theme_state["loaded_theme_name"] or "Dark"
            if current_data is not None and not theme_data_matches_base(current_data):
                theme_state["theme_is_dirty"] = True
                set_theme_title("Custom")
            else:
                set_theme_title(loaded_name)

        def set_status(text):
            theme_status_var.set(text)

        def mark_theme_dirty(*_):
            if theme_state["suspend_dirty_events"]:
                return
            current_data = get_editor_theme_data()
            theme_state["theme_is_dirty"] = not theme_data_matches_base(current_data)
            update_theme_title_from_state(current_data)
            set_status("Unsaved changes" if theme_state["theme_is_dirty"] else "")

        for var in color_vars.values():
            var.trace_add("write", mark_theme_dirty)
        for var in font_vars.values():
            var.trace_add("write", mark_theme_dirty)
        def apply_theme_to_editor(theme_name, theme_data_override=None):
            resolved = theme_name
            if resolved not in theme_catalog:
                for existing in theme_catalog.keys():
                    if existing.lower() == str(theme_name).lower():
                        resolved = existing
                        break
            if resolved not in theme_catalog:
                return

            base_theme_data = self.theme_manager.load_theme(resolved)
            merged = self.theme_manager._merge_with_defaults(theme_data_override or base_theme_data)
            theme_state["suspend_dirty_events"] = True
            theme_state["base_theme_name"] = resolved
            theme_state["base_theme_data"] = self._deepcopy_theme_data(base_theme_data)
            for key, _label in color_keys:
                color_vars[key].set(str(merged.get("colors", {}).get(key, self.theme_manager.DEFAULT_THEME["colors"].get(key, "#000000"))))
            fonts = merged.get("fonts", {})
            font_vars["family"].set(str(fonts.get("family", self.theme_manager.DEFAULT_THEME["fonts"]["family"])))
            font_vars["size_base"].set(str(int(fonts.get("size_base", 10))))
            theme_state["suspend_dirty_events"] = False

            theme_state["loaded_theme_name"] = resolved
            theme_state["theme_is_dirty"] = not theme_data_matches_base(merged)
            theme_selector_var.set(resolved)
            set_theme_title("Custom" if theme_state["theme_is_dirty"] else resolved)
            set_status("")

        def on_theme_selector_change(_event=None):
            selected_name = theme_selector_var.get().strip()
            if selected_name:
                apply_theme_to_editor(selected_name)

        theme_selector.bind("<<ComboboxSelected>>", on_theme_selector_change)

        def choose_theme_color(setting_key, label_text):
            current_color = color_vars[setting_key].get() or "#000000"
            picked = colorchooser.askcolor(initialcolor=current_color, title=f"Choose {label_text}", parent=settings_window)
            if picked and picked[1]:
                color_vars[setting_key].set(picked[1])

        color_section = tk.Frame(editor_content, bg=self.BG_MID)
        color_section.pack(fill="x", pady=(0, 8))
        self.theme_color_section = color_section

        color_header = tk.Label(color_section, text="Colors", bg=self.BG_MID, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 10, "bold"))
        color_header.pack(anchor="w", pady=(0, 4))
        self.theme_editor_widgets.append(color_header)

        color_rows = tk.Frame(color_section, bg=self.BG_MID)
        color_rows.pack(fill="x")
        self.theme_color_rows = color_rows

        color_swatches = {}
        self.theme_color_swatch_widgets = color_swatches

        def make_color_row(parent, key, label_text):
            row = tk.Frame(parent, bg=self.BG_MID)
            row.pack(fill="x", pady=2)

            label = tk.Label(row, text=label_text, bg=self.BG_MID, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 8), width=18, anchor="w")
            label.pack(side="left")
            self.theme_editor_widgets.append(label)
            self.theme_editor_widgets.append(row)

            entry = tk.Entry(
                row,
                textvariable=color_vars[key],
                width=12,
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                insertbackground=self.FG_TEXT,
                relief="solid",
                borderwidth=1,
                highlightthickness=1,
                highlightbackground=self.BG_LIGHT,
                highlightcolor=self.FG_ACCENT,
            )
            entry.pack(side="left", padx=(0, 6))
            self.theme_editor_widgets.append(entry)

            swatch = tk.Frame(row, bg="#000000", width=18, height=18, relief="solid", borderwidth=1)
            swatch.pack(side="left", padx=(0, 6))
            swatch.pack_propagate(False)
            color_swatches[key] = swatch

            def refresh_swatch(*_):
                value = color_vars[key].get().strip()
                if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                    swatch.config(bg=value)

            color_vars[key].trace_add("write", refresh_swatch)
            refresh_swatch()

            picker_btn = tk.Button(
                row,
                text="...",
                width=3,
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                relief="flat",
                activebackground=self.BG_LIGHT,
                activeforeground=self.FG_TEXT,
                command=lambda k=key, t=label_text: choose_theme_color(k, t),
            )
            picker_btn.pack(side="right")
            self.theme_editor_widgets.append(picker_btn)

        for key, label in color_keys:
            make_color_row(color_rows, key, label)

        font_section = tk.Frame(editor_content, bg=self.BG_MID)
        font_section.pack(fill="x", pady=(4, 8))
        self.theme_font_section = font_section

        font_header = tk.Label(font_section, text="Fonts", bg=self.BG_MID, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 10, "bold"))
        font_header.pack(anchor="w", pady=(0, 4))
        self.theme_editor_widgets.append(font_header)

        def font_row(parent, label_text, create_widget):
            row = tk.Frame(parent, bg=self.BG_MID)
            row.pack(fill="x", pady=2)
            self.theme_editor_widgets.append(row)
            label = tk.Label(row, text=label_text, bg=self.BG_MID, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 8), width=18, anchor="w")
            label.pack(side="left")
            self.theme_editor_widgets.append(label)
            widget = create_widget(row)
            widget.pack(side="right", fill="x", expand=True)
            self.theme_editor_widgets.append(widget)
            return widget

        font_families = sorted({family for family in tkfont.families() if family and not family.startswith("@")})
        if "Segoe UI" in font_families:
            font_families.insert(0, font_families.pop(font_families.index("Segoe UI")))

        font_family_combo = font_row(
            font_section,
            "Family",
            lambda parent: ttk.Combobox(
                parent,
                textvariable=font_vars["family"],
                values=font_families,
                state="readonly",
                width=24,
                style="ThemeEditor.TCombobox",
            ),
        )
        self.theme_family_combo = font_family_combo

        def make_size_entry(variable):
            return lambda parent: tk.Entry(
                parent,
                textvariable=variable,
                width=10,
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                insertbackground=self.FG_TEXT,
                relief="solid",
                borderwidth=1,
                highlightthickness=1,
                highlightbackground=self.BG_LIGHT,
                highlightcolor=self.FG_ACCENT,
            )

        font_row(font_section, "Base Size", make_size_entry(font_vars["size_base"]))

        def set_theme_from_editor():
            current_data = get_editor_theme_data()
            dirty = not theme_data_matches_base(current_data)
            theme_state["theme_is_dirty"] = dirty
            update_theme_title_from_state(current_data)
            self._save_current_theme_config(current_data, theme_state["base_theme_name"])
            self._apply_theme_data(current_data, selected_theme_name=("Custom" if dirty else theme_state["loaded_theme_name"]), persist_selection=True)
            set_status("Applied custom theme" if dirty else f"Applied {theme_state['loaded_theme_name']}")

        def save_theme_from_editor():
            current_data = get_editor_theme_data()
            suggested_name = theme_state["loaded_theme_name"]
            theme_name = simpledialog.askstring(
                "Save Theme",
                "Theme name:",
                initialvalue=suggested_name,
                parent=settings_window,
            )
            if theme_name is None:
                return

            theme_name = str(theme_name).strip()
            if not theme_name:
                messagebox.showwarning("Save Theme", "Theme name cannot be empty.", parent=settings_window)
                return

            safe_theme_name = re.sub(r'[<>:"/\\|?*]', "_", theme_name).strip()
            if not safe_theme_name:
                messagebox.showwarning("Save Theme", "Theme name contains only invalid filename characters.", parent=settings_window)
                return

            suggested_author = ""
            suggested_description = ""
            if suggested_name in self.theme_manager.get_available_themes():
                existing_theme = self.theme_manager.load_theme(suggested_name)
                suggested_author = existing_theme.get("metadata", {}).get("author", "")
                suggested_description = existing_theme.get("metadata", {}).get("description", "")

            author_name = simpledialog.askstring(
                "Save Theme",
                "Author:",
                initialvalue=suggested_author,
                parent=settings_window,
            )
            if author_name is None:
                return
            author_name = str(author_name).strip()
            if not author_name:
                messagebox.showwarning("Save Theme", "Author cannot be empty.", parent=settings_window)
                return

            description_text = simpledialog.askstring(
                "Save Theme",
                "Description:",
                initialvalue=suggested_description,
                parent=settings_window,
            )
            if description_text is None:
                return
            description_text = str(description_text).strip()
            if not description_text:
                messagebox.showwarning("Save Theme", "Description cannot be empty.", parent=settings_window)
                return

            available = self.theme_manager.get_available_themes()
            if safe_theme_name in available and available[safe_theme_name].get("builtin", False):
                messagebox.showwarning("Save Theme", "Cannot overwrite a builtin theme. Choose another name.", parent=settings_window)
                return

            if safe_theme_name in available and not messagebox.askyesno(
                "Save Theme",
                f"Overwrite existing custom theme '{safe_theme_name}'?",
                parent=settings_window,
            ):
                return

            save_data = self._deepcopy_theme_data(current_data)
            metadata = save_data.setdefault("metadata", {})
            metadata["name"] = safe_theme_name
            metadata["author"] = author_name
            metadata["description"] = description_text

            if not self.theme_manager.save_theme(safe_theme_name, save_data, is_custom=True):
                messagebox.showerror("Save Theme", "Failed to save theme.", parent=settings_window)
                return

            self._save_current_theme_config(save_data, safe_theme_name)
            theme_state["base_theme_name"] = safe_theme_name
            theme_state["loaded_theme_name"] = safe_theme_name
            theme_state["theme_is_dirty"] = False
            refresh_theme_catalog(safe_theme_name)
            apply_theme_to_editor(safe_theme_name, save_data)
            set_theme_title(safe_theme_name)
            set_status("Theme saved")
            messagebox.showinfo("Save Theme", f"Saved theme '{safe_theme_name}'.", parent=settings_window)

        button_row = ttk.Frame(themes_frame, style="Dark.TFrame")
        button_row.pack(fill="x")

        ttk.Button(button_row, text="Set Theme", style="Dark.TButton", command=set_theme_from_editor).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(button_row, text="Save Theme", style="Dark.TButton", command=save_theme_from_editor).pack(side="left", fill="x", expand=True, padx=(4, 0))

        refresh_theme_catalog(self.settings.get("selected_theme", "Dark"))
        if current_theme_config:
            apply_theme_to_editor(theme_state["loaded_theme_name"], current_theme_config)
        else:
            apply_theme_to_editor(theme_state["loaded_theme_name"])
        self._theme_editor_save_current_config = lambda: self._save_current_theme_config(get_editor_theme_data(), theme_state["base_theme_name"])
        if theme_state["theme_is_dirty"]:
            set_theme_title("Custom")
        else:
            set_theme_title(theme_state["loaded_theme_name"])
        
        dc_frame = ttk.Frame(discord_tab, style="Dark.TFrame")
        dc_frame.pack(fill="both", expand=True, padx=20, pady=15)

        webhook_cfg = self.settings.setdefault("discord_webhook", self._default_discord_integration_settings("webhook"))

        ttk.Label(
            dc_frame, text="Discord Webhook",
            style="Dark.TLabel", font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w", pady=(0, 2))

        ttk.Label(
            dc_frame, text="Send log events to Discord via webhook.",
            style="Dark.TLabel", font=(self.FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(0, 10))

        sep = ttk.Frame(dc_frame, style="Dark.TFrame", height=1)
        sep.pack(fill="x", pady=(0, 12))
        sep.configure(relief="solid", borderwidth=1)

        dc_enabled_var = tk.BooleanVar(value=webhook_cfg.get("enabled", False))
        dc_url_var = tk.StringVar(value=webhook_cfg.get("url", ""))
        dc_ping_var = tk.BooleanVar(value=webhook_cfg.get("enable_ping", False))
        dc_ping_id_var = tk.StringVar(value=webhook_cfg.get("ping_user_id", ""))
        dc_ping_err_var = tk.BooleanVar(value=webhook_cfg.get("ping_on_error", True))
        dc_log_all_var = tk.BooleanVar(value=webhook_cfg.get("log_everything", False))
        dc_log_err_var = tk.BooleanVar(value=webhook_cfg.get("log_errors", True))
        dc_log_ok_var = tk.BooleanVar(value=webhook_cfg.get("log_success", True))
        dc_log_warn_var = tk.BooleanVar(value=webhook_cfg.get("log_warnings", True))
        dc_log_info_var = tk.BooleanVar(value=webhook_cfg.get("log_info", False))
        dc_log_rejoin_var = tk.BooleanVar(value=webhook_cfg.get("log_auto_rejoin", True))
        dc_log_rejoin_console_var = tk.BooleanVar(value=webhook_cfg.get("log_auto_rejoin_console", False))
        dc_screenshot_interval_var = tk.StringVar(value=str(webhook_cfg.get("screenshot_interval_minutes", 60)))
        dc_screenshot_enabled_var = tk.BooleanVar(value=webhook_cfg.get("screenshot_enabled", False))

        def _dc_save():
            webhook_cfg["enabled"] = dc_enabled_var.get()
            webhook_cfg["url"] = dc_url_var.get().strip()
            webhook_cfg["enable_ping"] = dc_ping_var.get()
            webhook_cfg["ping_user_id"] = dc_ping_id_var.get().strip()
            webhook_cfg["ping_on_error"] = dc_ping_err_var.get()
            webhook_cfg["log_everything"] = dc_log_all_var.get()
            webhook_cfg["log_errors"] = dc_log_err_var.get()
            webhook_cfg["log_success"] = dc_log_ok_var.get()
            webhook_cfg["log_warnings"] = dc_log_warn_var.get()
            webhook_cfg["log_info"] = dc_log_info_var.get()
            webhook_cfg["log_auto_rejoin"] = dc_log_rejoin_var.get()
            webhook_cfg["log_auto_rejoin_console"] = dc_log_rejoin_console_var.get()
            try:
                webhook_cfg["screenshot_interval_minutes"] = max(1, int(dc_screenshot_interval_var.get()))
            except (ValueError, TypeError):
                webhook_cfg["screenshot_interval_minutes"] = 60
            webhook_cfg["screenshot_enabled"] = dc_screenshot_enabled_var.get()

            self.settings["discord_webhook"] = webhook_cfg
            self.save_settings()

        def _dc_toggle_fields(*_, _send_connect=True):
            now_enabled = dc_enabled_var.get()
            state = "normal" if now_enabled else "disabled"
            for w in _dc_dependent_widgets:
                try:
                    w.config(state=state)
                except Exception:
                    pass
            was_enabled = webhook_cfg.get("enabled", False)
            _dc_save()
            if _send_connect and now_enabled and not was_enabled and dc_url_var.get().strip():
                try:
                    self._send_webhook_embed(dc_url_var.get().strip(), "Connected to Discord!", "Roblox Account Manager is now connected.", 0x2ECC71)
                except Exception:
                    pass
            if dc_url_var.get().strip() and webhook_cfg.get("screenshot_enabled"):
                self._start_global_screenshot_loop()
            else:
                self._stop_global_screenshot_loop()

        dc_enable_check = ttk.Checkbutton(
            dc_frame, text="Enable Webhook", variable=dc_enabled_var,
            style="Dark.TCheckbutton", command=_dc_toggle_fields
        )
        dc_enable_check.pack(anchor="w", pady=(0, 8))

        url_row = ttk.Frame(dc_frame, style="Dark.TFrame")
        url_row.pack(fill="x", pady=(0, 6))
        dc_url_label = ttk.Label(url_row, text="Webhook URL:", style="Dark.TLabel",
                  font=(self.FONT_FAMILY, 9))
        dc_url_label.pack(anchor="w", pady=(0, 2))
        dc_url_entry = ttk.Entry(url_row, textvariable=dc_url_var, style="Dark.TEntry")
        dc_url_entry.pack(fill="x", ipady=3)

        ping_row1 = ttk.Frame(dc_frame, style="Dark.TFrame")
        ping_row1.pack(fill="x", pady=(4, 0))

        dc_ping_id_entry = ttk.Entry(ping_row1, textvariable=dc_ping_id_var,
                                     width=20, style="Dark.TEntry")

        def _dc_ping_toggle(*_):
            dc_ping_id_entry.config(state="normal" if dc_ping_var.get() else "disabled")
            _dc_save()

        ttk.Checkbutton(
            ping_row1, text="Ping user on alerts:", variable=dc_ping_var,
            style="Dark.TCheckbutton", command=_dc_ping_toggle
        ).pack(side="left")
        dc_ping_id_entry.pack(side="left", padx=(6, 0))
        dc_ping_id_entry.config(state="normal" if dc_ping_var.get() else "disabled")

        ping_row2 = ttk.Frame(dc_frame, style="Dark.TFrame")
        ping_row2.pack(fill="x", pady=(2, 6))
        ttk.Checkbutton(
            ping_row2, text="Ping only on [ERROR]", variable=dc_ping_err_var,
            style="Dark.TCheckbutton", command=_dc_save
        ).pack(anchor="w", padx=(2, 0))

        ss_row = ttk.Frame(dc_frame, style="Dark.TFrame")
        ss_row.pack(fill="x", pady=(2, 6))
        dc_ss_entry = ttk.Entry(ss_row, textvariable=dc_screenshot_interval_var, width=5, style="Dark.TEntry")

        def _dc_ss_toggle(*_):
            dc_ss_entry.config(state="normal" if dc_screenshot_enabled_var.get() else "disabled")
            _dc_save()
            try:
                cfg = self.settings.get("discord_webhook", {})
                if cfg.get("enabled") and cfg.get("screenshot_enabled"):
                    self._start_global_screenshot_loop()
                else:
                    self._stop_global_screenshot_loop()
            except Exception:
                self._stop_global_screenshot_loop()

        ttk.Checkbutton(
            ss_row, text="Screenshot every:", variable=dc_screenshot_enabled_var,
            style="Dark.TCheckbutton", command=_dc_ss_toggle
        ).pack(side="left")
        dc_ss_entry.pack(side="left", padx=(6, 4))
        dc_ss_entry.config(state="normal" if dc_screenshot_enabled_var.get() else "disabled")
        ttk.Label(ss_row, text="min", style="Dark.TLabel",
                  font=(self.FONT_FAMILY, 9)).pack(side="left")
        dc_ss_entry.bind("<FocusOut>", lambda e: _dc_save())
        dc_ss_entry.bind("<Return>", lambda e: _dc_save())

        btn_row = ttk.Frame(dc_frame, style="Dark.TFrame")
        btn_row.pack(fill="x", pady=(12, 0))

        def _open_log_filters():
            _dc_save()
            fw = tk.Toplevel(settings_window)
            self.apply_window_icon(fw)
            fw.title("Log Filters")
            fw.configure(bg=self.BG_DARK)
            fw.resizable(False, False)
            fw.transient(settings_window)
            fw.focus_force()
            settings_window.update_idletasks()
            fw.update_idletasks()
            fx = settings_window.winfo_x() + (settings_window.winfo_width() - 260) // 2
            fy = settings_window.winfo_y() + (settings_window.winfo_height() - 280) // 2
            fw.geometry(f"260x300+{fx}+{fy}")
            if self.settings.get("enable_topmost", False):
                fw.attributes("-topmost", True)

            ff = ttk.Frame(fw, style="Dark.TFrame")
            ff.pack(fill="both", expand=True, padx=18, pady=15)

            ttk.Label(ff, text="Log Filters", style="Dark.TLabel",
                      font=(self.FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(0, 8))

            def _chk(text, var):
                cb = ttk.Checkbutton(
                    ff, text=text, variable=var,
                    style="Dark.TCheckbutton", command=_dc_save
                )
                cb.pack(anchor="w", pady=2)
                return cb

            def _toggle_log_all(*_):
                st = "disabled" if dc_log_all_var.get() else "normal"
                for w in _sub_checks:
                    try:
                        w.config(state=st)
                    except Exception:
                        pass
                _dc_save()

            ttk.Checkbutton(
                ff, text="Log Everything (override all)", variable=dc_log_all_var,
                style="Dark.TCheckbutton", command=_toggle_log_all
            ).pack(anchor="w", pady=2)

            sep_f = ttk.Frame(ff, style="Dark.TFrame", height=1)
            sep_f.pack(fill="x", pady=(4, 6))
            sep_f.configure(relief="solid", borderwidth=1)

            _sub_checks = [
                _chk("Log [ERROR]",                    dc_log_err_var),
                _chk("Log [SUCCESS]",                  dc_log_ok_var),
                _chk("Log [WARNING]",                  dc_log_warn_var),
                _chk("Log [INFO]",                     dc_log_info_var),
                _chk("Log Auto-Rejoin events",         dc_log_rejoin_var),
                _chk("Log Auto-Rejoin console",        dc_log_rejoin_console_var),
            ]
            _toggle_log_all()

            ttk.Button(ff, text="Close", style="Dark.TButton",
                       command=fw.destroy).pack(fill="x", pady=(10, 0))

        def _dc_test():
            test_target = dc_url_var.get().strip()
            if not test_target:
                messagebox.showwarning("Missing Target", "Enter a webhook URL first.", parent=settings_window)
                return

            _dc_save()
            _ping = dc_ping_id_var.get().strip() if dc_ping_var.get() else None
            try:
                self._send_webhook_embed(test_target, "Discord Test", "Discord integration is working correctly!", 0x2ECC71, ping_user_id=_ping)
            except Exception:
                pass

        def _open_webhook_filters():
            fw = tk.Toplevel(settings_window)
            self.apply_window_icon(fw)
            fw.title("Webhook Filters")
            fw.configure(bg=self.BG_DARK)
            fw.resizable(False, False)
            fw.transient(settings_window)
            fw.focus_force()
            settings_window.update_idletasks()
            fx = settings_window.winfo_x() + (settings_window.winfo_width() - 320) // 2
            fy = settings_window.winfo_y() + (settings_window.winfo_height() - 380) // 2
            fw.geometry(f"320x380+{fx}+{fy}")
            if self.settings.get("enable_topmost", False):
                fw.attributes("-topmost", True)

            frm = ttk.Frame(fw, style="Dark.TFrame")
            frm.pack(fill="both", expand=True, padx=16, pady=14)

            ttk.Label(frm, text="Webhook Filters", style="Dark.TLabel",
                      font=(self.FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(0, 2))
            ttk.Label(frm, text="Messages containing these substrings won't be \nforwarded to Discord.\n[ERROR] messages are never filtered.",
                      style="Dark.TLabel", font=(self.FONT_FAMILY, 8),
                      justify="left").pack(anchor="w", pady=(0, 8))

            list_frame = ttk.Frame(frm, style="Dark.TFrame")
            list_frame.pack(fill="both", expand=True)

            lb = tk.Listbox(list_frame, bg=self.BG_MID, fg=self.FG_TEXT,
                            selectbackground=self.FG_ACCENT, highlightthickness=0,
                            border=0, font=(self.FONT_FAMILY, 9))
            lb.pack(side="left", fill="both", expand=True)
            sb = ttk.Scrollbar(list_frame, command=lb.yview)
            sb.pack(side="right", fill="y")
            lb.config(yscrollcommand=sb.set)

            filters = self.settings.setdefault("console_filters", [
                "Got authentication ticket!",
                "You are on the latest version",
            ])
            for f in filters:
                lb.insert(tk.END, f)

            add_row = ttk.Frame(frm, style="Dark.TFrame")
            add_row.pack(fill="x", pady=(8, 4))
            entry_var = tk.StringVar()
            entry = ttk.Entry(add_row, textvariable=entry_var, style="Dark.TEntry")
            entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

            def add_filter(e=None):
                val = entry_var.get().strip()
                if val and val not in filters:
                    filters.append(val)
                    lb.insert(tk.END, val)
                    self.save_settings()
                entry_var.set("")

            def remove_filter():
                sel = lb.curselection()
                if not sel:
                    return
                idx = sel[0]
                lb.delete(idx)
                del filters[idx]
                self.save_settings()

            entry.bind("<Return>", add_filter)
            ttk.Button(add_row, text="Add", style="Dark.TButton",
                       command=add_filter).pack(side="left")

            wf_btn_row = ttk.Frame(frm, style="Dark.TFrame")
            wf_btn_row.pack(fill="x", pady=(4, 0))
            ttk.Button(wf_btn_row, text="Remove Selected", style="Dark.TButton",
                       command=remove_filter).pack(side="left", fill="x", expand=True, padx=(0, 4))
            ttk.Button(wf_btn_row, text="Close", style="Dark.TButton",
                       command=fw.destroy).pack(side="left", fill="x", expand=True)

        ttk.Button(btn_row, text="Log Filters", style="Dark.TButton",
                   command=_open_log_filters).pack(side="left", fill="x", expand=True, padx=(0, 4))
        dc_test_btn = ttk.Button(btn_row, text="Test Webhook", style="Dark.TButton",
            command=_dc_test)
        dc_test_btn.pack(side="left", fill="x", expand=True)

        btn_row2 = ttk.Frame(dc_frame, style="Dark.TFrame")
        btn_row2.pack(fill="x", pady=(4, 0))
        dc_filters_btn = ttk.Button(btn_row2, text="Webhook Filters", style="Dark.TButton",
               command=_open_webhook_filters)
        dc_filters_btn.pack(fill="x")

        bot_sep = ttk.Frame(dc_frame, style="Dark.TFrame", height=1)
        bot_sep.pack(fill="x", pady=(12, 12))
        bot_sep.configure(relief="solid", borderwidth=1)

        ttk.Label(
            dc_frame, text="Embedded Discord Bot",
            style="Dark.TLabel", font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w", pady=(0, 2))

        ttk.Label(
            dc_frame, text="Listen for remote chat commands from Discord.",
            style="Dark.TLabel", font=(self.FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(0, 10))

        bot_enabled_var = tk.BooleanVar(value=self.settings.get("discord_bot_enabled", False))
        bot_token_var = tk.StringVar(value=self.settings.get("discord_bot_token", ""))
        bot_auth_id_var = tk.StringVar(value=self.settings.get("discord_bot_authorized_id", ""))

        def _bot_save():
            self.settings["discord_bot_enabled"] = bot_enabled_var.get()
            self.settings["discord_bot_token"] = bot_token_var.get().strip()
            self.settings["discord_bot_authorized_id"] = bot_auth_id_var.get().strip()
            self.save_settings()
            if bot_enabled_var.get():
                self.start_discord_bot()
            else:
                self.stop_discord_bot()

        bot_row1 = ttk.Frame(dc_frame, style="Dark.TFrame")
        bot_row1.pack(fill="x", pady=(2, 4))
        
        bot_enable_check = ttk.Checkbutton(
            bot_row1, text="Enable Embedded Bot", variable=bot_enabled_var,
            style="Dark.TCheckbutton", command=_bot_save
        )
        bot_enable_check.pack(side="left")

        bot_row2 = ttk.Frame(dc_frame, style="Dark.TFrame")
        bot_row2.pack(fill="x", pady=(2, 4))
        ttk.Label(bot_row2, text="Token:", style="Dark.TLabel", font=(self.FONT_FAMILY, 9)).pack(side="left")
        bot_token_entry = ttk.Entry(bot_row2, textvariable=bot_token_var, width=20, show="*", style="Dark.TEntry")
        bot_token_entry.pack(side="left", padx=(6, 12))
        bot_token_entry.bind("<FocusOut>", lambda e: _bot_save())
        bot_token_entry.bind("<Return>", lambda e: _bot_save())

        ttk.Label(bot_row2, text="Authorized ID:", style="Dark.TLabel", font=(self.FONT_FAMILY, 9)).pack(side="left")
        bot_auth_entry = ttk.Entry(bot_row2, textvariable=bot_auth_id_var, width=15, style="Dark.TEntry")
        bot_auth_entry.pack(side="left", padx=(6, 0))
        bot_auth_entry.bind("<FocusOut>", lambda e: _bot_save())
        bot_auth_entry.bind("<Return>", lambda e: _bot_save())

        sep2 = ttk.Frame(dc_frame, style="Dark.TFrame", height=1)
        sep2.pack(fill="x", pady=(15, 12))
        sep2.configure(relief="solid", borderwidth=1)

        ttk.Label(
            dc_frame, text="Discord Rich Presence (RPC)",
            style="Dark.TLabel", font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w", pady=(0, 2))

        ttk.Label(
            dc_frame, text="Configure your custom Discord RPC presence and client application ID.",
            style="Dark.TLabel", font=(self.FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(0, 10))

        rpc_enabled_var = tk.BooleanVar(value=self.settings.get("discord_rpc_enabled", True))
        rpc_client_id_var = tk.StringVar(value=self.settings.get("discord_rpc_client_id", "1240954157790367804"))

        def _rpc_save():
            self.settings["discord_rpc_enabled"] = rpc_enabled_var.get()
            cid = rpc_client_id_var.get().strip()
            if not cid:
                cid = "1240954157790367804"
                rpc_client_id_var.set(cid)
            self.settings["discord_rpc_client_id"] = cid
            self.save_settings()
            
            if hasattr(self, 'discord_rpc'):
                try:
                    self.discord_rpc.close()
                except:
                    pass
            if rpc_enabled_var.get():
                try:
                    from utils.discord_rpc import DiscordRPC
                    self.discord_rpc = DiscordRPC(client_id=cid)
                    
                    def rpc_worker():
                        import psutil
                        time.sleep(1)
                        while True:
                            if not self.settings.get("discord_rpc_enabled", True):
                                break
                            try:
                                active_users = []
                                if hasattr(self, '_active_instance_usernames'):
                                    active_users = list(self._active_instance_usernames)
                                cpu_val = psutil.cpu_percent()
                                mem_val = psutil.virtual_memory().percent
                                if active_users:
                                    raw_user = active_users[0]
                                    display_user = raw_user
                                    for key in list(self.manager.accounts.keys()):
                                        if key.lower() == raw_user.lower():
                                            display_user = key
                                            break
                                    self.discord_rpc.set_activity(
                                        details=f"🎮 Running: {len(active_users)} client(s)",
                                        state=f"💻 CPU: {cpu_val:.0f}% | RAM: {mem_val:.0f}%",
                                        large_image="https://raw.githubusercontent.com/ic3w0lf22/Roblox-Account-Manager/master/RBX%20Alt%20Manager/Resources/Roblox%20Account%20Manager.png",
                                        large_text="Account Manager by Nerd",
                                        small_image="https://images.rbxcdn.com/97800c6d7bb00b55502c34db97837012.png",
                                        small_text="Roblox active"
                                    )
                                else:
                                    total_accts = len(self.manager.accounts)
                                    self.discord_rpc.set_activity(
                                        details=f"📁 Idle | Managing {total_accts} account(s)",
                                        state=f"💻 CPU: {cpu_val:.0f}% | RAM: {mem_val:.0f}%",
                                        large_image="https://raw.githubusercontent.com/ic3w0lf22/Roblox-Account-Manager/master/RBX%20Alt%20Manager/Resources/Roblox%20Account%20Manager.png",
                                        large_text="Account Manager by Nerd"
                                    )
                            except Exception:
                                pass
                            time.sleep(10)
                    threading.Thread(target=rpc_worker, daemon=True).start()
                except Exception as e:
                    print(f"[Discord RPC Error] Failed to restart RPC: {e}")

        rpc_row1 = ttk.Frame(dc_frame, style="Dark.TFrame")
        rpc_row1.pack(fill="x", pady=(2, 4))
        
        rpc_enable_check = ttk.Checkbutton(
            rpc_row1, text="Enable Discord RPC Presence", variable=rpc_enabled_var,
            style="Dark.TCheckbutton", command=_rpc_save
        )
        rpc_enable_check.pack(side="left")

        rpc_row2 = ttk.Frame(dc_frame, style="Dark.TFrame")
        rpc_row2.pack(fill="x", pady=(2, 4))
        ttk.Label(rpc_row2, text="Application Client ID:", style="Dark.TLabel", font=(self.FONT_FAMILY, 9)).pack(side="left")
        rpc_client_entry = ttk.Entry(rpc_row2, textvariable=rpc_client_id_var, width=30, style="Dark.TEntry")
        rpc_client_entry.pack(side="left", padx=(6, 12))
        rpc_client_entry.bind("<FocusOut>", lambda e: _rpc_save())
        rpc_client_entry.bind("<Return>", lambda e: _rpc_save())

        _dc_dependent_widgets = [dc_url_entry, dc_ping_id_entry, dc_ss_entry]
        _dc_toggle_fields(_send_connect=False)

        tool_frame = ttk.Frame(tool_tab, style="Dark.TFrame")
        tool_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        ttk.Label(
            tool_frame,
            text="Tools",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 15))
        
        def wipe_data():
            """Wipe data"""
            if not messagebox.askyesno("Confirm Wipe Data", "Are you sure you want to wipe ALL data?\n\nThis action cannot be undone!"):
                return
            
            encryption_method = self.manager.get_encryption_method()
            
            if encryption_method == "password":
                password_window = tk.Toplevel(settings_window)
                self.apply_window_icon(password_window)
                password_window.title("Enter Password")
                password_window.geometry("350x150")
                password_window.configure(bg=self.BG_DARK)
                password_window.resizable(False, False)
                password_window.transient(settings_window)
                password_window.grab_set()
                
                settings_window.update_idletasks()
                x = settings_window.winfo_x() + (settings_window.winfo_width() - 350) // 2
                y = settings_window.winfo_y() + (settings_window.winfo_height() - 150) // 2
                password_window.geometry(f"350x150+{x}+{y}")
                
                main_frame = ttk.Frame(password_window, style="Dark.TFrame")
                main_frame.pack(fill="both", expand=True, padx=20, pady=20)
                
                ttk.Label(main_frame, text="Enter your password:", style="Dark.TLabel").pack(anchor="w", pady=(0, 10))
                
                password_entry = ttk.Entry(main_frame, style="Dark.TEntry", show="*")
                password_entry.pack(fill="x", pady=(0, 15))
                password_entry.focus_set()
                
                def verify_and_wipe():
                    password = password_entry.get()
                    if not password:
                        messagebox.showwarning("Missing Password", "Please enter your password.")
                        return
                    
                    if self.manager.verify_password(password):
                        password_window.destroy()
                        if messagebox.askyesno("Final Confirmation", "This will permanently delete ALL data. Continue?"):
                            settings_window.destroy()
                            self.manager.wipe_all_data()
                            messagebox.showinfo("Success", "All data has been wiped!")
                            settings_window.quit()
                    else:
                        messagebox.showerror("Invalid Password", "Password is incorrect.")
                
                btn_frame = ttk.Frame(main_frame, style="Dark.TFrame")
                btn_frame.pack(fill="x")
                
                ttk.Button(btn_frame, text="Verify", style="Dark.TButton", command=verify_and_wipe).pack(side="left", fill="x", expand=True, padx=(0, 5))
                ttk.Button(btn_frame, text="Cancel", style="Dark.TButton", command=password_window.destroy).pack(side="left", fill="x", expand=True, padx=(5, 0))
            else:
                if messagebox.askyesno("Final Confirmation", "This will permanently delete ALL data. Continue?"):
                    settings_window.destroy()
                    self.manager.wipe_all_data()
                    messagebox.showinfo("Success", "All data has been wiped!")
                    settings_window.quit()
        
        
        def switch_encryption_method():
            """Switch encryption method"""
            current_method = self.manager.get_encryption_method()
            
            if current_method == "password":
                password_window = tk.Toplevel(settings_window)
                self.apply_window_icon(password_window)
                password_window.title("Verify Password")
                password_window.geometry("350x150")
                password_window.configure(bg=self.BG_DARK)
                password_window.resizable(False, False)
                password_window.transient(settings_window)
                password_window.grab_set()
                
                settings_window.update_idletasks()
                x = settings_window.winfo_x() + (settings_window.winfo_width() - 350) // 2
                y = settings_window.winfo_y() + (settings_window.winfo_height() - 150) // 2
                password_window.geometry(f"350x150+{x}+{y}")
                
                pwd_frame = ttk.Frame(password_window, style="Dark.TFrame")
                pwd_frame.pack(fill="both", expand=True, padx=20, pady=20)
                
                ttk.Label(pwd_frame, text="Enter your password to continue:", style="Dark.TLabel").pack(anchor="w", pady=(0, 10))
                
                password_entry = ttk.Entry(pwd_frame, style="Dark.TEntry", show="*")
                password_entry.pack(fill="x", pady=(0, 15))
                password_entry.focus_set()
                
                def verify_and_proceed():
                    password = password_entry.get()
                    if not password:
                        messagebox.showwarning("Missing Password", "Please enter your password.")
                        return
                    
                    if self.manager.verify_password(password):
                        password_window.destroy()
                        settings_window.destroy()
                        self._run_encryption_switch()
                    else:
                        messagebox.showerror("Invalid Password", "Password is incorrect.")
                
                pwd_btn_frame = ttk.Frame(pwd_frame, style="Dark.TFrame")
                pwd_btn_frame.pack(fill="x")
                
                ttk.Button(pwd_btn_frame, text="Verify", style="Dark.TButton", command=verify_and_proceed).pack(side="left", fill="x", expand=True, padx=(0, 5))
                ttk.Button(pwd_btn_frame, text="Cancel", style="Dark.TButton", command=password_window.destroy).pack(side="left", fill="x", expand=True, padx=(5, 0))
            else:
                settings_window.destroy()
                self._run_encryption_switch()
        
        ttk.Button(
            tool_frame,
            text="Switch Encryption Method",
            style="Dark.TButton",
            command=switch_encryption_method
        ).pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            tool_frame,
            text="Browser Engine",
            style="Dark.TButton",
            command=self.open_browser_engine_window
        ).pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            tool_frame,
            text="Roblox Settings",
            style="Dark.TButton",
            command=self.open_roblox_settings_window
        ).pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            tool_frame,
            text="Active Instances",
            style="Dark.TButton",
            command=self.open_active_instances_window
        ).pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            tool_frame,
            text="Roblox Version",
            style="Dark.TButton",
            command=self.open_roblox_version_window
        ).pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            tool_frame,
            text="Wipe Data",
            style="Dark.TButton",
            command=wipe_data
        ).pack(side="bottom", fill="x", pady=(10, 0))
    
    def start_instances_monitoring(self):
        """Start background monitoring of active Roblox instances"""
        if self.instances_monitor_thread and self.instances_monitor_thread.is_alive():
            return
        
        self.instances_monitor_stop.clear()
        self.instances_monitor_thread = threading.Thread(target=self._instances_monitor_worker, daemon=True)
        self.instances_monitor_thread.start()
        print("[INFO] Active Instances background monitoring started")
    
    def stop_instances_monitoring(self):
        """Stop background monitoring of active Roblox instances"""
        if self.instances_monitor_thread:
            self.instances_monitor_stop.set()
            self.instances_monitor_thread = None
            self.instances_data.clear()
            self.instances_pids.clear()
            print("[INFO] Active Instances background monitoring stopped")
    
    def _instances_monitor_worker(self):
        last_memory_refresh = 0.0
        poll_interval_seconds = 4
        failed_retry_delay_seconds = 8
        persistent_procs = {}

        while not self.instances_monitor_stop.is_set():
            try:
                new_pids = set()
                processes = []
                pid_to_proc = {}
                
                for proc in psutil.process_iter(['pid', 'name', 'create_time', 'memory_info']):
                    try:
                        if proc.info['name'].lower() == 'robloxplayerbeta.exe':
                            pid = proc.info['pid']
                            if self._is_valid_roblox_game_client(pid, 'robloxplayerbeta.exe'):
                                new_pids.add(pid)
                                if pid not in persistent_procs:
                                    persistent_procs[pid] = proc
                                processes.append(persistent_procs[pid])
                                pid_to_proc[pid] = persistent_procs[pid]
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                active_pids = set(new_pids)
                for cached_pid in list(persistent_procs.keys()):
                    if cached_pid not in active_pids:
                        del persistent_procs[cached_pid]
                        if hasattr(self, 'proc_cpu_stats') and cached_pid in self.proc_cpu_stats:
                            del self.proc_cpu_stats[cached_pid]

                current_time = time.time()
                for pid in list(self.instances_failed_pids.keys()):
                    if pid not in new_pids:
                        del self.instances_failed_pids[pid]
                
                if new_pids != self.instances_pids:
                    print(f"[INFO] Active Instances: PID change detected. Old: {self.instances_pids}, New: {new_pids}")
                    self.instances_pids = new_pids.copy()

                    old_data_by_pid = {entry['pid']: entry for entry in self.instances_data}
                    new_data = []

                    for proc in processes:
                        pid = proc.info['pid']
                        
                        try:
                            memory_mb = proc.info['memory_info'].rss / 1024 / 1024
                            create_time = proc.info['create_time']
                        except:
                            memory_mb = 0
                            create_time = 0

                        prev = old_data_by_pid.get(pid, {})
                        new_data.append({
                            "pid": pid,
                            "user_id": prev.get("user_id"),
                            "username": prev.get("username"),
                            "avatar_url": prev.get("avatar_url"),
                            "create_time": create_time,
                            "memory_mb": memory_mb,
                            "cpu_percent": prev.get("cpu_percent", 0.0),
                        })

                    self.instances_data = new_data
                    self.instances_data_updated = True
                    self.root.after(0, self.refresh_accounts)

                if current_time - last_memory_refresh >= poll_interval_seconds:
                    last_memory_refresh = current_time
                    if not hasattr(self, 'proc_cpu_stats'):
                        self.proc_cpu_stats = {}
                    for entry in self.instances_data:
                        try:
                            proc = persistent_procs.get(entry["pid"])
                            if not proc:
                                proc = psutil.Process(entry["pid"])
                                persistent_procs[entry["pid"]] = proc
                            entry["memory_mb"] = proc.memory_info().rss / 1024 / 1024
                            
                            cpu_times = proc.cpu_times()
                            total_proc_time = cpu_times.user + cpu_times.system
                            stats_key = entry["pid"]
                            if stats_key in self.proc_cpu_stats:
                                prev_proc_time, prev_wall_time = self.proc_cpu_stats[stats_key]
                                delta_proc = total_proc_time - prev_proc_time
                                delta_wall = current_time - prev_wall_time
                                if delta_wall > 0:
                                    cpu_percent = (delta_proc / delta_wall) * 100.0 / psutil.cpu_count()
                                    entry["cpu_percent"] = max(0.0, min(100.0, cpu_percent))
                                else:
                                    entry["cpu_percent"] = 0.0
                            else:
                                entry["cpu_percent"] = 0.0
                            self.proc_cpu_stats[stats_key] = (total_proc_time, current_time)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                unresolved_entry = None
                for entry in self.instances_data:
                    if entry.get("user_id"):
                        continue
                    pid = entry.get("pid")
                    failed_data = self.instances_failed_pids.get(pid)
                    if failed_data and (current_time - failed_data[0] < failed_retry_delay_seconds):
                        continue
                    unresolved_entry = entry
                    break

                if unresolved_entry:
                    pid = unresolved_entry["pid"]
                    used_logs = set()
                    user_id, _ = self._get_user_id_from_pid(pid, used_logs)

                    if user_id:
                        username = None
                        avatar_url = None

                        if user_id in self.instances_cache["user_id_to_username"]:
                            username = self.instances_cache["user_id_to_username"][user_id]
                        else:
                            for account in list(self.manager.accounts):
                                stored_uid = self.manager.accounts[account].get("user_id")
                                if stored_uid == user_id or stored_uid == str(user_id):
                                    username = account
                                    self.instances_cache["user_id_to_username"][user_id] = username
                                    break

                            if not username:
                                username = RobloxAPI.get_username_from_user_id(user_id)
                                if username:
                                    self.instances_cache["user_id_to_username"][user_id] = username
                                    for account in list(self.manager.accounts):
                                        if account == username:
                                            self.manager.accounts[account]["user_id"] = str(user_id)
                                            self.manager.save_accounts()
                                            break

                        if user_id in self.instances_cache["user_id_to_avatar"]:
                            avatar_url = self.instances_cache["user_id_to_avatar"][user_id]
                        else:
                            avatar_url = RobloxAPI.get_user_avatar_url(user_id, "150x150")
                            if avatar_url:
                                self.instances_cache["user_id_to_avatar"][user_id] = avatar_url

                        unresolved_entry["user_id"] = user_id
                        unresolved_entry["username"] = username
                        unresolved_entry["avatar_url"] = avatar_url
                        if pid in self.instances_failed_pids:
                            del self.instances_failed_pids[pid]
                        self.instances_data_updated = True
                        self.root.after(0, self.refresh_accounts)
                    else:
                        self.instances_failed_pids[pid] = (
                            current_time,
                            unresolved_entry.get("create_time", 0),
                            unresolved_entry.get("memory_mb", 0),
                        )
                
            except Exception as e:
                print(f"[ERROR] Active Instances monitor error: {e}")
            
            try:
                self.summary_service.sync_active_instances(self.instances_data)
            except:
                pass
            
            self.instances_monitor_stop.wait(poll_interval_seconds)
    
    def open_active_instances_window(self):
        """Open window showing all active Roblox instances with pre-cached data"""
        instances_window = tk.Toplevel(self.root)
        self.apply_window_icon(instances_window)
        instances_window.title("Active Roblox Instances")
        instances_window.geometry("400x400")
        instances_window.configure(bg=self.BG_DARK)
        instances_window.resizable(False, False)
        
        if self.settings.get("enable_topmost", False):
            instances_window.attributes("-topmost", True)
        
        instances_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (instances_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (instances_window.winfo_height() // 2)
        instances_window.geometry(f"+{x}+{y}")
        
        main_frame = ttk.Frame(instances_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        header_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        header_frame.pack(fill="x", pady=(0, 10))
        
        title_label = ttk.Label(
            header_frame,
            text="Active Roblox Instances",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 12, "bold")
        )
        title_label.pack(side="left")
        
        monitoring_enabled = tk.BooleanVar(value=self.settings.get("active_instances_monitoring", False))
        
        monitor_checkbox = ttk.Checkbutton(
            header_frame,
            text="Enable Active Instances",
            variable=monitoring_enabled,
            style="Dark.TCheckbutton"
        )
        monitor_checkbox.pack(side="right")
        
        canvas_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        canvas_frame.pack(fill="both", expand=True)
        
        canvas = tk.Canvas(canvas_frame, bg=self.BG_DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="Dark.TFrame")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        status_label = ttk.Label(
            main_frame,
            text="Loading instances...",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        )
        status_label.pack(pady=(10, 0))
        
        window_active = [True]
        refresh_timer = [None]
        last_rendered_pids = [set()]
        instance_widgets = {}
        
        def on_window_close():
            window_active[0] = False
            if refresh_timer[0]:
                instances_window.after_cancel(refresh_timer[0])
            instances_window.destroy()
        
        instances_window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        def render_instances():
            """Render the pre-cached instance data to the UI"""
            if not window_active[0]:
                return
            
            if not monitoring_enabled.get():
                return
            
            data = list(self.instances_data)
            current_pids_set = {d["pid"] for d in data}
            
            data_was_updated = self.instances_data_updated
            if data_was_updated:
                self.instances_data_updated = False
            
            if current_pids_set != last_rendered_pids[0] or data_was_updated:
                reason = "PIDs changed" if current_pids_set != last_rendered_pids[0] else "data updated"
                print(f"[INFO] Active Instances window: {reason}, rebuilding UI")
                last_rendered_pids[0] = current_pids_set
                instance_widgets.clear()
                
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                
                if not data:
                    status_label.config(text="No active Roblox instances found")
                    ttk.Label(
                        scrollable_frame,
                        text="No active Roblox instances",
                        style="Dark.TLabel",
                        font=(self.FONT_FAMILY, 10)
                    ).pack(pady=20)
                else:
                    status_label.config(text=f"Found {len(data)} instance(s) - Last updated: {datetime.now().strftime('%H:%M:%S')}")
                    
                    for entry in data:
                        pid = entry["pid"]
                        user_id = entry["user_id"]
                        username = entry["username"]
                        avatar_url = entry["avatar_url"]
                        create_time = entry["create_time"]
                        memory_mb = entry["memory_mb"]
                        
                        instance_frame = tk.Frame(
                            scrollable_frame, bg=self.BG_MID, relief="solid", borderwidth=1
                        )
                        instance_frame.pack(fill="x", pady=5, padx=5)
                        
                        inner_frame = tk.Frame(instance_frame, bg=self.BG_MID)
                        inner_frame.pack(fill="x", padx=10, pady=10)
                        
                        try:
                            ct = datetime.fromtimestamp(create_time)
                            uptime = datetime.now() - ct
                            uptime_str = f"{int(uptime.total_seconds() // 3600)}h {int((uptime.total_seconds() % 3600) // 60)}m"
                        except:
                            uptime_str = "Unknown"
                        
                        if username:
                            avatar_label = tk.Label(inner_frame, bg=self.BG_MID)
                            avatar_label.pack(side="left", padx=(0, 15))
                            
                            if user_id and user_id in self.instances_cache["user_id_to_photo"]:
                                photo = self.instances_cache["user_id_to_photo"][user_id]
                                avatar_label.config(image=photo)
                                avatar_label.image = photo
                            else:
                                avatar_label.config(text="...", font=(self.FONT_FAMILY, 24), fg=self.FG_TEXT)
                                
                                def download_avatar(uid, url, label, win):
                                    try:
                                        if url:
                                            response = requests.get(url, timeout=5)
                                            if response.status_code == 200:
                                                img_data = BytesIO(response.content)
                                                img = Image.open(img_data)
                                                img = img.resize((70, 70), Image.Resampling.LANCZOS)
                                                photo = ImageTk.PhotoImage(img)
                                                self.instances_cache["user_id_to_photo"][uid] = photo
                                                def update_label():
                                                    try:
                                                        if window_active[0] and label.winfo_exists():
                                                            label.config(image=photo)
                                                            label.image = photo
                                                    except:
                                                        pass
                                                win.after(0, update_label)
                                                return
                                        def update_fallback():
                                            try:
                                                if window_active[0] and label.winfo_exists():
                                                    label.config(text="[?]", font=(self.FONT_FAMILY, 24), fg=self.FG_TEXT)
                                            except:
                                                pass
                                        win.after(0, update_fallback)
                                    except Exception as e:
                                        print(f"[ERROR] Failed to load avatar for user {uid}: {e}")
                                        def update_error():
                                            try:
                                                if window_active[0] and label.winfo_exists():
                                                    label.config(text="[?]", font=(self.FONT_FAMILY, 24), fg=self.FG_TEXT)
                                            except:
                                                pass
                                        win.after(0, update_error)
                                
                                if user_id and avatar_url:
                                    threading.Thread(target=download_avatar, args=(user_id, avatar_url, avatar_label, instances_window), daemon=True).start()
                                else:
                                    avatar_label.config(text="[?]", font=(self.FONT_FAMILY, 24), fg=self.FG_TEXT)
                            
                            info_frame = tk.Frame(inner_frame, bg=self.BG_MID)
                            info_frame.pack(side="left", fill="both", expand=True)
                            
                            tk.Label(info_frame, text=username, bg=self.BG_MID, fg=self.FG_TEXT,
                                     font=(self.FONT_FAMILY, 12, "bold"), anchor="w").pack(anchor="w")
                            
                            details1_frame = tk.Frame(info_frame, bg=self.BG_MID)
                            details1_frame.pack(anchor="w", pady=(2, 0))
                            tk.Label(details1_frame, text=f"PID: {pid}", bg=self.BG_MID, fg=self.FG_TEXT,
                                     font=(self.FONT_FAMILY, 9), anchor="w").pack(side="left", padx=(0, 15))
                            tk.Label(details1_frame, text=f"User ID: {user_id}", bg=self.BG_MID, fg=self.FG_TEXT,
                                     font=(self.FONT_FAMILY, 9), anchor="w").pack(side="left")
                            
                            details2_frame = tk.Frame(info_frame, bg=self.BG_MID)
                            details2_frame.pack(anchor="w", pady=(2, 0))
                            uptime_label = tk.Label(details2_frame, text=f"Uptime: {uptime_str}", bg=self.BG_MID, fg="#90EE90",
                                     font=(self.FONT_FAMILY, 9), anchor="w")
                            uptime_label.pack(side="left", padx=(0, 15))
                            memory_label = tk.Label(details2_frame, text=f"Memory: {memory_mb:.0f} MB", bg=self.BG_MID, fg="#87CEEB",
                                     font=(self.FONT_FAMILY, 9), anchor="w")
                            memory_label.pack(side="left")
                            
                            instance_widgets[pid] = {'uptime_label': uptime_label, 'memory_label': memory_label, 'create_time': create_time}
                        elif user_id:
                            tk.Label(inner_frame, text=f"PID: {pid} - Failed to get username (Uptime: {uptime_str})",
                                     bg=self.BG_MID, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 10)).pack()
                        else:
                            tk.Label(inner_frame, text=f"PID: {pid} - Failed to get user ID (Uptime: {uptime_str}, Memory: {memory_mb:.0f} MB)",
                                     bg=self.BG_MID, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 10)).pack()
            else:
                if data:
                    status_label.config(text=f"Found {len(data)} instance(s) - Last updated: {datetime.now().strftime('%H:%M:%S')}")
                    
                    for entry in data:
                        pid = entry["pid"]
                        if pid in instance_widgets:
                            widgets = instance_widgets[pid]
                            
                            try:
                                create_time = widgets['create_time']
                                ct = datetime.fromtimestamp(create_time)
                                uptime = datetime.now() - ct
                                uptime_str = f"{int(uptime.total_seconds() // 3600)}h {int((uptime.total_seconds() % 3600) // 60)}m"
                                if widgets['uptime_label'].winfo_exists():
                                    widgets['uptime_label'].config(text=f"Uptime: {uptime_str}")
                            except:
                                pass
                            
                            try:
                                memory_mb = entry.get("memory_mb", 0)
                                if widgets['memory_label'].winfo_exists():
                                    widgets['memory_label'].config(text=f"Memory: {memory_mb:.0f} MB")
                            except:
                                pass
            
            if window_active[0] and monitoring_enabled.get():
                refresh_timer[0] = instances_window.after(2000, render_instances)
        
        def toggle_monitoring():
            enabled = monitoring_enabled.get()
            self.settings["active_instances_monitoring"] = enabled
            self.save_settings()
            print(f"[INFO] Active Instances {'enabled' if enabled else 'disabled'}")
            if enabled:
                last_rendered_pids[0] = set()
                instance_widgets.clear()
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                
                self.start_instances_monitoring()
                refresh_btn.config(state="normal")
                status_label.config(text="Starting monitoring...")
                render_instances()
                self.refresh_accounts()
            else:
                self.stop_instances_monitoring()
                refresh_btn.config(state="disabled")
                if refresh_timer[0]:
                    instances_window.after_cancel(refresh_timer[0])
                    refresh_timer[0] = None
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                status_label.config(text="Active Instances disabled")
                ttk.Label(
                    scrollable_frame,
                    text="Enable the checkbox to start monitoring",
                    style="Dark.TLabel",
                    font=(self.FONT_FAMILY, 10)
                ).pack(pady=20)
                self.refresh_accounts()
        
        monitor_checkbox.config(command=toggle_monitoring)
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x", pady=(10, 0))
        
        refresh_btn = ttk.Button(
            button_frame,
            text="Refresh Now",
            style="Dark.TButton",
            command=render_instances,
            state="normal" if monitoring_enabled.get() else "disabled"
        )
        refresh_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Close",
            style="Dark.TButton",
            command=on_window_close
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        if monitoring_enabled.get():
            render_instances()
        else:
            status_label.config(text="Active Instances disabled")
            ttk.Label(
                scrollable_frame,
                text="Enable the checkbox to start monitoring",
                style="Dark.TLabel",
                font=(self.FONT_FAMILY, 10)
            ).pack(pady=20)
    
    def open_browser_engine_window(self):
        """Open Browser Engine selection window"""
        browser_window = tk.Toplevel(self.root)
        self.apply_window_icon(browser_window)
        browser_window.title("Browser Engine Settings")
        browser_window.geometry("420x330")
        browser_window.configure(bg=self.BG_DARK)
        browser_window.resizable(False, False)
        browser_window.transient(self.root)
        
        if self.settings.get("enable_topmost", False):
            browser_window.attributes("-topmost", True)
        
        browser_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (browser_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (browser_window.winfo_height() // 2)
        browser_window.geometry(f"+{x}+{y}")
        
        current_browser = self.settings.get("browser_type", "chrome")
        browser_var = tk.StringVar(value=current_browser)
        chrome_installed = self.is_chrome_installed()
        chromium_path = os.path.join(self.data_folder, "Chromium", "chrome-win64", "chrome.exe")
        chromium_installed = os.path.exists(chromium_path)
        
        container = ttk.Frame(browser_window, style="Dark.TFrame")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        header_frame = ttk.Frame(container, style="Dark.TFrame")
        header_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(
            header_frame,
            text="Select Browser Engine",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text="Choose which browser to use for Add Account",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(2, 0))
        
        separator = ttk.Frame(container, style="Dark.TFrame", height=1)
        separator.pack(fill="x", pady=(0, 15))
        separator.configure(relief="solid", borderwidth=1)
        
        options_frame = ttk.Frame(container, style="Dark.TFrame")
        options_frame.pack(fill="both", expand=True)
        
        radio_style = ttk.Style()
        radio_style.configure(
            "Browser.TRadiobutton",
            background=self.BG_DARK,
            foreground=self.FG_TEXT,
            font=(self.FONT_FAMILY, 10)
        )
        radio_style.map(
            "Browser.TRadiobutton",
            background=[("active", self.BG_DARK)],
            foreground=[("active", self.FG_TEXT)]
        )
        
        chrome_frame = ttk.Frame(options_frame, style="Dark.TFrame")
        chrome_frame.pack(fill="x", pady=(0, 8))
        
        chrome_radio = ttk.Radiobutton(
            chrome_frame,
            text="Google Chrome",
            variable=browser_var,
            value="chrome",
            style="Browser.TRadiobutton"
        )
        chrome_radio.pack(side="left")
        
        chrome_status = "✓ Installed" if chrome_installed else "Not Installed"
        chrome_color = "#00FF00" if chrome_installed else "#FF6666"
        tk.Label(
            chrome_frame,
            text=f"  [{chrome_status}]",
            bg=self.BG_DARK,
            fg=chrome_color,
            font=(self.FONT_FAMILY, 9)
        ).pack(side="left")
        
        chromium_frame = ttk.Frame(options_frame, style="Dark.TFrame")
        chromium_frame.pack(fill="x", pady=(0, 15))
        
        chromium_radio = ttk.Radiobutton(
            chromium_frame,
            text="Chromium",
            variable=browser_var,
            value="chromium",
            style="Browser.TRadiobutton"
        )
        chromium_radio.pack(side="left")
        
        chromium_status_text = "✓ Installed" if chromium_installed else "Not Installed"
        chromium_color = "#00FF00" if chromium_installed else "#FF6666"
        chromium_status_label = tk.Label(
            chromium_frame,
            text=f"  [{chromium_status_text}]",
            bg=self.BG_DARK,
            fg=chromium_color,
            font=(self.FONT_FAMILY, 9)
        )
        chromium_status_label.pack(side="left")
        
        progress_outer = tk.Frame(options_frame, bg=self.BG_LIGHT, relief="solid", borderwidth=1)
        
        progress_inner = tk.Frame(progress_outer, bg=self.BG_MID, height=22)
        progress_inner.pack(fill="x", padx=1, pady=1)
        progress_inner.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_inner, bg=self.BG_LIGHT, width=0)
        progress_fill.place(x=0, y=0, relheight=1)
        
        progress_label = tk.Label(
            progress_inner,
            text="0%",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=(self.FONT_FAMILY, 9, "bold")
        )
        progress_label.place(relx=0.5, rely=0.5, anchor="center")
        
        status_label = ttk.Label(
            options_frame,
            text="",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9)
        )
        
        def update_progress(percent):
            """Update the custom progress bar"""
            progress_inner.update_idletasks()
            total_width = progress_inner.winfo_width()
            fill_width = int((percent / 100) * total_width)
            progress_fill.place(x=0, y=0, relheight=1, width=fill_width)
            
            label_x = total_width // 2
            if fill_width >= label_x:
                progress_label.config(bg=self.BG_LIGHT, fg=self.BG_DARK)
            else:
                progress_label.config(bg=self.BG_MID, fg=self.FG_TEXT)
            
            progress_label.config(text=f"{int(percent)}%")
            browser_window.update()
        
        download_btn = None
        
        def download_chromium():
            """Download portable Chromium"""
            nonlocal chromium_installed
            
            download_btn.config(state="disabled", text="Downloading...")
            progress_outer.pack(fill="x", pady=(0, 10))
            status_label.pack(anchor="w", pady=(0, 10))
            status_label.config(text="Downloading Chromium...")
            browser_window.update()
            
            def do_download():
                try:
                    chromium_dir = os.path.join(self.data_folder, "Chromium")
                    os.makedirs(chromium_dir, exist_ok=True)
                    
                    browser_window.after(0, lambda: status_label.config(text="Fetching latest version..."))
                    last_change_url = "https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/LAST_CHANGE"
                    last_change_response = requests.get(last_change_url, timeout=30)
                    if last_change_response.status_code != 200:
                        raise Exception("Failed to fetch latest Chromium version")
                    build_number = last_change_response.text.strip()
                    
                    download_url = f"https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/{build_number}/chrome-win.zip"
                    browser_window.after(0, lambda: status_label.config(text=f"Downloading build {build_number}..."))
                    zip_path = os.path.join(chromium_dir, "chromium.zip")
                    
                    response = requests.get(download_url, stream=True, timeout=60)
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    last_progress = 0
                    
                    with open(zip_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    progress = int((downloaded / total_size) * 100)
                                    if progress >= last_progress + 1:
                                        last_progress = progress
                                        browser_window.after(10, lambda p=progress: update_progress(p))
                    
                    browser_window.after(0, lambda: update_progress(100))
                    browser_window.after(0, lambda: status_label.config(text="Extracting Chromium..."))
                    browser_window.after(50, lambda: update_progress(0))
                    
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        file_list = zip_ref.namelist()
                        total_files = len(file_list)
                        for i, file in enumerate(file_list):
                            zip_ref.extract(file, chromium_dir)
                            if i % 50 == 0:
                                progress = int((i / total_files) * 100)
                                browser_window.after(0, lambda p=progress: update_progress(p))
                    
                    browser_window.after(0, lambda: update_progress(100))
                    
                    extracted_folder = os.path.join(chromium_dir, "chrome-win")
                    target_folder = os.path.join(chromium_dir, "chrome-win64")
                    if os.path.exists(extracted_folder) and not os.path.exists(target_folder):
                        os.rename(extracted_folder, target_folder)
                    
                    os.remove(zip_path)
                    
                    browser_window.after(0, lambda: status_label.config(text="Downloading ChromeDriver..."))
                    browser_window.after(50, lambda: update_progress(0))
                    
                    chromedriver_url = f"https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/{build_number}/chromedriver_win32.zip"
                    chromedriver_zip_path = os.path.join(chromium_dir, "chromedriver.zip")
                    
                    chromedriver_response = requests.get(chromedriver_url, stream=True, timeout=60)
                    cd_total_size = int(chromedriver_response.headers.get('content-length', 0))
                    cd_downloaded = 0
                    cd_last_progress = 0
                    
                    with open(chromedriver_zip_path, 'wb') as f:
                        for chunk in chromedriver_response.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                                cd_downloaded += len(chunk)
                                if cd_total_size > 0:
                                    progress = int((cd_downloaded / cd_total_size) * 100)
                                    if progress >= cd_last_progress + 1:
                                        cd_last_progress = progress
                                        browser_window.after(10, lambda p=progress: update_progress(p))
                    
                    browser_window.after(0, lambda: update_progress(100))
                    browser_window.after(0, lambda: status_label.config(text="Extracting ChromeDriver..."))
                    browser_window.after(50, lambda: update_progress(0))
                    
                    with zipfile.ZipFile(chromedriver_zip_path, 'r') as zip_ref:
                        zip_ref.extractall(chromium_dir)
                    
                    browser_window.after(0, lambda: update_progress(100))
                    
                    chromedriver_extracted = os.path.join(chromium_dir, "chromedriver-win32", "chromedriver.exe")
                    chromedriver_target = os.path.join(target_folder, "chromedriver.exe")
                    if os.path.exists(chromedriver_extracted):
                        shutil.copy2(chromedriver_extracted, chromedriver_target)
                        shutil.rmtree(os.path.join(chromium_dir, "chromedriver-win32"))
                    
                    os.remove(chromedriver_zip_path)
                    
                    def update_ui():
                        nonlocal chromium_installed
                        chromium_installed = os.path.exists(os.path.join(chromium_dir, "chrome-win64", "chrome.exe"))
                        if chromium_installed:
                            chromium_status_label.config(text="  [✓ Installed]", fg="#00FF00")
                            download_btn.config(state="disabled", text="✓ Downloaded")
                            status_label.config(text="Chromium downloaded successfully!")
                        else:
                            download_btn.config(state="normal", text="Download Chromium")
                            status_label.config(text="Failed to extract Chromium.")
                        progress_outer.pack_forget()
                    
                    browser_window.after(0, update_ui)
                    
                except Exception as download_error:
                    error_msg = str(download_error)
                    def show_error():
                        download_btn.config(state="normal", text="Download Chromium")
                        progress_outer.pack_forget()
                        status_label.config(text=f"Download failed: {error_msg[:50]}...")
                    browser_window.after(0, show_error)
            
            thread = threading.Thread(target=do_download, daemon=True)
            thread.start()
        
        if not chromium_installed:
            download_btn = ttk.Button(
                options_frame,
                text="Download Chromium",
                style="Dark.TButton",
                command=download_chromium
            )
            download_btn.pack(fill="x", pady=(0, 10))
        else:
            download_btn = ttk.Button(
                options_frame,
                text="✓ Downloaded",
                style="Dark.TButton",
                state="disabled"
            )
            download_btn.pack(fill="x", pady=(0, 10))
        
        def on_browser_change(*args):
            nonlocal chromium_installed
            selected = browser_var.get()
            if selected == "chromium" and not chromium_installed:
                messagebox.showwarning(
                    "Chromium Not Installed",
                    "Please download Chromium first."
                )
                browser_var.set("chrome")
                return
            if selected == "chrome" and not chrome_installed:
                messagebox.showwarning(
                    "Chrome Not Installed",
                    "Google Chrome is not installed.\nPlease install Chrome or use Chromium."
                )
                if chromium_installed:
                    browser_var.set("chromium")
                return
            self.settings["browser_type"] = selected
            self.save_settings()
        
        browser_var.trace_add("write", on_browser_change)
        
        ttk.Button(
            container,
            text="Close",
            style="Dark.TButton",
            command=browser_window.destroy
        ).pack(fill="x", pady=(10, 0))
    
    def open_roblox_version_window(self):
        """Open Roblox Version downloader window"""
        version_window = tk.Toplevel(self.root)
        self.apply_window_icon(version_window)
        version_window.title("Roblox Version Downloader")
        version_window.geometry("500x550")
        version_window.configure(bg=self.BG_DARK)
        version_window.resizable(False, False)
        version_window.transient(self.root)
        
        if self.settings.get("enable_topmost", False):
            version_window.attributes("-topmost", True)
        
        version_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (version_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (version_window.winfo_height() // 2)
        version_window.geometry(f"+{x}+{y}")
        
        container = ttk.Frame(version_window, style="Dark.TFrame")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        header_frame = ttk.Frame(container, style="Dark.TFrame")
        header_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(
            header_frame,
            text="Roblox Version Downloader",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text="Download and install specific Roblox versions",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 8)
        ).pack(anchor="w", pady=(2, 0))
        
        separator = ttk.Frame(container, style="Dark.TFrame", height=1)
        separator.pack(fill="x", pady=(0, 15))
        separator.configure(relief="solid", borderwidth=1)
        
        input_frame = ttk.Frame(container, style="Dark.TFrame")
        input_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(
            input_frame,
            text="Version Hash:",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9, "bold")
        ).pack(anchor="w", pady=(0, 5))
        
        version_entry_frame = ttk.Frame(input_frame, style="Dark.TFrame")
        version_entry_frame.pack(fill="x", pady=(0, 10))
        
        version_var = tk.StringVar()
        version_entry = ttk.Entry(version_entry_frame, textvariable=version_var, style="Dark.TEntry")
        version_entry.pack(side="left", fill="x", expand=True, padx=(0, 5), ipady=4)
        
        ttk.Label(
            input_frame,
            text="Install Path:",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9, "bold")
        ).pack(anchor="w", pady=(0, 5))
        
        path_frame = ttk.Frame(input_frame, style="Dark.TFrame")
        path_frame.pack(fill="x", pady=(0, 10))
        
        default_path = os.path.join(os.getenv("LOCALAPPDATA"), "Roblox", "Versions")
        path_var = tk.StringVar(value=default_path)
        path_entry = ttk.Entry(path_frame, textvariable=path_var, style="Dark.TEntry")
        path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5), ipady=4)
        
        def browse_path():
            """Browse for install directory"""
            versions_path = os.path.join(os.getenv("LOCALAPPDATA"), "Roblox", "Versions")
            directory = filedialog.askdirectory(title="Select Install Directory", initialdir=versions_path if os.path.exists(versions_path) else None)
            if directory:
                path_var.set(directory)
        
        ttk.Button(
            path_frame,
            text="Browse",
            style="Dark.TButton",
            command=browse_path
        ).pack(side="left")
        
        progress_outer = tk.Frame(container, bg=self.BG_LIGHT, relief="solid", borderwidth=1)
        
        progress_inner = tk.Frame(progress_outer, bg=self.BG_MID, height=22)
        progress_inner.pack(fill="x", padx=1, pady=1)
        progress_inner.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_inner, bg=self.BG_LIGHT, width=0)
        progress_fill.place(x=0, y=0, relheight=1)
        
        progress_label = tk.Label(
            progress_inner,
            text="0%",
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=(self.FONT_FAMILY, 9, "bold")
        )
        progress_label.place(relx=0.5, rely=0.5, anchor="center")
        
        log_frame = ttk.Frame(container, style="Dark.TFrame")
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        
        ttk.Label(
            log_frame,
            text="Download Log:",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 9, "bold")
        ).pack(anchor="w", pady=(0, 5))
        
        log_text = tk.Text(
            log_frame,
            height=8,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=(self.FONT_FAMILY, 9),
            relief="solid",
            borderwidth=1,
            wrap="word",
            state="disabled"
        )
        log_text.pack(fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(log_text, command=log_text.yview, style="Dark.Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        log_text.config(yscrollcommand=scrollbar.set)
        
        def update_progress(percent):
            """Update the custom progress bar"""
            try:
                progress_inner.update_idletasks()
                total_width = progress_inner.winfo_width()
                fill_width = int((percent / 100) * total_width)
                progress_fill.place(x=0, y=0, relheight=1, width=fill_width)
                
                label_x = total_width // 2
                if fill_width >= label_x:
                    progress_label.config(bg=self.BG_LIGHT, fg=self.BG_DARK)
                else:
                    progress_label.config(bg=self.BG_MID, fg=self.FG_TEXT)
                
                progress_label.config(text=f"{int(percent)}%")
                version_window.update()
            except:
                pass
        
        def log_message(msg):
            """Log message to text widget"""
            try:
                log_text.config(state="normal")
                log_text.insert(tk.END, msg + "\n")
                log_text.see(tk.END)
                log_text.config(state="disabled")
            except:
                pass
        
        def get_current_version():
            """Fetch current LIVE version"""
            fetch_btn.config(state="disabled", text="Fetching...")
            version_window.update()
            
            def do_fetch():
                try:
                    version = self.manager.get_roblox_version("LIVE")
                    if version:
                        def update_ui():
                            version_var.set(version)
                            log_message(f"✓ Fetched current version: {version}")
                            fetch_btn.config(state="normal", text="Get Latest")
                        version_window.after(0, update_ui)
                    else:
                        def show_error():
                            log_message("✗ Failed to fetch current version")
                            fetch_btn.config(state="normal", text="Get Latest")
                        version_window.after(0, show_error)
                except Exception as e:
                    def show_error():
                        log_message(f"✗ Error: {str(e)[:50]}")
                        fetch_btn.config(state="normal", text="Get Latest")
                    version_window.after(0, show_error)
            
            thread = threading.Thread(target=do_fetch, daemon=True)
            thread.start()
        
        fetch_btn = ttk.Button(
            version_entry_frame,
            text="Get Latest",
            style="Dark.TButton",
            command=get_current_version
        )
        fetch_btn.pack(side="left")
        
        download_btn = None
        
        def download_version():
            """Download and install Roblox version"""
            version = version_var.get().strip()
            if not version:
                messagebox.showwarning("Missing Version", "Please enter a version hash or click 'Get Latest'")
                return
            
            base_path = path_var.get().strip()
            if not base_path:
                messagebox.showwarning("Missing Path", "Please select an install directory")
                return
            
            if not version.startswith("version-"):
                version_hash = f"version-{version}"
            else:
                version_hash = version
            
            install_path = os.path.join(base_path, version_hash)
            
            download_btn.config(state="disabled", text="Downloading...")
            fetch_btn.config(state="disabled")
            log_text.config(state="normal")
            log_text.delete("1.0", tk.END)
            log_text.config(state="disabled")
            progress_outer.pack(fill="x", pady=(10, 0))
            progress_outer.pack_configure(before=log_frame)
            update_progress(0)
            version_window.update()
            
            def do_download():
                try:
                    package_count = [0]
                    total_packages = [1]
                    last_logged_percent = [-1]
                    
                    def progress_callback(msg):
                        if msg.startswith("DOWNLOAD_PROGRESS:"):
                            try:
                                parts = msg.split(":")
                                package_name = parts[1]
                                percent = float(parts[2])
                                size_mb = float(parts[3])
                                total_mb = float(parts[4])
                                display_msg = f"Downloading {package_name}: {percent:.0f}% ({size_mb:.1f} MB / {total_mb:.1f} MB)"
                                
                                if int(percent) % 10 == 0 and int(percent) != last_logged_percent[0]:
                                    last_logged_percent[0] = int(percent)
                                    version_window.after(0, lambda m=display_msg: log_message(m))
                                
                                version_window.after(0, lambda p=percent: update_progress(p))
                            except:
                                pass
                        elif msg.startswith("EXTRACT_START:"):
                            try:
                                package_name = msg.split(":")[1]
                                display_msg = f"Extracting {package_name}..."
                                version_window.after(0, lambda m=display_msg: log_message(m))
                                version_window.after(0, lambda: update_progress(0))
                                last_logged_percent[0] = -1
                            except:
                                pass
                        elif msg.startswith("EXTRACT_PROGRESS:"):
                            try:
                                parts = msg.split(":")
                                package_name = parts[1]
                                percent = float(parts[2])
                                
                                if int(percent) % 25 == 0 and int(percent) != last_logged_percent[0]:
                                    last_logged_percent[0] = int(percent)
                                    display_msg = f"Extracting {package_name}: {percent:.0f}%"
                                    version_window.after(0, lambda m=display_msg: log_message(m))
                                
                                version_window.after(0, lambda p=percent: update_progress(p))
                            except:
                                pass
                        elif msg.startswith("EXTRACT_COMPLETE:"):
                            try:
                                package_name = msg.split(":")[1]
                                display_msg = f"✓ Completed {package_name}"
                                version_window.after(0, lambda m=display_msg: log_message(m))
                                version_window.after(0, lambda: update_progress(100))
                                last_logged_percent[0] = -1
                            except:
                                pass
                        else:
                            version_window.after(0, lambda m=msg: log_message(m))
                    
                    success, result = self.manager.download_roblox_version(
                        version,
                        install_path,
                        "LIVE",
                        progress_callback
                    )
                    
                    def update_ui():
                        if success:
                            log_message(f"✓ Installation complete!")
                            download_btn.config(state="normal", text="Download")
                        else:
                            log_message(f"✗ {result}")
                            download_btn.config(state="normal", text="Download")
                            messagebox.showerror("Download Failed", result)
                        
                        fetch_btn.config(state="normal")
                        progress_outer.pack_forget()
                    
                    version_window.after(0, update_ui)
                    
                except Exception as e:
                    def show_error():
                        error_msg = str(e)
                        log_message(f"✗ Error: {error_msg}")
                        download_btn.config(state="normal", text="Download")
                        fetch_btn.config(state="normal")
                        progress_outer.pack_forget()
                        messagebox.showerror("Error", f"Download failed:\n{error_msg}")
                    version_window.after(0, show_error)
            
            thread = threading.Thread(target=do_download, daemon=True)
            thread.start()
        
        button_frame = ttk.Frame(container, style="Dark.TFrame")
        button_frame.pack(fill="x", pady=(15, 0))
        
        download_btn = ttk.Button(
            button_frame,
            text="Download",
            style="Dark.TButton",
            command=download_version
        )
        download_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Close",
            style="Dark.TButton",
            command=version_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
    def write(self, text):
        """Redirect stdout/stderr writes to console"""
        if text.strip():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_to_console(f"[{timestamp}] {text}\n")
        if self.original_stdout:
            self.original_stdout.write(text)
    
    def flush(self):
        """Flush stdout"""
        if self.original_stdout:
            self.original_stdout.flush()
    
    _MAX_CONSOLE_LINES = 2000

    def log_to_console(self, message):
        """Log message to console output buffer"""
        self.console_output.append(message)
        if len(self.console_output) > self._MAX_CONSOLE_LINES:
            del self.console_output[: len(self.console_output) - self._MAX_CONSOLE_LINES]

        self._maybe_log_message(message)
        
        if self.console_text_widget:
            try:
                self.console_text_widget.config(state="normal")
                insert_start = self.console_text_widget.index(f"{tk.END}-1c linestart")
                self.console_text_widget.insert(tk.END, message)
                line_count = int(self.console_text_widget.index(tk.END).split(".")[0]) - 1
                if line_count > self._MAX_CONSOLE_LINES:
                    excess = line_count - self._MAX_CONSOLE_LINES
                    self.console_text_widget.delete("1.0", f"{excess + 1}.0")
                    insert_start = "1.0"
                self._apply_console_tags(search_from=insert_start)
                self.console_text_widget.see(tk.END)
                self.console_text_widget.config(state="disabled")
            except:
                pass
    
    def _apply_console_tags(self, search_from: str = "1.0"):
        """Apply color tags to console keywords."""
        if not self.console_text_widget:
            return
        
        keywords = {
            "[SUCCESS]": "success",
            "[ERROR]": "error",
            "[INFO]": "info",
            "[WARNING]": "warning"
        }
        
        for keyword, tag in keywords.items():
            search_start = search_from
            while True:
                pos = self.console_text_widget.search(keyword, search_start, tk.END, nocase=False)
                if not pos:
                    break
                end_pos = f"{pos}+{len(keyword)}c"
                self.console_text_widget.tag_add(tag, pos, end_pos)
                search_start = end_pos
    
    def open_console_window(self):
        """Open the Console Output window"""
        if self.console_window and tk.Toplevel.winfo_exists(self.console_window):
            self.console_window.focus()
            return
        
        self.console_window = tk.Toplevel(self.root)
        self.apply_window_icon(self.console_window)
        self.console_window.title("Console Output")
        self.console_window.configure(bg=self.BG_DARK)
        self.console_window.minsize(500, 450)
        
        if self.settings.get("enable_topmost", False):
            self.console_window.attributes("-topmost", True)
        
        self.root.update_idletasks()
        
        saved_console = self.settings.get('console_window_geometry')
        if saved_console and saved_console.get('x') is not None and saved_console.get('y') is not None:
            width = saved_console.get('width', 700)
            height = saved_console.get('height', 500)
            x = saved_console['x']
            y = saved_console['y']
            self.console_window.geometry(f"{width}x{height}+{x}+{y}")
        else:
            main_x = self.root.winfo_x()
            main_y = self.root.winfo_y()
            main_width = self.root.winfo_width()
            main_height = self.root.winfo_height()
            x = main_x + (main_width - 700) // 2
            y = main_y + (main_height - 500) // 2
            self.console_window.geometry(f"700x500+{x}+{y}")
        
        main_frame = ttk.Frame(self.console_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        title_label = ttk.Label(
            main_frame,
            text="Console Output",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        )
        title_label.pack(anchor="w", pady=(0, 10))
        
        text_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        text_frame.pack(fill="both", expand=True)
        
        self.console_text_widget = tk.Text(
            text_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            font=("Consolas", 9),
            wrap="word",
            state="disabled"
        )
        self.console_text_widget.pack(side="left", fill="both", expand=True)
        
        self.console_text_widget.tag_configure("success", foreground="#00FF00")
        self.console_text_widget.tag_configure("error", foreground="#FF0000")
        self.console_text_widget.tag_configure("info", foreground="#0078D7")
        self.console_text_widget.tag_configure("warning", foreground="#FFD700")
        
        scrollbar = ttk.Scrollbar(text_frame, command=self.console_text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        self.console_text_widget.config(yscrollcommand=scrollbar.set)
        
        self.console_text_widget.config(state="normal")
        for message in self.console_output:
            self.console_text_widget.insert(tk.END, message)
        
        self._apply_console_tags()
        self.console_text_widget.config(state="disabled")
        
        self.console_text_widget.see(tk.END)
        
        button_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        button_frame.pack(fill="x", pady=(10, 0))
        
        def clear_console():
            self.console_output.clear()
            self.console_text_widget.config(state="normal") 
            self.console_text_widget.delete(1.0, tk.END)
            self.console_text_widget.config(state="disabled") 
        
        def copy_all():
            text = self.console_text_widget.get(1.0, tk.END)
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
            except Exception:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
            messagebox.showinfo("Copied", "Console output copied to clipboard!")

        ttk.Button(
            button_frame,
            text="Clear",
            style="Dark.TButton",
            command=clear_console
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Copy All",
            style="Dark.TButton",
            command=copy_all
        ).pack(side="left", fill="x", expand=True, padx=5)
        
        ttk.Button(
            button_frame,
            text="Close",
            style="Dark.TButton",
            command=self.console_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        def on_console_close():
            """Save window geometry (position and size) before closing"""
            self.settings['console_window_geometry'] = {
                'x': self.console_window.winfo_x(),
                'y': self.console_window.winfo_y(),
                'width': self.console_window.winfo_width(),
                'height': self.console_window.winfo_height()
            }
            self.save_settings()
            self.console_text_widget = None
            self.console_window.destroy()
            self.console_window = None
        
        self.console_window.protocol("WM_DELETE_WINDOW", on_console_close)
    
    def open_favorites_window(self):
        """Open the favorites management window"""
        favorites_window = tk.Toplevel(self.root)
        self.apply_window_icon(favorites_window)
        favorites_window.title("Favorite Games")
        favorites_window.configure(bg=self.BG_DARK)
        favorites_window.resizable(False, False)
        
        self.root.update_idletasks()
        
        saved_pos = self.settings.get('favorites_window_position')
        if saved_pos and saved_pos.get('x') is not None and saved_pos.get('y') is not None:
            x = saved_pos['x']
            y = saved_pos['y']
        else:
            x = self.root.winfo_x() + 50
            y = self.root.winfo_y() + 50
        favorites_window.geometry(f"400x350+{x}+{y}")
        
        if self.settings.get("enable_topmost", False):
            favorites_window.attributes("-topmost", True)
        
        favorites_window.transient(self.root)
        favorites_window.focus_force()
        
        main_frame = ttk.Frame(favorites_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        ttk.Label(
            main_frame,
            text="Favorite Games",
            style="Dark.TLabel",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        list_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        favorites_list = tk.Listbox(
            list_frame,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            highlightthickness=0,
            border=0,
            font=("Segoe UI", 9)
        )
        favorites_list.grid(row=0, column=0, sticky="nsew")
        
        v_scrollbar = ttk.Scrollbar(list_frame, command=favorites_list.yview, orient="vertical")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        favorites_list.config(yscrollcommand=v_scrollbar.set)
        
        h_scrollbar = ttk.Scrollbar(list_frame, command=favorites_list.xview, orient="horizontal")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        favorites_list.config(xscrollcommand=h_scrollbar.set)
        
        def refresh_favorites():
            favorites_list.delete(0, tk.END)
            for fav in self.settings.get("favorite_games", []):
                private_server = fav.get("private_server", "")
                note = fav.get("note", "")
                prefix = "[P] " if private_server else ""
                display = f"{prefix}{fav['name']}"
                if note:
                    display += f" • {note}"
                favorites_list.insert(tk.END, display)
        
        refresh_favorites()
        
        def on_favorite_click(event):
            """Load selected favorite into main UI when clicked"""
            selection = favorites_list.curselection()
            if not selection:
                return
            
            index = selection[0]
            fav = self.settings["favorite_games"][index]
            
            self.place_entry.delete(0, tk.END)
            self.place_entry.insert(0, fav["place_id"])
            self.settings["last_place_id"] = fav["place_id"]
            
            private_server = fav.get("private_server", "")
            self.private_server_entry.delete(0, tk.END)
            self.private_server_entry.insert(0, private_server)
            self.settings["last_private_server"] = private_server
            
            self.save_settings()
            self.update_game_name()
        
        favorites_list.bind("<<ListboxSelect>>", on_favorite_click)
        
        btn_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        btn_frame.pack(fill="x")
        
        def add_favorite():
            """Open dialog to add a new favorite"""
            add_window = tk.Toplevel(favorites_window)
            self.apply_window_icon(add_window)
            add_window.title("Add Favorite")
            add_window.configure(bg=self.BG_DARK)
            add_window.resizable(False, False)
            
            favorites_window.update_idletasks()
            x = favorites_window.winfo_x() + 50
            y = favorites_window.winfo_y() + 50
            add_window.geometry(f"400x250+{x}+{y}")
            
            if self.settings.get("enable_topmost", False):
                add_window.attributes("-topmost", True)
            
            add_window.transient(favorites_window)
            add_window.focus_force()
            
            form_frame = ttk.Frame(add_window, style="Dark.TFrame")
            form_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            ttk.Label(form_frame, text="Place ID:", style="Dark.TLabel").pack(anchor="w")
            place_id_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            place_id_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Private Server ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            ps_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            ps_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Note (Optional):", style="Dark.TLabel").pack(anchor="w")
            note_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            note_entry.pack(fill="x", pady=(0, 10))
            
            def save_favorite():
                place_id = place_id_entry.get().strip()
                
                if not place_id:
                    messagebox.showerror("Error", "Place ID is required!")
                    return
                
                name = RobloxAPI.get_game_name(place_id)
                if not name:
                    messagebox.showerror("Error", "Could not fetch game name. Please check the Place ID.")
                    return
                
                favorite = {
                    "place_id": place_id,
                    "name": name,
                    "private_server": ps_entry.get().strip(),
                    "note": note_entry.get().strip()
                }
                
                if "favorite_games" not in self.settings:
                    self.settings["favorite_games"] = []
                
                self.settings["favorite_games"].append(favorite)
                self.save_settings()
                refresh_favorites()
                add_window.destroy()
                messagebox.showinfo("Success", f"Added '{name}' to favorites!")
                favorites_window.lift()
                favorites_window.focus_force()
        
        def on_favorites_close():
            """Save window position before closing"""
            self.settings['favorites_window_position'] = {
                'x': favorites_window.winfo_x(),
                'y': favorites_window.winfo_y()
            }
            self.save_settings()
            favorites_window.destroy()
        
        favorites_window.protocol("WM_DELETE_WINDOW", on_favorites_close)
        
        def edit_favorite():
            """Edit selected favorite"""
            selection = favorites_list.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a favorite to edit.")
                return
            
            index = selection[0]
            fav = self.settings["favorite_games"][index]
            
            edit_window = tk.Toplevel(favorites_window)
            edit_window.title("Edit Favorite")
            edit_window.configure(bg=self.BG_DARK)
            edit_window.resizable(False, False)
            
            favorites_window.update_idletasks()
            x = favorites_window.winfo_x() + 50
            y = favorites_window.winfo_y() + 50
            edit_window.geometry(f"400x250+{x}+{y}")
            
            if self.settings.get("enable_topmost", False):
                edit_window.attributes("-topmost", True)
            
            edit_window.transient(favorites_window)
            edit_window.focus_force()
            
            form_frame = ttk.Frame(edit_window, style="Dark.TFrame")
            form_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            ttk.Label(form_frame, text="Place ID:", style="Dark.TLabel").pack(anchor="w")
            place_id_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            place_id_entry.insert(0, fav["place_id"])
            place_id_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Private Server ID (Optional):", style="Dark.TLabel").pack(anchor="w")
            ps_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            ps_entry.insert(0, fav.get("private_server", ""))
            ps_entry.pack(fill="x", pady=(0, 10))
            
            ttk.Label(form_frame, text="Note (Optional):", style="Dark.TLabel").pack(anchor="w")
            note_entry = ttk.Entry(form_frame, style="Dark.TEntry")
            note_entry.insert(0, fav.get("note", ""))
            note_entry.pack(fill="x", pady=(0, 10))
            
            def save_edit():
                place_id = place_id_entry.get().strip()
                
                if not place_id:
                    messagebox.showerror("Error", "Place ID is required!")
                    return
                
                if place_id != fav["place_id"]:
                    name = RobloxAPI.get_game_name(place_id)
                    if not name:
                        messagebox.showerror("Error", "Could not fetch game name. Please check the Place ID.")
                        return
                else:
                    name = fav["name"]
                
                self.settings["favorite_games"][index] = {
                    "place_id": place_id,
                    "name": name,
                    "private_server": ps_entry.get().strip(),
                    "note": note_entry.get().strip()
                }
                
                self.save_settings()
                refresh_favorites()
                edit_window.destroy()
                messagebox.showinfo("Success", "Favorite updated!")
                favorites_window.lift()
                favorites_window.focus_force()
            
            
            button_frame = ttk.Frame(form_frame, style="Dark.TFrame")
            button_frame.pack(fill="x", pady=(10, 0))
            
            ttk.Button(
                button_frame,
                text="Save",
                style="Dark.TButton",
                command=save_edit
            ).pack(side="left", fill="x", expand=True, padx=(0, 5))
            
            ttk.Button(
                button_frame,
                text="Cancel",
                style="Dark.TButton",
                command=edit_window.destroy
            ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        def remove_favorite():
            """Remove selected favorite"""
            selection = favorites_list.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a favorite to remove.")
                return
            
            index = selection[0]
            fav = self.settings["favorite_games"][index]
            
            confirm = messagebox.askyesno(
                "Confirm Delete",
                f"Remove '{fav['name']}' from favorites?"
            )
            
            if confirm:
                self.settings["favorite_games"].pop(index)
                self.save_settings()
                refresh_favorites()
                messagebox.showinfo("Success", "Favorite removed!")
                favorites_window.lift()
                favorites_window.focus_force()
        
        ttk.Button(
            btn_frame,
            text="Add Favorite",
            style="Dark.TButton",
            command=add_favorite
        ).pack(side="left", fill="x", expand=True, padx=(0, 2))
        
        ttk.Button(
            btn_frame,
            text="Edit",
            style="Dark.TButton",
            command=edit_favorite
        ).pack(side="left", fill="x", expand=True, padx=2)
        
        ttk.Button(
            btn_frame,
            text="Remove",
            style="Dark.TButton",
            command=remove_favorite
        ).pack(side="left", fill="x", expand=True, padx=2)
        
        ttk.Button(
            btn_frame,
            text="Close",
            style="Dark.TButton",
            command=favorites_window.destroy
        ).pack(side="left", fill="x", expand=True, padx=(2, 0))
    
    def start_rename_monitoring(self):
        """Start monitoring and renaming Roblox windows"""
        if self.rename_thread and self.rename_thread.is_alive():
            return
        
        self.rename_stop_event.clear()
        self.renamed_pids.clear()
        self.rename_thread = threading.Thread(target=self._rename_monitoring_worker, daemon=True)
        self.rename_thread.start()
        print("[INFO] Rename monitoring started")
    
    def stop_rename_monitoring(self):
        """Stop rename monitoring"""
        if self.rename_thread:
            self.rename_stop_event.set()
            self.rename_thread = None
            self.renamed_pids.clear()
            print("[INFO] Rename monitoring stopped")
    
    def _rename_monitoring_worker(self):
        """Monitor for new Roblox PIDs and renames them"""
        while not self.rename_stop_event.is_set():
            try:
                current_pids = set()
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] and proc.info['name'].lower() == 'robloxplayerbeta.exe':
                            pid = proc.info['pid']
                            if self._is_valid_roblox_game_client(pid, 'robloxplayerbeta.exe'):
                                current_pids.add(pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                new_pids = current_pids - self.renamed_pids
                
                for pid in new_pids:
                    if self.rename_stop_event.is_set():
                        break
                    
                    user_id, _ = self._get_user_id_from_pid(pid)
                    
                    if user_id:
                        username = RobloxAPI.get_username_from_user_id(user_id)
                        
                        if username:
                            self._rename_roblox_window(pid, username)
                            self.renamed_pids.add(pid)
                            print(f"[INFO] Renamed Roblox window for PID {pid} to '{username}'")
                    
                    time.sleep(0.5)
                
                self.renamed_pids = self.renamed_pids.intersection(current_pids)
                
            except Exception as e:
                print(f"[ERROR] Error in rename monitoring: {e}")
            
            time.sleep(2)
    
    def _rename_roblox_window(self, pid, username):
        """Rename a Roblox window by PID"""
        try:
            def enum_windows_callback(hwnd, pid_target):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid_target:
                    if win32gui.IsWindowVisible(hwnd):
                        current_title = win32gui.GetWindowText(hwnd)
                        if 'roblox' in current_title.lower():
                            win32gui.SetWindowText(hwnd, username)
                            return False
                return True
            
            win32gui.EnumWindows(enum_windows_callback, pid)
        except Exception as e:
            print(f"[ERROR] Failed to rename window for PID {pid}: {e}")
    
    def start_anti_afk(self):
        """Start the Anti-AFK background thread"""
        if self.anti_afk_thread and self.anti_afk_thread.is_alive():
            return
        
        self.anti_afk_stop_event.clear()
        self.anti_afk_thread = threading.Thread(target=self.anti_afk_worker, daemon=True)
        self.anti_afk_thread.start()
        print("[Anti-AFK] Started")
    
    def stop_anti_afk(self):
        """Stop the Anti-AFK background thread"""
        if self.anti_afk_thread and self.anti_afk_thread.is_alive():
            self.anti_afk_stop_event.set()
            thread = self.anti_afk_thread
            def _join_afk():
                thread.join(timeout=2)
                print("[Anti-AFK] Stopped")
            threading.Thread(target=_join_afk, daemon=True).start()
        self._hide_anti_afk_tooltip()

    def _hide_anti_afk_tooltip(self):
        def _hide():
            if self.anti_afk_tooltip_timer:
                try:
                    self.root.after_cancel(self.anti_afk_tooltip_timer)
                except Exception:
                    pass
                self.anti_afk_tooltip_timer = None

            if self.anti_afk_tooltip:
                try:
                    self.anti_afk_tooltip.destroy()
                except Exception:
                    pass
                self.anti_afk_tooltip = None
                self.anti_afk_tooltip_label = None

        if self.root.winfo_exists():
            self.root.after(0, _hide)

    def _show_anti_afk_tooltip(self, text):
        if self.anti_afk_stop_event.is_set() or not self.root.winfo_exists():
            return

        def _create_or_update():
            if self.anti_afk_tooltip and self.anti_afk_tooltip.winfo_exists():
                if self.anti_afk_tooltip_label:
                    self.anti_afk_tooltip_label.config(text=text)
                self._position_anti_afk_tooltip(self.anti_afk_tooltip)
                return

            self.anti_afk_tooltip = tk.Toplevel(self.root)
            self.anti_afk_tooltip.wm_overrideredirect(True)
            self.anti_afk_tooltip.configure(bg=self.BG_MID)
            self.anti_afk_tooltip.attributes("-topmost", True)
            if self.settings.get("enable_topmost", False):
                try:
                    self.anti_afk_tooltip.attributes("-topmost", True)
                except Exception:
                    pass

            label = tk.Label(
                self.anti_afk_tooltip,
                text=text,
                bg=self.BG_MID,
                fg=self.FG_TEXT,
                font=(self.FONT_FAMILY, max(8, self.FONT_SIZE - 1)),
                padx=10,
                pady=5,
                relief="solid",
                borderwidth=1,
                highlightbackground=self.BG_LIGHT,
                highlightcolor=self.BG_LIGHT,
            )
            label.pack()
            self.anti_afk_tooltip_label = label

            self.anti_afk_tooltip.update_idletasks()
            self._position_anti_afk_tooltip(self.anti_afk_tooltip)

        if self.root.winfo_exists():
            self.root.after(0, _create_or_update)

    def _position_anti_afk_tooltip(self, tooltip_window):
        if not tooltip_window or not tooltip_window.winfo_exists():
            return

        try:
            point = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            x = point.x + 18
            y = point.y + 22
            tooltip_window.wm_geometry(f"+{x}+{y}")
        except Exception:
            try:
                x = self.root.winfo_pointerx() + 18
                y = self.root.winfo_pointery() + 22
                tooltip_window.wm_geometry(f"+{x}+{y}")
            except Exception:
                pass

    def _anti_afk_record_action_key(self, button, key_var):
        button.config(text="Press...")
        button.focus_set()

        def finish_recording(recorded_key):
            key_var.set(recorded_key)
            button.config(text=recorded_key.upper())
            self.settings["anti_afk_key"] = recorded_key
            self.save_settings()

            button.unbind("<KeyPress>")
            button.unbind("<Button-1>")
            button.unbind("<Button-2>")
            button.unbind("<Button-3>")
            button.unbind("<Button-4>")
            button.unbind("<Button-5>")
            button.unbind("<MouseWheel>")

        def on_key_press(event):
            key = event.keysym.lower()
            key_mapping = {
                "return": "enter",
                "control_l": "ctrl",
                "control_r": "ctrl",
                "shift_l": "shift",
                "shift_r": "shift",
                "alt_l": "alt",
                "alt_r": "alt",
            }
            finish_recording(key_mapping.get(key, key))
            return "break"

        def on_mouse_button(event):
            mouse_mapping = {
                1: "lmb",
                2: "mmb",
                3: "rmb",
                4: "xbutton1",
                5: "xbutton2",
            }
            finish_recording(mouse_mapping.get(event.num, f"mouse{event.num}"))
            return "break"

        def on_scroll(event):
            finish_recording("scroll_up" if event.delta > 0 else "scroll_down")
            return "break"

        button.bind("<KeyPress>", on_key_press)
        button.bind("<Button-1>", on_mouse_button)
        button.bind("<Button-2>", on_mouse_button)
        button.bind("<Button-3>", on_mouse_button)
        button.bind("<Button-4>", on_mouse_button)
        button.bind("<Button-5>", on_mouse_button)
        button.bind("<MouseWheel>", on_scroll)

    def open_anti_afk_window(self):
        """Open the standalone Anti-AFK window"""
        if self.anti_afk_window and self.anti_afk_window.winfo_exists():
            self.anti_afk_window.deiconify()
            self.anti_afk_window.lift()
            self.anti_afk_window.focus_force()
            return

        anti_afk_window = tk.Toplevel(self.root)
        self.apply_window_icon(anti_afk_window)
        self.anti_afk_window = anti_afk_window
        anti_afk_window.title("Anti AFK")
        anti_afk_window.configure(bg=self.BG_DARK)
        anti_afk_window.resizable(False, False)
        anti_afk_window.transient(self.root)

        settings_width = 320
        settings_height = 360
        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - settings_width) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - settings_height) // 2
        anti_afk_window.geometry(f"{settings_width}x{settings_height}+{x}+{y}")

        def on_close():
            self._hide_anti_afk_tooltip()
            self.anti_afk_window = None
            anti_afk_window.destroy()

        anti_afk_window.protocol("WM_DELETE_WINDOW", on_close)

        if self.settings.get("enable_topmost", False):
            anti_afk_window.attributes("-topmost", True)

        main_frame = ttk.Frame(anti_afk_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=18, pady=14)

        ttk.Label(
            main_frame,
            text="Anti AFK",
            style="Dark.TLabel",
            font=(self.FONT_FAMILY, 11, "bold")
        ).pack(anchor="w", pady=(0, 10))

        enabled_var = tk.BooleanVar(value=self.settings.get("anti_afk_enabled", False))
        action_key_var = tk.StringVar(value=self.settings.get("anti_afk_key", "w"))
        press_time_var = tk.IntVar(value=int(self.settings.get("anti_afk_press_count", self.settings.get("anti_afk_key_amount", 1))))
        interval_var = tk.IntVar(value=int(self.settings.get("anti_afk_interval_minutes", 10)))

        def save_anti_afk_settings():
            self.settings["anti_afk_enabled"] = enabled_var.get()
            self.settings["anti_afk_key"] = action_key_var.get().strip().lower() or "w"
            try:
                self.settings["anti_afk_press_count"] = max(1, int(press_time_var.get()))
            except Exception:
                self.settings["anti_afk_press_count"] = 1
            try:
                self.settings["anti_afk_interval_minutes"] = max(1, int(interval_var.get()))
            except Exception:
                self.settings["anti_afk_interval_minutes"] = 10
            self.save_settings()

        def on_enabled_toggle():
            save_anti_afk_settings()
            if enabled_var.get():
                self.start_anti_afk()
            else:
                self.stop_anti_afk()

        ttk.Checkbutton(
            main_frame,
            text="Enable Anti-AFK",
            variable=enabled_var,
            style="Dark.TCheckbutton",
            command=on_enabled_toggle
        ).pack(anchor="w", pady=(0, 10))

        action_row = ttk.Frame(main_frame, style="Dark.TFrame")
        action_row.pack(fill="x", pady=2)
        ttk.Label(action_row, text="Action Key:", style="Dark.TLabel", font=(self.FONT_FAMILY, 9)).pack(side="left")
        action_button = ttk.Button(
            action_row,
            text=action_key_var.get().upper(),
            style="Dark.TButton",
            width=14
        )
        action_button.pack(side="right")
        action_button.config(command=lambda: self._anti_afk_record_action_key(action_button, action_key_var))

        press_row = ttk.Frame(main_frame, style="Dark.TFrame")
        press_row.pack(fill="x", pady=2)
        ttk.Label(press_row, text="Press Keys:", style="Dark.TLabel", font=(self.FONT_FAMILY, 9)).pack(side="left")
        press_spinner = tk.Spinbox(
            press_row,
            from_=1,
            to=10,
            increment=1,
            textvariable=press_time_var,
            width=8,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            buttonbackground=self.BG_LIGHT,
            font=(self.FONT_FAMILY, 9),
            readonlybackground=self.BG_MID,
            selectbackground=self.FG_ACCENT,
            selectforeground=self.FG_TEXT,
            insertbackground=self.FG_TEXT,
            relief="flat",
            borderwidth=1,
            highlightthickness=0,
        )
        press_spinner.pack(side="right")
        press_spinner.bind("<KeyRelease>", lambda _e: save_anti_afk_settings())
        press_spinner.bind("<FocusOut>", lambda _e: save_anti_afk_settings())

        interval_row = ttk.Frame(main_frame, style="Dark.TFrame")
        interval_row.pack(fill="x", pady=2)
        ttk.Label(interval_row, text="Interval (minutes):", style="Dark.TLabel", font=(self.FONT_FAMILY, 9)).pack(side="left")
        interval_spinner = tk.Spinbox(
            interval_row,
            from_=1,
            to=120,
            textvariable=interval_var,
            width=8,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            buttonbackground=self.BG_LIGHT,
            font=(self.FONT_FAMILY, 9),
            readonlybackground=self.BG_MID,
            selectbackground=self.FG_ACCENT,
            selectforeground=self.FG_TEXT,
            insertbackground=self.FG_TEXT,
            relief="flat",
            borderwidth=1,
            highlightthickness=0,
        )
        interval_spinner.pack(side="right")
        interval_spinner.bind("<KeyRelease>", lambda _e: save_anti_afk_settings())
        interval_spinner.bind("<FocusOut>", lambda _e: save_anti_afk_settings())

        win_actions_frame = ttk.LabelFrame(main_frame, text="Window Manager", style="Dark.TLabelframe")
        win_actions_frame.pack(fill="x", pady=(10, 0), ipady=5)
        btn_grid = ttk.Frame(win_actions_frame, style="Dark.TFrame")
        btn_grid.pack(fill="x", padx=5, pady=5)
        ttk.Button(
            btn_grid,
            text="Minimise All",
            style="Dark.TButton",
            command=self.minimize_all_roblox
        ).grid(row=0, column=0, padx=5, pady=2, sticky="ew")
        ttk.Button(
            btn_grid,
            text="Restore All",
            style="Dark.TButton",
            command=self.restore_all_roblox
        ).grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        ttk.Button(
            btn_grid,
            text="Cascade",
            style="Dark.TButton",
            command=self.cascade_roblox_windows
        ).grid(row=1, column=0, padx=5, pady=2, sticky="ew")
        ttk.Button(
            btn_grid,
            text="Grid Layout",
            style="Dark.TButton",
            command=self.grid_roblox_windows
        ).grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        btn_grid.columnconfigure(0, weight=1)
        btn_grid.columnconfigure(1, weight=1)

        ttk.Button(
            main_frame,
            text="Close",
            style="Dark.TButton",
            command=on_close
        ).pack(fill="x", pady=(12, 0))

        if enabled_var.get():
            self.start_anti_afk()

    def start_optimize_roblox_ram(self):
        """Start background RAM trimming for newly detected Roblox processes"""
        if self.optimize_ram_thread and self.optimize_ram_thread.is_alive():
            return

        self.optimize_ram_stop_event.clear()
        self.optimize_ram_thread = threading.Thread(target=self._optimize_roblox_ram_worker, daemon=True, name="RobloxRamTrim")
        self.optimize_ram_thread.start()
        print("[INFO] Roblox RAM optimization started")

    def stop_optimize_roblox_ram(self):
        """Stop background RAM trimming"""
        if self.optimize_ram_thread and self.optimize_ram_thread.is_alive():
            self.optimize_ram_stop_event.set()
            thread = self.optimize_ram_thread
            def _join_ram():
                thread.join(timeout=2)
            threading.Thread(target=_join_ram, daemon=True).start()
        self.optimize_ram_thread = None
        self.optimize_ram_stop_event.clear()
        print("[INFO] Roblox RAM optimization stopped")

    def _trim_roblox_process_ram(self, pid):
        try:
            kernel32 = ctypes.windll.kernel32
            h_process = kernel32.OpenProcess(0x0500, False, int(pid))
            if h_process:
                try:
                    kernel32.SetProcessWorkingSetSize(h_process, -1, -1)
                finally:
                    kernel32.CloseHandle(h_process)
                print(f"[INFO] Trimmed Roblox RAM for PID {pid}")
        except Exception as e:
            print(f"[ERROR] Failed to trim RAM for PID {pid}: {e}")

    def _optimize_roblox_ram_worker(self):
        while not self.optimize_ram_stop_event.is_set():
            try:
                limit_mb = max(1, int(self.settings.get("optimize_roblox_ram_limit_mb", 750)))
                current_pids = sorted(self._get_roblox_pids())

                for pid in current_pids:
                    if self.optimize_ram_stop_event.is_set():
                        break
                    try:
                        proc = psutil.Process(pid)
                        memory_mb = proc.memory_info().rss / 1024 / 1024
                        if memory_mb >= limit_mb:
                            self._trim_roblox_process_ram(pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except Exception as e:
                print(f"[ERROR] Roblox RAM optimization error: {e}")

            if self.optimize_ram_stop_event.wait(15):
                break
    
    def minimize_all_roblox(self):
        hwnds = self._get_roblox_windows()
        for hwnd in hwnds:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        return len(hwnds)

    def restore_all_roblox(self):
        hwnds = self._get_roblox_windows()
        for hwnd in hwnds:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        return len(hwnds)

    def cascade_roblox_windows(self):
        hwnds = self._get_roblox_windows()
        if not hwnds:
            return 0
        try:
            work_area = win32api.GetMonitorInfo(win32api.MonitorFromPoint((0, 0)))['Work']
            left, top, right, bottom = work_area
        except Exception:
            left, top, right, bottom = 0, 0, 1920, 1080
        work_width = right - left
        work_height = bottom - top
        win_w = min(800, int(work_width * 0.8))
        win_h = min(600, int(work_height * 0.8))
        start_x = left + 30
        start_y = top + 30
        offset_x = 30
        offset_y = 30
        for idx, hwnd in enumerate(hwnds):
            pos_x = start_x + (idx * offset_x)
            pos_y = start_y + (idx * offset_y)
            if pos_x + win_w > right or pos_y + win_h > bottom:
                reset_cycle = idx % 5
                pos_x = start_x + (reset_cycle * offset_x)
                pos_y = start_y + (reset_cycle * offset_y)
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, pos_x, pos_y, win_w, win_h, win32con.SWP_SHOWWINDOW)
        return len(hwnds)

    def grid_roblox_windows(self):
        hwnds = self._get_roblox_windows()
        if not hwnds:
            return 0
        try:
            work_area = win32api.GetMonitorInfo(win32api.MonitorFromPoint((0, 0)))['Work']
            left, top, right, bottom = work_area
        except Exception:
            left, top, right, bottom = 0, 0, 1920, 1080
        work_width = right - left
        work_height = bottom - top
        import math
        n = len(hwnds)
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        cell_w = int(work_width / cols)
        cell_h = int(work_height / rows)
        for idx, hwnd in enumerate(hwnds):
            r = idx // cols
            c = idx % cols
            pos_x = left + (c * cell_w)
            pos_y = top + (r * cell_h)
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, pos_x, pos_y, cell_w, cell_h, win32con.SWP_SHOWWINDOW)
        return len(hwnds)

    def _get_roblox_windows(self):
        hwnds = []
        def _cb(hwnd, extra):
            if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                if win32gui.GetClassName(hwnd) == "RobloxPlayClass":
                    hwnds.append(hwnd)
            return True
        win32gui.EnumWindows(_cb, None)
        return hwnds
    
    def start_auto_rejoin_for_account(self, account):
        """Start the auto-rejoin background thread for a specific account"""
        if account in self.auto_rejoin_threads:
            existing_thread = self.auto_rejoin_threads[account]
            if existing_thread.is_alive():
                print(f"[Auto-Rejoin] Thread already running for {account}")
                return
            else:
                print(f"[Auto-Rejoin] Cleaning up dead thread for {account}")
                del self.auto_rejoin_threads[account]
        
        if account not in self.auto_rejoin_configs:
            print(f"[Auto-Rejoin] No config found for {account}")
            return
        
        stop_event = threading.Event()
        self.auto_rejoin_stop_events[account] = stop_event
        
        thread = threading.Thread(
            target=self.auto_rejoin_worker_for_account,
            args=(account,),
            daemon=True,
            name=f"AutoRejoin-{account}"  
        )
        self.auto_rejoin_threads[account] = thread
        thread.start()
        print(f"[Auto-Rejoin] Started thread {thread.name} for {account}")
        if len(self.auto_rejoin_threads) == 1:
            self._start_global_screenshot_loop()
    
    def stop_auto_rejoin_for_account(self, account):
        """Stop the auto-rejoin background thread for a specific account"""
        if account in self.auto_rejoin_stop_events:
            self.auto_rejoin_stop_events[account].set()
        
        if account in self.auto_rejoin_threads:
            thread = self.auto_rejoin_threads[account]
            if thread.is_alive():
                def _join_rejoin():
                    thread.join(timeout=2)
                threading.Thread(target=_join_rejoin, daemon=True).start()
            del self.auto_rejoin_threads[account]
        
        if account in self.auto_rejoin_stop_events:
            del self.auto_rejoin_stop_events[account]

        if not self.auto_rejoin_threads:
            self._stop_global_screenshot_loop()

        print(f"[Auto-Rejoin] Stopped for {account}")
    
    def stop_all_auto_rejoin(self):
        """Stop all auto-rejoin threads"""
        for account in list(self.auto_rejoin_threads.keys()):
            self.stop_auto_rejoin_for_account(account)
        self._stop_global_screenshot_loop()

    def _start_global_screenshot_loop(self):
        if self._webhook_screenshot_thread and self._webhook_screenshot_thread.is_alive():
            return
        self._webhook_screenshot_thread = threading.Thread(
            target=self._global_screenshot_worker, daemon=True, name="WebhookScreenshot"
        )
        self._webhook_screenshot_thread.start()
        print("[INFO] Global hourly webhook screenshot started")

    def _stop_global_screenshot_loop(self):
        if self._webhook_screenshot_thread is None:
            return
        self._webhook_screenshot_thread = None
        print("[INFO] Global hourly webhook screenshot stopped")

    def _global_screenshot_worker(self):
        interval = self._webhook_screenshot_interval_minutes() * 60
        time.sleep(interval)
        while self._webhook_screenshot_thread is threading.current_thread():
            interval = self._webhook_screenshot_interval_minutes() * 60
            if self._webhook_enabled() and self._webhook_screenshot_enabled():
                self._send_webhook_screenshot(self._get_webhook_cfg().get("url", ""), "")
            time.sleep(interval)
    
    def is_roblox_running(self):
        """Check if any Roblox window exists"""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "Roblox")
            return hwnd != 0
        except:
            return False

    def _has_internet_connection(self, timeout=3):
        test_urls = (
            "https://www.google.com/generate_204",
            "https://www.cloudflare.com/cdn-cgi/trace",
        )
        for url in test_urls:
            try:
                resp = requests.get(url, timeout=timeout)
                if resp.status_code < 500:
                    return True
            except Exception:
                continue
        return False
    
    def _wait_for_presence_slot(self, stop_event=None, min_gap_seconds=0.35):
        """Throttle Presence API checks so multiple accounts are checked sequentially."""
        while True:
            now = time.time()
            with self.auto_rejoin_presence_lock:
                wait_for = self.auto_rejoin_next_presence_time - now
                if wait_for <= 0:
                    self.auto_rejoin_next_presence_time = now + max(0.1, float(min_gap_seconds))
                    return True

            sleep_for = min(0.25, max(0.05, wait_for))
            if stop_event and stop_event.wait(sleep_for):
                return False
            if not stop_event:
                time.sleep(sleep_for)

    def is_player_in_game(self, user_id, cookie, expected_place_id, stop_event=None):
        """Check if player is still in the same game using Presence API.
        Returns (in_game, place_id, game_id, error_msg) — error_msg is None on success."""
        try:
            if not self._wait_for_presence_slot(stop_event):
                return False, None, None, "Presence check cancelled"

            presence = RobloxAPI.get_player_presence(user_id, cookie)

            if presence:
                in_game = presence.get('in_game', False)
                place_id = presence.get('place_id')

                if in_game:
                    try:
                        if int(place_id) == int(expected_place_id):
                            return True, place_id, presence.get('game_id'), None
                    except (ValueError, TypeError):
                        pass

                return False, None, None, None
            else:
                return False, None, None, "Presence API returned None — cookie may be invalid"
        except Exception as e:
            print(f"[Auto-Rejoin] Error checking player status: {e}")
            traceback.print_exc()
            return False, None, None, f"Presence check exception: {e}"
    
    def _check_roblox_process_exists(self, account):
        if account not in self.auto_rejoin_pids:
            return False
        
        pid = self.auto_rejoin_pids[account]
        try:
            return psutil.pid_exists(pid)
        except Exception as e:
            print(f"[Auto-Rejoin] Error checking process {pid}: {e}")
            return False
    
    def auto_rejoin_worker_for_account(self, account):
        """Background worker that monitors for disconnection and rejoins for a specific account."""   
        config = self.auto_rejoin_configs.get(account, {})
        stop_event = self.auto_rejoin_stop_events.get(account)
        
        if not stop_event:
            return
        
        stagger_delay = random.uniform(6.0, 9.0)
        time.sleep(stagger_delay)
        
        retry_count = 0
        max_retries = config.get('max_retries', 5)
        check_interval = config.get('check_interval', 10)
        check_internet_before_launch = bool(config.get('check_internet_before_launch', True))
        last_internet_warning_time = 0.0

        def wait_next_check():
            base = max(3, int(check_interval))
            jitter = random.uniform(0.2, min(1.5, base * 0.2))
            return stop_event.wait(base + jitter)

        def can_launch_now():
            nonlocal last_internet_warning_time
            if not check_internet_before_launch:
                return True
            if self._has_internet_connection(timeout=3):
                return True

            now = time.time()
            if now - last_internet_warning_time > 60:
                print(f"[Auto-Rejoin] [{account}] Internet unavailable, delaying launch.")
                self._maybe_send_webhook_embed(
                    "Auto Rejoin — Waiting For Internet",
                    f"**{account}** is waiting for internet before launching.",
                    0xF39C12
                )
                last_internet_warning_time = now
            return False

        place_id = config.get('place_id')
        private_server = config.get('private_server', '')
        job_id = config.get('job_id', '')
        
        if not place_id:
            print(f"[Auto-Rejoin] Invalid configuration for {account}")
            return
        
        if account not in self.manager.accounts:
            print(f"[Auto-Rejoin] Account {account} not found")
            return
        
        account_data = self.manager.accounts[account]
        cookie = account_data.get('cookie')
        
        if 'user_id_cache' not in self.settings:
            self.settings['user_id_cache'] = {}
        
        user_id = RobloxAPI.get_user_id_from_username(
            account,
            use_cache=True,
            cache_dict=self.settings['user_id_cache']
        )
        if not user_id:
            print(f"[Auto-Rejoin] Could not get user ID for {account}")
            return
        
        try:
            self.save_settings()
        except Exception as e:
            print(f"[Auto-Rejoin] Warning: Could not save user ID cache: {e}")
        
        print(f"[Auto-Rejoin] Started monitoring {account} for game {place_id}")
        self._maybe_send_webhook_embed(
            "Auto Rejoin — Started",
            f"**{account}** is now being monitored for place `{place_id}`.",
            0x3498DB
        )

        consecutive_failed_checks = 0
        max_consecutive_fails = 2

        if account in self.auto_rejoin_pids:
            print(f"[Auto-Rejoin] [{account}] Using pre-matched PID {self.auto_rejoin_pids[account]}")
        else:
            print(f"[Auto-Rejoin] [{account}] No pre-matched PID - launching game...")
            while not stop_event.is_set() and not can_launch_now():
                if wait_next_check():
                    return
            success = self._launch_and_track_pid(account, place_id, private_server, job_id)
            if not success:
                retry_count += 1
                self._maybe_send_webhook_embed(
                    "Auto Rejoin — Launch Failed",
                    f"**{account}** failed to launch place `{place_id}` (attempt {retry_count}/{max_retries}).",
                    0xE74C3C
                )
                if retry_count >= max_retries:
                    print(f"[Auto-Rejoin] [{account}] Max retries ({max_retries}) reached on initial launch. Stopping.")
                    return
            time.sleep(10)
        
        while not stop_event.is_set():
            try:
                check_presence = config.get('check_presence', True)
                disconnect_detected = False
                game_id = ''

                if check_presence:
                    in_game, current_place_id, game_id, pres_err = self.is_player_in_game(user_id, cookie, place_id, stop_event)
                    if pres_err:
                        self._maybe_send_webhook_embed(
                            "Auto Rejoin — Presence Error",
                            f"**{account}**\n{pres_err}",
                            0xF39C12
                        )
                    disconnect_detected = not in_game
                    
                    if disconnect_detected:
                        consecutive_failed_checks += 1
                        if consecutive_failed_checks < max_consecutive_fails:
                            disconnect_detected = False
                            if wait_next_check():
                                break
                            continue
                    else:
                        consecutive_failed_checks = 0
                else:
                    if not self._wait_for_presence_slot(stop_event):
                        break
                    presence = RobloxAPI.get_player_presence(user_id, cookie)
                    
                    if presence:
                        in_game = presence.get('in_game', False)
                        current_place_id = presence.get('place_id')
                        game_id = presence.get('game_id', '')
                        
                        print(f"[Auto-Rejoin] [{account}] Presence check (any game mode) - in_game: {in_game}, place_id: {current_place_id}")
                        
                        if in_game:
                            disconnect_detected = False
                            consecutive_failed_checks = 0
                        else:
                            consecutive_failed_checks += 1
                            if consecutive_failed_checks < max_consecutive_fails:
                                disconnect_detected = False
                                if wait_next_check():
                                    break
                                continue
                            else:
                                disconnect_detected = True
                    else:
                        consecutive_failed_checks += 1
                        if consecutive_failed_checks < max_consecutive_fails:
                            disconnect_detected = False
                            if wait_next_check():
                                break
                            continue
                        else:
                            disconnect_detected = True
                
                if disconnect_detected:
                    if not can_launch_now():
                        if wait_next_check():
                            break
                        continue

                    retry_count += 1
                    consecutive_failed_checks = 0
                    print(f"[Auto-Rejoin] [{account}] Disconnection detected! Rejoining... (Attempt {retry_count}/{max_retries})")

                    self._maybe_send_webhook_embed(
                        "Auto Rejoin — Disconnected",
                        f"**{account}** disconnected from place `{place_id}`.\nRejoin attempt **{retry_count}/{max_retries}**.",
                        0xF39C12
                    )

                    if account in self.auto_rejoin_pids:
                        old_pid = self.auto_rejoin_pids[account]
                        try:
                            subprocess.run(['taskkill', '/F', '/PID', str(old_pid)],
                                         capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
                            time.sleep(1)
                            print(f"[Auto-Rejoin] [{account}] Closed old Roblox instance (PID: {old_pid})")
                        except Exception as e:
                            print(f"[Auto-Rejoin] [{account}] Error closing instance (PID: {old_pid}): {e}")
                        del self.auto_rejoin_pids[account]

                    rejoin_job_id = job_id if job_id else (game_id if game_id else '')
                    success = self._launch_and_track_pid(account, place_id, private_server, rejoin_job_id)

                    if success:
                        print(f"[Auto-Rejoin] [{account}] Rejoin attempt successful")
                        self._maybe_send_webhook_embed(
                            "Auto Rejoin — Success",
                            f"**{account}** has rejoined place `{place_id}`.",
                            0x2ECC71
                        )
                        retry_count = 0
                        time.sleep(10)
                    else:
                        self._maybe_send_webhook_embed(
                            "Auto Rejoin — Rejoin Failed",
                            f"**{account}** failed to relaunch for place `{place_id}` (attempt {retry_count}/{max_retries}).",
                            0xE74C3C
                        )
                        if retry_count >= max_retries:
                            print(f"[Auto-Rejoin] [{account}] Max retries ({max_retries}) reached. Stopping.")
                            self._maybe_send_webhook_embed(
                                "Auto Rejoin — Stopped",
                                f"**{account}** reached max retries ({max_retries}). Auto-rejoin stopped.",
                                0xE74C3C
                            )
                            break
                        if wait_next_check():
                            break
                else:
                    retry_count = 0
                    if wait_next_check():
                        break

            except Exception as e:
                print(f"[Auto-Rejoin] [{account}] Error: {e}")
                self._maybe_send_webhook_embed(
                    "Auto Rejoin — Error",
                    f"**{account}**\n```{e}```",
                    0xE74C3C
                )
                if wait_next_check():
                    break
    
    def _launch_and_track_pid(self, account, place_id, private_server, job_id):
        with self.auto_rejoin_launch_lock:
            pids_before = self._get_roblox_pids()
            
            launcher_pref, custom_launcher_path = self._get_roblox_launcher_config()
            success = self.manager.launch_roblox(account, place_id, private_server, launcher_pref, job_id, custom_launcher_path)
            
            if not success:
                return False
            
            print(f"[Auto-Rejoin] [{account}] Game launched successfully")
            
            time.sleep(5)
            
            pids_after = self._get_roblox_pids()
            new_pids = pids_after - pids_before
            
            if not new_pids:
                print(f"[Auto-Rejoin] [{account}] No new Roblox processes detected")
                return False
            
            available_pids = new_pids - set(self.auto_rejoin_pids.values())
            
            if available_pids:
                new_pid = max(available_pids)
                self.auto_rejoin_pids[account] = new_pid
                print(f"[Auto-Rejoin] [{account}] Successfully tracked PID {new_pid}")
                return True
            else:
                print(f"[Auto-Rejoin] [{account}] All new PIDs are already tracked by other accounts")
                return False
    
    def _get_roblox_pids(self):
        """Get all currently running RobloxPlayerBeta.exe PIDs using psutil."""
        try:
            pids = set()
            for p in psutil.process_iter(["pid", "name"]):
                if p.info["name"] and p.info["name"].lower() == "robloxplayerbeta.exe":
                    pid = p.info["pid"]
                    if self._is_valid_roblox_game_client(pid, "robloxplayerbeta.exe"):
                        pids.add(pid)
            return pids
        except Exception as e:
            print(f"[Auto-Rejoin] Error getting Roblox PIDs: {e}")
            return set()
    
    def _is_pid_roblox_process(self, pid):
        """Check if a specific PID is still a running RobloxPlayerBeta.exe process"""
        try:
            process = psutil.Process(pid)
            return process.is_running() and process.name().lower() == "robloxplayerbeta.exe"
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        except Exception as e:
            print(f"[Auto-Rejoin] Error checking PID {pid}: {e}")
            return False
    
    def _get_exe_description(self, pid):
        try:
            proc = psutil.Process(pid)
            exe = proc.exe()
            translations = win32api.GetFileVersionInfo(exe, r'\VarFileInfo\Translation')
            lang, codepage = translations[0]
            key = f'\\StringFileInfo\\{lang:04X}{codepage:04X}\\FileDescription'
            return win32api.GetFileVersionInfo(exe, key) or ""
        except Exception:
            return ""

    def _is_valid_roblox_game_client(self, pid, process_name_lower=None):
        try:
            if process_name_lower is None:
                try:
                    process = psutil.Process(pid)
                    process_name_lower = process.name().lower()
                except:
                    return False

            if process_name_lower != "robloxplayerbeta.exe":
                return False

            desc = self._get_exe_description(pid)
            if desc:
                return "roblox" in desc.lower()

            return True

        except Exception:
            return process_name_lower == "robloxplayerbeta.exe" if process_name_lower else False
    
    def _match_pids_to_accounts(self, accounts):
        """Match all running Roblox PIDs to accounts"""
        print(f"[Auto-Rejoin] Starting global PID matching for {len(accounts)} account(s)...")
        
        if 'user_id_cache' not in self.settings:
            self.settings['user_id_cache'] = {}
        
        account_user_ids = {}
        for account in accounts:
            user_id = RobloxAPI.get_user_id_from_username(
                account,
                use_cache=True,
                cache_dict=self.settings['user_id_cache']
            )
            if user_id:
                account_user_ids[account] = str(user_id)
                print(f"[Auto-Rejoin] {account} -> User ID: {user_id}")
            else:
                print(f"[Auto-Rejoin] {account} -> Could not get user ID")
        
        try:
            self.save_settings()
        except Exception as e:
            print(f"[Auto-Rejoin] Warning: Could not save user ID cache: {e}")
        
        all_pids = self._get_roblox_pids()
        print(f"[Auto-Rejoin] Found {len(all_pids)} Roblox process(es)")
        
        if not all_pids:
            return {}
        
        used_logs = set()
        pid_user_ids = {}
        for pid in all_pids:
            if pid in self.auto_rejoin_pids.values():
                print(f"[Auto-Rejoin] PID {pid} already tracked, skipping")
                continue
            
            user_id, matched_log = self._get_user_id_from_pid(pid, used_logs)
            if user_id:
                pid_user_ids[pid] = str(user_id)
                print(f"[Auto-Rejoin] PID {pid} -> User ID: {user_id}")
            else:
                print(f"[Auto-Rejoin] PID {pid} -> Could not extract user ID")
        
        matches = {}
        for account, account_user_id in account_user_ids.items():
            if account in self.auto_rejoin_pids:
                continue
                
            for pid, pid_user_id in pid_user_ids.items():
                if account_user_id == pid_user_id:
                    matches[account] = pid
                    self.auto_rejoin_pids[account] = pid
                    print(f"[Auto-Rejoin] MATCHED: {account} (user {account_user_id}) -> PID {pid}")
                    del pid_user_ids[pid]
                    break
        
        unmatched = [acc for acc in accounts if acc not in matches and acc not in self.auto_rejoin_pids]
        if unmatched:
            print(f"[Auto-Rejoin] Unmatched accounts (will launch new): {unmatched}")
        
        return matches
    
    def _get_user_id_from_pid(self, pid, used_logs=None):
        if used_logs is None:
            used_logs = set()
            
        try:
            process = psutil.Process(pid)
            if not (process.is_running() and process.name().lower() == "robloxplayerbeta.exe"):
                return None, None
            
            for uname, r_pid in list(self.auto_rejoin_pids.items()):
                if r_pid == pid:
                    for account in list(self.manager.accounts):
                        if account == uname:
                            stored_uid = self.manager.accounts[account].get("user_id")
                            if stored_uid:
                                return str(stored_uid), None
                            uid = RobloxAPI.get_user_id_from_username(uname)
                            if uid:
                                self.manager.accounts[account]["user_id"] = str(uid)
                                self.manager.save_accounts()
                                return str(uid), None

            try:
                cmd_args = process.cmdline()
                for arg in cmd_args:
                    if hasattr(RobloxAPI, "launch_trackers"):
                        for tracker_id, uname in RobloxAPI.launch_trackers.items():
                            if tracker_id in arg:
                                for account in list(self.manager.accounts):
                                    if account == uname:
                                        stored_uid = self.manager.accounts[account].get("user_id")
                                        if stored_uid:
                                            return str(stored_uid), None
                                        uid = RobloxAPI.get_user_id_from_username(uname)
                                        if uid:
                                            self.manager.accounts[account]["user_id"] = str(uid)
                                            self.manager.save_accounts()
                                            return str(uid), None
            except:
                pass

            create_time_local = datetime.fromtimestamp(process.create_time())
            create_time_utc = datetime.fromtimestamp(process.create_time(), tz=timezone.utc).replace(tzinfo=None)
            
            logs_dir = os.path.join(os.getenv("LOCALAPPDATA"), "Roblox", "logs")
            if not os.path.exists(logs_dir):
                return None, None
            
            time_window = timedelta(seconds=10)
            matching_logs = []
            
            for filename in os.listdir(logs_dir):
                if not filename.endswith("_last.log"):
                    continue
                
                full_path = os.path.join(logs_dir, filename)
                
                if full_path in used_logs:
                    continue
                
                match = re.search(r'(\d{8}T\d{6}Z)', filename)
                if not match:
                    continue
                
                timestamp_str = match.group(1)
                try:
                    log_time = datetime.strptime(timestamp_str, "%Y%m%dT%H%M%SZ")
                    time_diff = (log_time - create_time_utc).total_seconds()
                    
                    if 0 <= time_diff <= 10:
                        matching_logs.append((time_diff, full_path, log_time))
                except ValueError:
                    continue
            
            matching_logs.sort(key=lambda x: x[0])
            
            for time_diff, log_path, log_time in matching_logs:
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(50000)
                    
                    if "userid:" in content:
                        user_id = content.split("userid:")[1].split(",")[0].strip()
                        if user_id.isdigit():
                            used_logs.add(log_path)
                            return user_id, log_path
                except Exception as e:
                    print(f"[Auto-Rejoin] Error reading log {log_path}: {e}")
                    continue
            
            return None, None
            
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None, None
        except Exception as e:
            print(f"[Auto-Rejoin] Error getting user ID for PID {pid}: {e}")
            return None, None
      
    def anti_afk_worker(self):
        """Background worker that rotates Roblox windows during anti-AFK maintenance."""
        while not self.anti_afk_stop_event.is_set():
            try:
                interval_minutes = max(1, int(self.settings.get("anti_afk_interval_minutes", 10)))
                press_count = max(1, int(self.settings.get("anti_afk_press_count", self.settings.get("anti_afk_key_amount", 1))))
                action_key = str(self.settings.get("anti_afk_key", "w") or "w").strip().lower()
                total_seconds = interval_minutes * 60
                countdown_seconds = min(30, total_seconds)
                wait_seconds = max(0, total_seconds - countdown_seconds)

                if wait_seconds > 0 and self.anti_afk_stop_event.wait(wait_seconds):
                    break

                for remaining in range(countdown_seconds, 0, -1):
                    if self.anti_afk_stop_event.is_set():
                        return
                    self._show_anti_afk_tooltip(f"Anti-AFK Maintenance will start in {remaining}s")
                    if self.anti_afk_stop_event.wait(1):
                        return

                self._hide_anti_afk_tooltip()
                self._anti_afk_run_maintenance_cycle(action_key, press_count)

            except Exception as e:
                print(f"[Anti-AFK] Error: {e}")
                time.sleep(5)

    def _anti_afk_run_maintenance_cycle(self, action_key, press_count):
        roblox_pids = self._get_roblox_pids()
        if not roblox_pids:
            print("[Anti-AFK] No Roblox processes found")
            return

        hwnds = self._get_roblox_hwnds_from_pids(roblox_pids)
        if not hwnds:
            print("[Anti-AFK] No Roblox windows found")
            return

        try:
            original_hwnd = win32gui.GetForegroundWindow()
        except Exception:
            original_hwnd = None

        for hwnd in hwnds:
            if self.anti_afk_stop_event.is_set():
                break

            window_spec = f"[HANDLE:0x{hwnd:08X}]"
            try:
                try:
                    import win32con
                    win32gui.SetWindowPos(
                        hwnd, 0,
                        100, 100, 0, 0,
                        win32con.SWP_NOSIZE | win32con.SWP_NOZORDER
                    )
                except:
                    pass
                try:
                    autoit.win_activate(window_spec)
                except Exception:
                    win32gui.ShowWindow(hwnd, 9)
                    win32gui.SetForegroundWindow(hwnd)

                time.sleep(0.15)

                try:
                    autoit.win_maximize(window_spec)
                except Exception:
                    win32gui.ShowWindow(hwnd, 3)

                time.sleep(0.15)
                for _ in range(max(1, int(press_count))):
                    if self.anti_afk_stop_event.is_set():
                        break
                    self._anti_afk_perform_action(action_key)
                    time.sleep(0.15)

                try:
                    import win32con
                    win32gui.SetWindowPos(
                        hwnd, 0,
                        -32000, -32000, 0, 0,
                        win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                    )
                    win32gui.ShowWindow(hwnd, 8)
                except:
                    try:
                        autoit.win_minimize(window_spec)
                    except Exception:
                        win32gui.ShowWindow(hwnd, 6)

                time.sleep(0.1)
            except Exception as e:
                print(f"[Anti-AFK] Error on window {hwnd}: {e}")

        if original_hwnd and win32gui.IsWindow(original_hwnd):
            try:
                original_spec = f"[HANDLE:0x{original_hwnd:08X}]"
                autoit.win_activate(original_spec)
            except Exception:
                try:
                    win32gui.SetForegroundWindow(original_hwnd)
                except Exception:
                    pass

    def _anti_afk_perform_action(self, action_key):
        mouse_actions = {
            "lmb": "left",
            "rmb": "right",
            "mmb": "middle",
        }

        if action_key in mouse_actions:
            button = mouse_actions[action_key]
            autoit.mouse_down(button)
            time.sleep(0.1)
            autoit.mouse_up(button)
            return

        if action_key == "scroll_up":
            autoit.mouse_wheel("up", 1)
            return

        if action_key == "scroll_down":
            autoit.mouse_wheel("down", 1)
            return

        autoit.send(f"{{{action_key.upper()} down}}")
        time.sleep(0.1)
        autoit.send(f"{{{action_key.upper()} up}}")
    
    def send_key_to_roblox_windows(self, action):
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            
            KEYEVENTF_KEYUP = 0x0002
            SW_RESTORE = 9
            SW_MINIMIZE = 6
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004
            MOUSEEVENTF_RIGHTDOWN = 0x0008
            MOUSEEVENTF_RIGHTUP = 0x0010
            
            vk_codes = {
                'w': 0x57, 'a': 0x41, 's': 0x53, 'd': 0x44,
                'space': 0x20, ' ': 0x20,
                'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12
            }
            
            is_mouse = action.upper() in ['LMB', 'RMB']
            
            if not is_mouse:
                action_lower = action.lower()
                if action_lower in vk_codes:
                    vk_code = vk_codes[action_lower]
                elif len(action) == 1:
                    vk_code = ord(action.upper())
                else:
                    print(f"[Anti-AFK] Unknown action: {action}")
                    return
            
            roblox_pids = set()
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == 'robloxplayerbeta.exe':
                        pid = proc.info['pid']
                        if self._is_valid_roblox_game_client(pid, 'robloxplayerbeta.exe'):
                            roblox_pids.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if not roblox_pids:
                return
            
            roblox_windows = []
            
            def enum_windows_callback(hwnd, lParam):
                if user32.IsWindowVisible(hwnd):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value in roblox_pids:
                        roblox_windows.append((hwnd, pid.value))
                return True
            
            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)
            
            if not roblox_windows:
                return
            
            original_hwnd = user32.GetForegroundWindow()
            current_thread_id = kernel32.GetCurrentThreadId()
            
            for hwnd, pid in roblox_windows:
                try:
                    was_minimized = user32.IsIconic(hwnd)
                    if was_minimized:
                        try:
                            import win32con
                            user32.SetWindowPos(
                                hwnd, 0,
                                100, 100, 0, 0,
                                win32con.SWP_NOSIZE | win32con.SWP_NOZORDER
                            )
                        except:
                            pass
                        user32.ShowWindow(hwnd, SW_RESTORE)
                        time.sleep(0.05)
                    
                    target_thread_id = user32.GetWindowThreadProcessId(hwnd, None)
                    user32.AttachThreadInput(current_thread_id, target_thread_id, True)
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(current_thread_id, target_thread_id, False)
                    time.sleep(0.1)
                    
                    if is_mouse:
                        if action.upper() == 'LMB':
                            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                            time.sleep(0.05)
                            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        elif action.upper() == 'RMB':
                            user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                            time.sleep(0.05)
                            user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                    else:
                        scan_code = user32.MapVirtualKeyW(vk_code, 0)
                        user32.keybd_event(vk_code, scan_code, 0, 0)
                        time.sleep(0.05)
                        user32.keybd_event(vk_code, scan_code, KEYEVENTF_KEYUP, 0)
                    
                    if was_minimized:
                        try:
                            import win32con
                            user32.SetWindowPos(
                                hwnd, 0,
                                -32000, -32000, 0, 0,
                                win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                            )
                            user32.ShowWindow(hwnd, 8)
                        except:
                            user32.ShowWindow(hwnd, SW_MINIMIZE)
                    
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"[Anti-AFK] Error on PID {pid}: {e}")
            
            if original_hwnd:
                try:
                    prev_thread_id = user32.GetWindowThreadProcessId(original_hwnd, None)
                    user32.AttachThreadInput(current_thread_id, prev_thread_id, True)
                    user32.BringWindowToTop(original_hwnd)
                    user32.SetForegroundWindow(original_hwnd)
                    user32.AttachThreadInput(current_thread_id, prev_thread_id, False)
                except:
                    pass
            
        except Exception as e:
            print(f"[Anti-AFK] Failed to send action: {e}")
    
    def send_key_to_roblox_windows_staggered(self, action, window_timers, current_time):
        """Send key presses to Roblox windows"""
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            
            vk_codes = {
                'w': 0x57, 'a': 0x41, 's': 0x53, 'd': 0x44,
                'space': 0x20, ' ': 0x20,
                'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12
            }
            
            KEYEVENTF_KEYUP = 0x0002
            SW_RESTORE = 9
            SW_MINIMIZE = 6
            
            is_mouse = action.upper() in ['LMB', 'RMB']
            
            if not is_mouse:
                action_lower = action.lower()
                if action_lower in vk_codes:
                    vk_code = vk_codes[action_lower]
                elif len(action) == 1:
                    vk_code = ord(action.upper())
                else:
                    print(f"[Anti-AFK] Unknown action: {action}")
                    return
            
            roblox_windows = []
            
            roblox_pids = set()
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == 'robloxplayerbeta.exe':
                        pid = proc.info['pid']
                        if self._is_valid_roblox_game_client(pid, 'robloxplayerbeta.exe'):
                            roblox_pids.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if not roblox_pids:
                print("[Anti-AFK] No RobloxPlayerBeta.exe processes found")
                return
            
            def enum_windows_callback(hwnd, lParam):
                if user32.IsWindowVisible(hwnd):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value in roblox_pids:
                        roblox_windows.append(hwnd)
                return True
            
            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)
            
            if not roblox_windows:
                print("[Anti-AFK] No Roblox game windows found")
                return
            
            original_hwnd = user32.GetForegroundWindow()
            current_thread_id = kernel32.GetCurrentThreadId()
            
            for idx, hwnd in enumerate(roblox_windows):
                try:
                    was_minimized = user32.IsIconic(hwnd)
                    if was_minimized:
                        try:
                            import win32con
                            user32.SetWindowPos(
                                hwnd, 0,
                                100, 100, 0, 0,
                                win32con.SWP_NOSIZE | win32con.SWP_NOZORDER
                            )
                        except:
                            pass
                        user32.ShowWindow(hwnd, SW_RESTORE)
                        time.sleep(0.05)
                    
                    user32.SetForegroundWindow(hwnd)
                    time.sleep(0.05)
                    
                    for repeat in range(3):
                        if is_mouse:
                            MOUSEEVENTF_LEFTDOWN = 0x0002
                            MOUSEEVENTF_LEFTUP = 0x0004
                            MOUSEEVENTF_RIGHTDOWN = 0x0008
                            MOUSEEVENTF_RIGHTUP = 0x0010
                            
                            if action.upper() == 'LMB':
                                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                time.sleep(0.015)
                                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            elif action.upper() == 'RMB':
                                user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                                time.sleep(0.015)
                                user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                        else:
                            scan_code = user32.MapVirtualKeyW(vk_code, 0)
                            user32.keybd_event(vk_code, scan_code, 0, 0)
                            time.sleep(0.015)
                            user32.keybd_event(vk_code, scan_code, KEYEVENTF_KEYUP, 0)
                    
                    print(f"[Anti-AFK] Sent '{action}' to Roblox instance {idx + 1}")
                    
                    if was_minimized:
                        try:
                            import win32con
                            user32.SetWindowPos(
                                hwnd, 0,
                                -32000, -32000, 0, 0,
                                win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                            )
                            user32.ShowWindow(hwnd, 8)
                        except:
                            user32.ShowWindow(hwnd, SW_MINIMIZE)
                    
                except Exception as e:
                    print(f"[Anti-AFK] Error on instance {idx + 1}: {e}")
            
            if original_hwnd:
                prev_thread_id = user32.GetWindowThreadProcessId(original_hwnd, None)
                user32.AttachThreadInput(current_thread_id, prev_thread_id, True)
                user32.BringWindowToTop(original_hwnd)
                user32.SetForegroundWindow(original_hwnd)
                user32.AttachThreadInput(current_thread_id, prev_thread_id, False)
            
        except Exception as e:
            print(f"[Anti-AFK] Failed: {e}")
            traceback.print_exc()
    
    def apply_and_lock_roblox_settings(self):
        """Apply local Roblox settings and lock file"""
        try:
            local_settings_path = os.path.join(self.data_folder, "roblox_settings.xml")
            roblox_settings_path = os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "Roblox",
                "GlobalBasicSettings_13.xml"
            )
            
            if not os.path.exists(local_settings_path):
                if os.path.exists(roblox_settings_path):
                    shutil.copy2(roblox_settings_path, local_settings_path)
                    print(f"[INFO] Created local Roblox settings file")
                else:
                    print(f"[WARNING] Roblox settings file not found, skipping auto-apply")
                    return
            
            try:
                os.chmod(roblox_settings_path, stat.S_IWRITE | stat.S_IREAD)
            except:
                pass
            
            shutil.copy2(local_settings_path, roblox_settings_path)
            print(f"[INFO] Applied local settings to Roblox")
            
            os.chmod(roblox_settings_path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            print(f"[INFO] Locked Roblox settings to read-only")
            
        except Exception as e:
            print(f"[ERROR] Failed to apply and lock Roblox settings: {e}")
    
    def open_roblox_settings_window(self):
        """Open Roblox Settings window to view/edit GlobalBasicSettings_13.xml"""
        settings_window = tk.Toplevel(self.root)
        self.apply_window_icon(settings_window)
        settings_window.title("Roblox Settings")
        settings_window.geometry("500x400")
        settings_window.configure(bg=self.BG_DARK)
        settings_window.resizable(False, False)
        settings_window.minsize(600, 400)
        
        if self.settings.get("enable_topmost", False):
            settings_window.attributes("-topmost", True)
        
        settings_window.transient(self.root)
        
        roblox_settings_path = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Roblox",
            "GlobalBasicSettings_13.xml"
        )
        
        local_settings_path = os.path.join(self.data_folder, "roblox_settings.xml")
        
        settings_data = {}
        xml_tree = None
        
        def ensure_local_settings_file():
            """Create local settings file if it doesn't exist by copying from Roblox"""
            if not os.path.exists(local_settings_path):
                if os.path.exists(roblox_settings_path):
                    try:
                        shutil.copy2(roblox_settings_path, local_settings_path)
                        print(f"[INFO] Created local Roblox settings file: {local_settings_path}")
                    except Exception as e:
                        print(f"[ERROR] Failed to create local settings file: {e}")
        
        def parse_settings():
            """Parse the local XML settings file"""
            nonlocal settings_data, xml_tree
            settings_data.clear()
            
            ensure_local_settings_file()
            
            if not os.path.exists(local_settings_path):
                return False
            
            try:
                xml_tree = ET.parse(local_settings_path)
                root = xml_tree.getroot()
                
                properties = root.find(".//Properties")
                if properties is None:
                    return False
                
                for child in properties:
                    tag = child.tag
                    name = child.get("name", "")
                    
                    if name:
                        if tag == "Vector2":
                            x_elem = child.find("X")
                            y_elem = child.find("Y")
                            value = f"{x_elem.text if x_elem is not None else '0'}, {y_elem.text if y_elem is not None else '0'}"
                        else:
                            value = child.text if child.text else ""
                        
                        settings_data[name] = {
                            "type": tag,
                            "value": value,
                            "element": child
                        }
                
                return True
            except Exception as e:
                print(f"[ERROR] Failed to parse settings: {e}")
                return False
        
        def refresh_list(filter_text=""):
            """Refresh the settings list, optionally filtering by search text"""
            settings_list.delete(0, tk.END)
            
            for name, data in sorted(settings_data.items()):
                if filter_text.lower() in name.lower() or filter_text.lower() in str(data["value"]).lower():
                    display = f"{name}: {data['value']}"
                    if len(display) > 60:
                        display = display[:57] + "..."
                    settings_list.insert(tk.END, display)
        
        def on_search(*args):
            """Filter list based on search input"""
            refresh_list(search_var.get())
        
        def on_select(event):
            """Handle list selection"""
            selection = settings_list.curselection()
            if not selection:
                return
            
            selected_text = settings_list.get(selection[0])
            selected_name = selected_text.split(":")[0]
            
            if selected_name in settings_data:
                data = settings_data[selected_name]
                selected_name_label.config(text=f"Selected: {selected_name}")
                type_label.config(text=f"Type: {data['type']}")
                value_entry.delete(0, tk.END)
                value_entry.insert(0, data["value"])
        
        def set_value():
            """Set value locally (in memory)"""
            selection = settings_list.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a setting first.")
                return
            
            selected_text = settings_list.get(selection[0])
            selected_name = selected_text.split(":")[0]
            new_value = value_entry.get()
            
            if selected_name in settings_data:
                data = settings_data[selected_name]
                element = data["element"]
                
                if data["type"] == "Vector2":
                    parts = new_value.split(",")
                    if len(parts) == 2:
                        x_elem = element.find("X")
                        y_elem = element.find("Y")
                        if x_elem is not None:
                            x_elem.text = parts[0].strip()
                        if y_elem is not None:
                            y_elem.text = parts[1].strip()
                else:
                    element.text = new_value
                
                settings_data[selected_name]["value"] = new_value
                save_settings_to_local()
                refresh_list(search_var.get())
                messagebox.showinfo("Set", f"Value for '{selected_name}' set and saved to local file.")
        
        def refresh_settings():
            """Reload settings from local XML file"""
            if parse_settings():
                refresh_list(search_var.get())
                messagebox.showinfo("Refreshed", "Settings reloaded from local file.")
            else:
                messagebox.showerror("Error", f"Could not load settings from:\n{local_settings_path}")
        
        def save_settings_to_local():
            """Save settings to local XML file"""
            nonlocal xml_tree
            if xml_tree is None:
                messagebox.showerror("Error", "No settings loaded to save.")
                return False
            
            try:
                xml_tree.write(local_settings_path, encoding="utf-8", xml_declaration=True)
                print(f"[INFO] Settings saved to local file: {local_settings_path}")
                return True
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save settings: {e}")
                return False
        
        def apply_settings_to_roblox():
            """Apply local settings to Roblox's GlobalBasicSettings_13.xml"""
            if not os.path.exists(local_settings_path):
                messagebox.showerror("Error", "No local settings file found.")
                return False
            
            try:
                try:
                    os.chmod(roblox_settings_path, stat.S_IWRITE | stat.S_IREAD)
                except:
                    pass
                
                shutil.copy2(local_settings_path, roblox_settings_path)
                print(f"[INFO] Applied settings to Roblox: {roblox_settings_path}")
                return True
            except Exception as e:
                messagebox.showerror("Error", f"Failed to apply settings: {e}")
                return False
        
        def lock_roblox_settings():
            """Lock Roblox settings file to read-only"""
            if not os.path.exists(roblox_settings_path):
                print(f"[WARNING] Roblox settings file not found: {roblox_settings_path}")
                return False
            
            try:
                os.chmod(roblox_settings_path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
                print(f"[INFO] Locked Roblox settings to read-only")
                return True
            except Exception as e:
                print(f"[ERROR] Failed to lock settings: {e}")
                return False
        
        def unlock_roblox_settings():
            """Unlock Roblox settings file"""
            if not os.path.exists(roblox_settings_path):
                print(f"[WARNING] Roblox settings file not found: {roblox_settings_path}")
                return False
            
            try:
                os.chmod(roblox_settings_path, stat.S_IWRITE | stat.S_IREAD)
                print(f"[INFO] Unlocked Roblox settings (writable)")
                return True
            except Exception as e:
                print(f"[ERROR] Failed to unlock settings: {e}")
                return False
        
        def toggle_lock_settings():
            """Handle Lock Settings checkbox toggle"""
            enabled = lock_settings_var.get()
            self.settings["lock_roblox_settings"] = enabled
            self.save_settings()
            
            if enabled:
                if save_settings_to_local():
                    if apply_settings_to_roblox():
                        if lock_roblox_settings():
                            messagebox.showinfo("Locked", "Settings applied and locked to read-only!")
                        else:
                            messagebox.showwarning("Warning", "Settings applied but failed to lock.")
            else:
                if unlock_roblox_settings():
                    messagebox.showinfo("Unlocked", "Roblox settings file is now writable!")
        
        main_frame = ttk.Frame(settings_window, style="Dark.TFrame")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        lock_settings_var = tk.BooleanVar(value=self.settings.get("lock_roblox_settings", False))
        
        search_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        search_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_frame, text="Search:", style="Dark.TLabel").pack(side="left", padx=(0, 5))
        
        search_var = tk.StringVar()
        search_var.trace("w", on_search)
        search_entry = ttk.Entry(search_frame, textvariable=search_var, style="Dark.TEntry")
        search_entry.pack(side="left", fill="x", expand=True)
        
        content_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        content_frame.pack(fill="both", expand=True)
        
        list_frame = ttk.Frame(content_frame, style="Dark.TFrame")
        list_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ttk.Label(list_frame, text="Roblox Settings", style="Dark.TLabel", 
                  font=(self.FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(0, 5))
        
        list_container = ttk.Frame(list_frame, style="Dark.TFrame")
        list_container.pack(fill="both", expand=True)
        
        settings_list = tk.Listbox(
            list_container,
            bg=self.BG_MID,
            fg=self.FG_TEXT,
            selectbackground=self.FG_ACCENT,
            selectforeground="white",
            font=(self.FONT_FAMILY, 9),
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightcolor=self.BG_LIGHT,
            highlightbackground=self.BG_LIGHT,
            exportselection=False
        )
        settings_list.pack(side="left", fill="both", expand=True)
        settings_list.bind("<<ListboxSelect>>", on_select)
        
        list_scrollbar = ttk.Scrollbar(list_container, command=settings_list.yview)
        list_scrollbar.pack(side="right", fill="y")
        settings_list.config(yscrollcommand=list_scrollbar.set)
        
        edit_frame = ttk.Frame(content_frame, style="Dark.TFrame", width=200)
        edit_frame.pack(side="right", fill="y", padx=(10, 0))
        edit_frame.pack_propagate(False)
        
        ttk.Label(edit_frame, text="Edit Setting", style="Dark.TLabel",
                  font=(self.FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(0, 10))
        
        selected_name_label = ttk.Label(edit_frame, text="Selected: (none)", style="Dark.TLabel",
                                         font=(self.FONT_FAMILY, 9))
        selected_name_label.pack(anchor="w", pady=(0, 5))
        
        type_label = ttk.Label(edit_frame, text="Type: -", style="Dark.TLabel",
                               font=(self.FONT_FAMILY, 9))
        type_label.pack(anchor="w", pady=(0, 10))
        
        ttk.Label(edit_frame, text="Set Value:", style="Dark.TLabel").pack(anchor="w", pady=(0, 5))
        
        value_entry = ttk.Entry(edit_frame, style="Dark.TEntry")
        value_entry.pack(fill="x", pady=(0, 10))
        
        ttk.Button(edit_frame, text="Set", style="Dark.TButton", command=set_value).pack(fill="x", pady=(0, 5))
        ttk.Button(edit_frame, text="Refresh", style="Dark.TButton", command=refresh_settings).pack(fill="x", pady=(0, 5))
        ttk.Button(edit_frame, text="Apply to Roblox", style="Dark.TButton", command=lambda: apply_settings_to_roblox() and messagebox.showinfo("Applied", "Settings applied to Roblox!")).pack(fill="x", pady=(0, 5))
        
        ttk.Checkbutton(
            edit_frame,
            text="Lock settings (auto-apply)",
            variable=lock_settings_var,
            command=toggle_lock_settings,
            style="Dark.TCheckbutton"
        ).pack(anchor="w", pady=(10, 0))

        if parse_settings():
            refresh_list()
        else:
            settings_list.insert(tk.END, "Could not load settings file.")
            settings_list.insert(tk.END, "Make sure Roblox has been run at least once.")

    def setup_dashboard_tab(self):
        self.db_header = ttk.Frame(self.dashboard_tab, style="Dark.TFrame")
        self.db_header.pack(fill="x", padx=2, pady=(2, 2))
        self.db_title = ttk.Label(self.db_header, text="Live Telemetry Dashboard", style="Dark.TLabel", font=(self.FONT_FAMILY, 14, "bold"))
        self.db_title.pack(side="left")
        self.db_stats = ttk.Label(self.db_header, text="Active Sessions: 0", style="Dark.TLabel", font=(self.FONT_FAMILY, 10))
        self.db_stats.pack(side="right", pady=4)

        self.db_webhook_frame = ttk.Frame(self.dashboard_tab, style="Dark.TFrame")
        self.db_webhook_frame.pack(fill="x", padx=2, pady=(2, 4))

        self.db_webhook_lbl = ttk.Label(self.db_webhook_frame, text="Webhook:", style="Dark.TLabel", font=(self.FONT_FAMILY, 9))
        self.db_webhook_lbl.grid(row=0, column=0, padx=2, pady=(2, 4), sticky="w")

        self.db_webhook_entry = ttk.Entry(self.db_webhook_frame, style="Dark.TEntry", width=18)
        self.db_webhook_entry.grid(row=0, column=1, padx=2, pady=(2, 4), sticky="w", ipady=2)
        self.db_webhook_entry.insert(0, self.settings.get("dashboard_webhook_url", ""))

        def save_db_webhook(event=None):
            self.settings["dashboard_webhook_url"] = self.db_webhook_entry.get().strip()
            self.save_settings(force_immediate=True)

        self.db_webhook_entry.bind("<FocusOut>", save_db_webhook)
        self.db_webhook_entry.bind("<KeyRelease>", save_db_webhook)

        self.db_webhook_btn = ttk.Button(self.db_webhook_frame, text="Send Active Report", style="Dark.TButton", command=self.send_active_report_webhook)
        self.db_webhook_btn.grid(row=1, column=0, columnspan=4, padx=2, pady=(2, 4), sticky="ew")

        self.db_auto_var = tk.BooleanVar(value=self.settings.get("dashboard_auto_report", False))
        def toggle_db_auto():
            self.settings["dashboard_auto_report"] = self.db_auto_var.get()
            self.save_settings(force_immediate=True)

        self.db_auto_cb = ttk.Checkbutton(
            self.db_webhook_frame,
            text="Auto-Report",
            variable=self.db_auto_var,
            command=toggle_db_auto,
            style="Dark.TCheckbutton"
        )
        self.db_auto_cb.grid(row=0, column=2, padx=2, pady=(2, 4), sticky="w")

        self.db_interval_spin = tk.Spinbox(
            self.db_webhook_frame,
            from_=5,
            to=86400,
            width=3,
            bg=self.BG_DARK,
            fg=self.FG_TEXT,
            buttonbackground=self.BG_MID,
            selectbackground=self.FG_ACCENT,
            highlightthickness=0,
            bd=0,
            font=(self.FONT_FAMILY, 9)
        )
        self.db_interval_spin.grid(row=0, column=3, padx=2, pady=(2, 4), sticky="w")
        self.db_interval_spin.delete(0, tk.END)
        self.db_interval_spin.insert(0, str(self.settings.get("dashboard_report_interval", 60)))

        def save_db_interval(event=None):
            try:
                val = int(self.db_interval_spin.get().strip())
                if val >= 5:
                    self.settings["dashboard_report_interval"] = val
                    self.save_settings(force_immediate=True)
            except:
                pass

        self.db_interval_spin.bind("<FocusOut>", save_db_interval)
        self.db_interval_spin.bind("<KeyRelease>", save_db_interval)

        self.db_canvas_frame = ttk.Frame(self.dashboard_tab, style="Dark.TFrame")
        self.db_canvas_frame.pack(fill="both", expand=True, padx=2, pady=(0, 2))
        self.db_canvas = tk.Canvas(self.db_canvas_frame, bg=self.BG_DARK, highlightthickness=0)
        self.db_scrollbar = ttk.Scrollbar(self.db_canvas_frame, orient="vertical", command=self.db_canvas.yview)
        self.db_cards_frame = ttk.Frame(self.db_canvas, style="Dark.TFrame")
        self.db_cards_frame.bind("<Configure>", lambda e: self.db_canvas.configure(scrollregion=self.db_canvas.bbox("all")))
        self.db_canvas.create_window((0, 0), window=self.db_cards_frame, anchor="nw")
        self.db_canvas.configure(yscrollcommand=self.db_scrollbar.set)
        self.db_canvas.pack(side="left", fill="both", expand=True)
        self.db_scrollbar.pack(side="right", fill="y")
        def _on_mousewheel(event):
            self.db_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.db_canvas.bind("<Enter>", lambda e: self.db_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.db_canvas.bind("<Leave>", lambda e: self.db_canvas.unbind_all("<MouseWheel>"))
        self.db_cards = {}
        self.db_placeholder = ttk.Frame(self.db_cards_frame, style="Dark.TFrame")
        self.db_placeholder.pack(fill="both", expand=True, pady=40)
        self.db_placeholder_title = ttk.Label(self.db_placeholder, text="No Active Roblox Sessions", style="Dark.TLabel", font=(self.FONT_FAMILY, 12, "bold"))
        self.db_placeholder_title.pack(anchor="center")
        self.db_placeholder_sub = ttk.Label(self.db_placeholder, text="Launch accounts from the Manager tab to begin monitoring.", style="Dark.TLabel", font=(self.FONT_FAMILY, 9))
        self.db_placeholder_sub.pack(anchor="center", pady=5)

    def update_dashboard(self):
        try:
            unique_sessions = {}
            counts = {}
            for entry in self.instances_data:
                username = entry.get("username")
                if not username:
                    continue
                counts[username] = counts.get(username, 0) + 1
            processed_counts = {}
            for entry in self.instances_data:
                username = entry.get("username")
                if not username:
                    continue
                pid = entry.get("pid")
                user_id = entry.get("user_id")
                create_time = entry.get("create_time", 0)
                if counts[username] > 1:
                    processed_counts[username] = processed_counts.get(username, 0) + 1
                    display_name = f"{username} #{processed_counts[username]}"
                else:
                    display_name = username
                unique_sessions[display_name] = {
                    "pid": pid,
                    "username": username,
                    "display_name": display_name,
                    "user_id": user_id,
                    "create_time": create_time,
                    "memory_mb": entry.get("memory_mb", 0),
                    "cpu_percent": entry.get("cpu_percent", 0.0),
                    "avatar_url": entry.get("avatar_url")
                }
            self.db_stats.config(text=f"Active Sessions: {len(unique_sessions)}")
            if not unique_sessions:
                self.db_placeholder.pack(fill="both", expand=True, pady=40)
            else:
                self.db_placeholder.pack_forget()
            for dname in list(self.db_cards.keys()):
                if dname not in unique_sessions:
                    self.db_cards[dname]["frame"].destroy()
                    del self.db_cards[dname]
            for dname, data in unique_sessions.items():
                pid = data["pid"]
                username = data["username"]
                user_id = data["user_id"]
                create_time = data["create_time"]
                avatar_url = data["avatar_url"]
                place_id = "N/A"
                game_name = ""
                status_color = "#2ECC71"
                status_name = "Active"
                if hasattr(self, 'presence_statuses') and username in self.presence_statuses:
                    presence = self.presence_statuses[username]
                    status = presence.get('status', 0)
                    if status == 2:
                        status_name = "InGame"
                        status_color = "#2ECC71"
                        place_id = presence.get('place_id', "Unknown")
                        if place_id and place_id != "Unknown":
                            cached_name = RobloxAPI.get_game_name(str(place_id))
                            if cached_name:
                                game_name = cached_name
                            else:
                                game_name = f"Place ID: {place_id}"
                    elif status == 1:
                        status_name = "Online"
                        status_color = "#F1C40F"
                    elif status == 3:
                        status_name = "InStudio"
                        status_color = "#9B59B6"
                uptime_str = "00:00:00"
                if create_time:
                    try:
                        elapsed = int(time.time() - create_time)
                        h = elapsed // 3600
                        m = (elapsed % 3600) // 60
                        s = elapsed % 60
                        uptime_str = f"{h:02d}:{m:02d}:{s:02d}"
                    except:
                        pass
                mem_val = data.get("memory_mb", 0.0)
                stats_str = f"RAM: {mem_val:.1f} MB"
                if dname not in self.db_cards:
                    card_frame = tk.Frame(self.db_cards_frame, bg=self.BG_MID, highlightbackground=self.BG_LIGHT, highlightthickness=1, bd=0)
                    card_frame.pack(fill="x", pady=2, padx=5)
                    inner = tk.Frame(card_frame, bg=self.BG_MID)
                    inner.pack(fill="both", expand=True, padx=10, pady=8)
                    avatar_label = tk.Label(inner, bg=self.BG_MID)
                    avatar_label.pack(side="left", padx=(0, 10))
                    if user_id and user_id in self.instances_cache["user_id_to_photo"]:
                        photo = self.instances_cache["user_id_to_photo"][user_id]
                        avatar_label.config(image=photo)
                        avatar_label.image = photo
                    else:
                        avatar_label.config(text="...", font=(self.FONT_FAMILY, 14), fg=self.FG_TEXT)
                        def download_db_avatar(uid, url, lbl):
                            try:
                                if url:
                                    response = requests.get(url, timeout=5)
                                    if response.status_code == 200:
                                        img_data = BytesIO(response.content)
                                        img = Image.open(img_data)
                                        img = img.resize((40, 40), Image.Resampling.LANCZOS)
                                        photo = ImageTk.PhotoImage(img)
                                        self.instances_cache["user_id_to_photo"][uid] = photo
                                        def update_lbl():
                                            try:
                                                if lbl.winfo_exists():
                                                    lbl.config(image=photo)
                                                    lbl.image = photo
                                            except:
                                                pass
                                        self.root.after(0, update_lbl)
                            except:
                                pass
                        if user_id and avatar_url:
                            threading.Thread(target=download_db_avatar, args=(user_id, avatar_url, avatar_label), daemon=True).start()
                    id_frame = tk.Frame(inner, bg=self.BG_MID)
                    id_frame.pack(side="left", fill="y", padx=(0, 15))
                    name_lbl = tk.Label(id_frame, text=dname, bg=self.BG_MID, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 10, "bold"), anchor="w")
                    name_lbl.pack(anchor="w")
                    uid_lbl = tk.Label(id_frame, text=f"ID: {user_id or 'Unknown'}", bg=self.BG_MID, fg="#888888", font=(self.FONT_FAMILY, 8), anchor="w")
                    uid_lbl.pack(anchor="w")
                    stats_lbl = tk.Label(id_frame, text=stats_str, bg=self.BG_MID, fg="#888888", font=(self.FONT_FAMILY, 8), anchor="w")
                    stats_lbl.pack(anchor="w")
                    game_frame = tk.Frame(inner, bg=self.BG_MID)
                    game_frame.pack(side="left", fill="both", expand=True)
                    game_lbl = tk.Label(game_frame, text=game_name, bg=self.BG_MID, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 9), anchor="w", wraplength=150)
                    game_lbl.pack(anchor="w")
                    status_frame = tk.Frame(inner, bg=self.BG_MID)
                    status_frame.pack(side="right", fill="y", padx=(5, 0))
                    time_lbl = tk.Label(status_frame, text=uptime_str, bg=self.BG_MID, fg=self.FG_ACCENT, font=(self.FONT_FAMILY, 11, "bold"), anchor="e")
                    time_lbl.pack(anchor="e")
                    indicator_frame = tk.Frame(status_frame, bg=self.BG_MID)
                    indicator_frame.pack(anchor="e", pady=(2, 0))
                    dot_lbl = tk.Label(indicator_frame, text="●", bg=self.BG_MID, fg=status_color, font=(self.FONT_FAMILY, 10))
                    dot_lbl.pack(side="left", padx=(0, 4))
                    lbl_text = tk.Label(indicator_frame, text=status_name, bg=self.BG_MID, fg="#888888", font=(self.FONT_FAMILY, 8))
                    lbl_text.pack(side="left")
                    self.db_cards[dname] = {
                        "frame": card_frame,
                        "time_label": time_lbl,
                        "game_label": game_lbl,
                        "stats_label": stats_lbl,
                        "dot_label": dot_lbl,
                        "status_label": lbl_text,
                        "name_label": name_lbl
                    }
                else:
                    card_ref = self.db_cards[dname]
                    card_ref["time_label"].config(text=uptime_str)
                    card_ref["game_label"].config(text=game_name)
                    card_ref["stats_label"].config(text=stats_str)
                    card_ref["dot_label"].config(fg=status_color)
                    card_ref["status_label"].config(text=status_name)
        except Exception as e:
            print(f"[ERROR] Error updating dashboard: {e}")
        self.root.after(1000, self.update_dashboard)

    def pulse_telemetry_indicators(self):
        if not hasattr(self, 'pulse_state'):
            self.pulse_state = True
        self.pulse_state = not self.pulse_state
        for dname, data in getattr(self, 'db_cards', {}).items():
            try:
                dot = data.get("dot_label")
                status = data.get("status_label")
                if dot and status and dot.winfo_exists() and status.winfo_exists():
                    status_text = status.cget("text").strip()
                    if status_text in ("InGame", "Active", "In-Game"):
                        color = "#2ECC71" if self.pulse_state else "#1B5E20"
                        dot.config(fg=color)
                    elif status_text == "Online":
                        color = "#F1C40F" if self.pulse_state else "#9A7D0A"
                        dot.config(fg=color)
            except:
                pass
        self.root.after(500, self.pulse_telemetry_indicators)

    def start_presence_tracker(self):
        if hasattr(self, 'presence_tracker_thread') and self.presence_tracker_thread and self.presence_tracker_thread.is_alive():
            return
        self.presence_tracker_stop = threading.Event()
        self.presence_alerted_accounts = set()
        self.presence_tracker_thread = threading.Thread(target=self._presence_tracker_worker, daemon=True)
        self.presence_tracker_thread.start()

    def stop_presence_tracker(self):
        if hasattr(self, 'presence_tracker_thread') and self.presence_tracker_thread:
            self.presence_tracker_stop.set()
            self.presence_tracker_thread = None

    def _presence_tracker_worker(self):
        poll_interval = 25
        while not self.presence_tracker_stop.is_set():
            try:
                running_accounts = []
                active_usernames = set()
                for entry in self.instances_data:
                    username = entry.get("username")
                    user_id = entry.get("user_id")
                    if username and user_id:
                        running_accounts.append((username, user_id))
                        active_usernames.add(username)
                for username in list(self.presence_alerted_accounts):
                    if username not in active_usernames:
                        self.presence_alerted_accounts.remove(username)
                for username, user_id in running_accounts:
                    if self.presence_tracker_stop.is_set():
                        break
                    account_data = self.manager.accounts.get(username)
                    cookie = account_data.get("cookie") if isinstance(account_data, dict) else None
                    if not cookie:
                        continue
                    try:
                        presence = RobloxAPI.get_player_presence(user_id, cookie)
                        if presence:
                            self.presence_statuses[username] = presence
                            status = presence.get('status', 0)
                            if status != 2:
                                if username not in self.presence_alerted_accounts:
                                    self.presence_alerted_accounts.add(username)
                            else:
                                if username in self.presence_alerted_accounts:
                                    self.presence_alerted_accounts.remove(username)
                        else:
                            self.presence_statuses[username] = {"status": 0}
                    except Exception as e:
                        print(f"[ERROR] Error checking presence for {username}: {e}")
                    self.presence_tracker_stop.wait(2.0)
            except Exception as e:
                print(f"[ERROR] Presence tracker worker loop error: {e}")
            self.presence_tracker_stop.wait(poll_interval)

    def setup_watchlist_tab(self):
        self.wl_header = ttk.Frame(self.watchlist_tab, style="Dark.TFrame")
        self.wl_header.pack(fill="x", padx=2, pady=(2, 2))
        self.wl_title = ttk.Label(self.wl_header, text="Account Presence Watchlist", style="Dark.TLabel", font=(self.FONT_FAMILY, 14, "bold"))
        self.wl_title.pack(side="left")
        self.wl_stats = ttk.Label(self.wl_header, text="Watched Accounts: 0", style="Dark.TLabel", font=(self.FONT_FAMILY, 10))
        self.wl_stats.pack(side="right", pady=4)

        self.wl_config_frame = ttk.Frame(self.watchlist_tab, style="Dark.TFrame")
        self.wl_config_frame.pack(fill="x", padx=2, pady=2)

        self.wl_webhook_lbl = ttk.Label(self.wl_config_frame, text="Webhook:", style="Dark.TLabel", font=(self.FONT_FAMILY, 9))
        self.wl_webhook_lbl.grid(row=0, column=0, padx=2, pady=2, sticky="w")

        self.wl_webhook_entry = ttk.Entry(self.wl_config_frame, style="Dark.TEntry", width=28)
        self.wl_webhook_entry.grid(row=0, column=1, columnspan=2, padx=2, pady=2, sticky="w", ipady=2)
        self.wl_webhook_entry.insert(0, self.settings.get("watchlist_webhook_url", ""))

        def save_wl_webhook(event=None):
            self.settings["watchlist_webhook_url"] = self.wl_webhook_entry.get().strip()
            self.save_settings(force_immediate=True)

        self.wl_webhook_entry.bind("<FocusOut>", save_wl_webhook)
        self.wl_webhook_entry.bind("<KeyRelease>", save_wl_webhook)

        self.wl_ping_lbl = ttk.Label(self.wl_config_frame, text="Ping ID:", style="Dark.TLabel", font=(self.FONT_FAMILY, 9))
        self.wl_ping_lbl.grid(row=1, column=0, padx=2, pady=2, sticky="w")

        self.wl_ping_entry = ttk.Entry(self.wl_config_frame, style="Dark.TEntry", width=28)
        self.wl_ping_entry.grid(row=1, column=1, columnspan=2, padx=2, pady=2, sticky="w", ipady=2)
        self.wl_ping_entry.insert(0, self.settings.get("watchlist_ping_id", ""))

        def save_wl_ping(event=None):
            self.settings["watchlist_ping_id"] = self.wl_ping_entry.get().strip()
            self.save_settings(force_immediate=True)

        self.wl_ping_entry.bind("<FocusOut>", save_wl_ping)
        self.wl_ping_entry.bind("<KeyRelease>", save_wl_ping)

        self.wl_interval_lbl = ttk.Label(self.wl_config_frame, text="Interval:", style="Dark.TLabel", font=(self.FONT_FAMILY, 9))
        self.wl_interval_lbl.grid(row=2, column=0, padx=2, pady=2, sticky="w")

        self.wl_interval_spin = tk.Spinbox(
            self.wl_config_frame,
            from_=5,
            to=86400,
            width=5,
            bg=self.BG_DARK,
            fg=self.FG_TEXT,
            buttonbackground=self.BG_MID,
            selectbackground=self.FG_ACCENT,
            highlightthickness=0,
            bd=0,
            font=(self.FONT_FAMILY, 9)
        )
        self.wl_interval_spin.grid(row=2, column=1, padx=2, pady=2, sticky="w")
        self.wl_interval_spin.delete(0, tk.END)
        self.wl_interval_spin.insert(0, str(self.settings.get("watchlist_interval", 300)))

        def save_wl_interval(event=None):
            try:
                val = int(self.wl_interval_spin.get().strip())
                if val >= 5:
                    self.settings["watchlist_interval"] = val
                    self.save_settings(force_immediate=True)
            except:
                pass

        self.wl_interval_spin.bind("<FocusOut>", save_wl_interval)
        self.wl_interval_spin.bind("<KeyRelease>", save_wl_interval)

        self.wl_track_var = tk.BooleanVar(value=self.settings.get("watchlist_tracking_enabled", True))
        def toggle_wl_track():
            self.settings["watchlist_tracking_enabled"] = self.wl_track_var.get()
            self.save_settings(force_immediate=True)
            if not self.wl_track_var.get():
                if hasattr(self, 'watchlist_alerted_states'):
                    self.watchlist_alerted_states.clear()
                if hasattr(self, 'presence_alerted_accounts'):
                    self.presence_alerted_accounts.clear()

        self.wl_track_cb = ttk.Checkbutton(
            self.wl_config_frame,
            text="Enable Tracking",
            variable=self.wl_track_var,
            command=toggle_wl_track,
            style="Dark.TCheckbutton"
        )
        self.wl_track_cb.grid(row=2, column=2, padx=10, pady=2, sticky="w")

        self.wl_entry_lbl = ttk.Label(self.wl_config_frame, text="Account:", style="Dark.TLabel", font=(self.FONT_FAMILY, 9))
        self.wl_entry_lbl.grid(row=3, column=0, padx=2, pady=2, sticky="w")

        self.wl_entry = ttk.Entry(self.wl_config_frame, style="Dark.TEntry", width=16)
        self.wl_entry.grid(row=3, column=1, padx=2, pady=2, sticky="w", ipady=2)
        self.wl_entry.insert(0, "Username or ID...")
        self.wl_entry.bind("<FocusIn>", lambda e: self.wl_entry.delete(0, tk.END) if self.wl_entry.get() == "Username or ID..." else None)
        self.wl_entry.bind("<FocusOut>", lambda e: self.wl_entry.insert(0, "Username or ID...") if not self.wl_entry.get().strip() else None)
        self.wl_entry.bind("<Return>", lambda e: self.add_to_watchlist())

        self.wl_add_btn = ttk.Button(self.wl_config_frame, text="Add Account", style="Dark.TButton", command=self.add_to_watchlist)
        self.wl_add_btn.grid(row=3, column=2, padx=4, pady=2, sticky="w")

        self.wl_canvas_frame = ttk.Frame(self.watchlist_tab, style="Dark.TFrame")
        self.wl_canvas_frame.pack(fill="both", expand=True, padx=2, pady=(0, 2))
        
        self.wl_canvas = tk.Canvas(self.wl_canvas_frame, bg=self.BG_DARK, highlightthickness=0)
        self.wl_scrollbar = ttk.Scrollbar(self.wl_canvas_frame, orient="vertical", command=self.wl_canvas.yview)
        self.wl_list_frame = ttk.Frame(self.wl_canvas, style="Dark.TFrame")
        
        self.wl_list_frame.bind("<Configure>", lambda e: self.wl_canvas.configure(scrollregion=self.wl_canvas.bbox("all")))
        self.wl_canvas.create_window((0, 0), window=self.wl_list_frame, anchor="nw")
        self.wl_canvas.configure(yscrollcommand=self.wl_scrollbar.set)
        
        self.wl_canvas.pack(side="left", fill="both", expand=True)
        self.wl_scrollbar.pack(side="right", fill="y")
        
        def _on_wl_mousewheel(event):
            self.wl_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            
        self.wl_canvas.bind("<Enter>", lambda e: self.wl_canvas.bind_all("<MouseWheel>", _on_wl_mousewheel))
        self.wl_canvas.bind("<Leave>", lambda e: self.wl_canvas.unbind_all("<MouseWheel>"))

        self.wl_cards = {}
        self.refresh_watchlist_ui()

    def add_to_watchlist(self):
        query = self.wl_entry.get().strip()
        if not query or query == "Username or ID...":
            return
        
        self.wl_add_btn.config(state="disabled")
        self.wl_entry.config(state="disabled")

        def worker():
            try:
                if query.isdigit():
                    user_id = query
                    username = RobloxAPI.get_username_from_user_id(user_id) or f"User {user_id}"
                else:
                    user_id = RobloxAPI.get_user_id_from_username(query)
                    username = query

                if not user_id:
                    self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to resolve '{query}' to a valid Roblox User ID."))
                    return

                watchlist = self.settings.get("watchlist", [])
                if any(str(item.get("user_id")) == str(user_id) for item in watchlist):
                    self.root.after(0, lambda: messagebox.showwarning("Duplicate", f"Account '{username}' is already in the watchlist."))
                    return

                watchlist.append({
                    "user_id": str(user_id),
                    "username": username
                })
                self.settings["watchlist"] = watchlist
                self.save_settings(force_immediate=True)

                def clear_input():
                    self.wl_entry.delete(0, tk.END)
                    self.wl_entry.insert(0, "Username or ID...")

                self.root.after(0, self.refresh_watchlist_ui)
                self.root.after(0, clear_input)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"An error occurred: {e}"))
            finally:
                self.root.after(0, lambda: self.wl_add_btn.config(state="normal"))
                self.root.after(0, lambda: self.wl_entry.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_watchlist_ui(self):
        try:
            watchlist = self.settings.get("watchlist", [])
            self.wl_stats.config(text=f"Watched Accounts: {len(watchlist)}")
            
            for card in self.wl_cards.values():
                card.destroy()
            self.wl_cards.clear()

            if not watchlist:
                self.wl_empty_lbl = ttk.Label(self.wl_list_frame, text="Watchlist is empty. Add Roblox Usernames/IDs to track presence.", style="Dark.TLabel", font=(self.FONT_FAMILY, 9))
                self.wl_empty_lbl.pack(pady=40, anchor="center")
                self.wl_cards["_empty"] = self.wl_empty_lbl
                return

            wl_statuses = getattr(self, "watchlist_statuses", {})

            for item in watchlist:
                user_id = str(item.get("user_id"))
                username = item.get("username")
                
                card_frame = tk.Frame(self.wl_list_frame, bg=self.BG_MID, highlightbackground=self.BG_LIGHT, highlightthickness=1, bd=0)
                card_frame.pack(fill="x", pady=6, padx=5)
                self.wl_cards[user_id] = card_frame

                inner = tk.Frame(card_frame, bg=self.BG_MID)
                inner.pack(fill="both", expand=True, padx=10, pady=8)

                info_frame = tk.Frame(inner, bg=self.BG_MID)
                info_frame.pack(side="left", fill="y")
                
                name_lbl = tk.Label(info_frame, text=username, bg=self.BG_MID, fg=self.FG_TEXT, font=(self.FONT_FAMILY, 10, "bold"), anchor="w")
                name_lbl.pack(anchor="w")
                
                uid_lbl = tk.Label(info_frame, text=f"ID: {user_id}", bg=self.BG_MID, fg="#888888", font=(self.FONT_FAMILY, 8), anchor="w")
                uid_lbl.pack(anchor="w")

                status_name = wl_statuses.get(user_id, "Pending...")
                status_colors = {
                    "Offline": "#95A5A6",
                    "Online": "#F1C40F",
                    "InGame": "#2ECC71",
                    "InStudio": "#9B59B6",
                    "Pending...": "#888888"
                }
                scolor = status_colors.get(status_name, "#95A5A6")

                status_lbl = tk.Label(inner, text=status_name, bg=self.BG_MID, fg=scolor, font=(self.FONT_FAMILY, 9, "bold"))
                status_lbl.pack(side="left", padx=(20, 0))

                remove_btn = tk.Button(
                    inner,
                    text="Remove",
                    bg="#C0392B",
                    fg=self.FG_TEXT,
                    activebackground="#E74C3C",
                    activeforeground=self.FG_TEXT,
                    font=(self.FONT_FAMILY, 9, "bold"),
                    relief="flat",
                    bd=0,
                    highlightthickness=0,
                    padx=10,
                    pady=4,
                    command=lambda uid=user_id: self.remove_from_watchlist(uid)
                )
                remove_btn.pack(side="right", padx=(10, 0))
                
        except Exception as e:
            print(f"[ERROR] Failed to refresh watchlist UI: {e}")

    def remove_from_watchlist(self, user_id):
        watchlist = self.settings.get("watchlist", [])
        watchlist = [item for item in watchlist if str(item.get("user_id")) != str(user_id)]
        self.settings["watchlist"] = watchlist
        self.save_settings(force_immediate=True)
        
        uid_int = None
        try:
            uid_int = int(user_id)
        except:
            pass
        if uid_int in self.watchlist_alerted_states:
            del self.watchlist_alerted_states[uid_int]
        if str(user_id) in self.watchlist_alerted_states:
            del self.watchlist_alerted_states[str(user_id)]
            
        self.refresh_watchlist_ui()

    def start_watchlist_tracker(self):
        if hasattr(self, 'watchlist_tracker_thread') and self.watchlist_tracker_thread and self.watchlist_tracker_thread.is_alive():
            return
        self.watchlist_tracker_stop = threading.Event()
        self.watchlist_tracker_thread = threading.Thread(target=self._watchlist_tracker_worker, daemon=True)
        self.watchlist_tracker_thread.start()

    def stop_watchlist_tracker(self):
        if hasattr(self, 'watchlist_tracker_thread') and self.watchlist_tracker_thread:
            self.watchlist_tracker_stop.set()
            self.watchlist_tracker_thread = None

    def _watchlist_tracker_worker(self):
        while not self.watchlist_tracker_stop.is_set():
            try:
                if not self.settings.get("watchlist_tracking_enabled", True):
                    interval = max(5, self.settings.get("watchlist_interval", 300))
                    self.watchlist_tracker_stop.wait(float(interval))
                    continue

                watchlist = self.settings.get("watchlist", [])
                interval = max(5, self.settings.get("watchlist_interval", 300))
                if not watchlist:
                    self.watchlist_tracker_stop.wait(float(interval))
                    continue

                cookie = None
                for account_name in list(self.manager.accounts):
                    account_data = self.manager.accounts[account_name]
                    cookie = account_data.get("cookie") if isinstance(account_data, dict) else None
                    if cookie:
                        break

                if not cookie:
                    self.watchlist_tracker_stop.wait(float(interval))
                    continue

                user_ids = []
                id_to_username = {}
                for item in watchlist:
                    uid = item.get("user_id")
                    uname = item.get("username")
                    if uid:
                        try:
                            user_ids.append(int(uid))
                            id_to_username[int(uid)] = uname
                        except:
                            pass

                if not user_ids:
                    self.watchlist_tracker_stop.wait(float(interval))
                    continue

                url = "https://presence.roblox.com/v1/presence/users"
                csrf_token = RobloxAPI.get_csrf_token(cookie)
                if not csrf_token:
                    self.watchlist_tracker_stop.wait(5.0)
                    continue

                headers = {
                    'Cookie': f'.ROBLOSECURITY={cookie}',
                    'Content-Type': 'application/json',
                    'X-CSRF-TOKEN': csrf_token
                }
                payload = {
                    "userIds": user_ids
                }

                response = requests.post(url, headers=headers, json=payload, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    user_presences = data.get('userPresences', [])
                    
                    status_names = {0: "Offline", 1: "Online", 2: "InGame", 3: "InStudio"}
                    if not hasattr(self, 'watchlist_statuses'):
                        self.watchlist_statuses = {}

                    for presence in user_presences:
                        uid = presence.get('userId')
                        uid_str = str(uid)
                        status = presence.get('userPresenceType', 0)
                        username = id_to_username.get(uid, f"User {uid}")

                        status_name = status_names.get(status, "Unknown")
                        self.watchlist_statuses[uid_str] = status_name

                        if status == 2:
                            if uid in self.watchlist_alerted_states:
                                del self.watchlist_alerted_states[uid]
                            if uid_str in self.watchlist_alerted_states:
                                del self.watchlist_alerted_states[uid_str]
                        else:
                            if uid not in self.watchlist_alerted_states and uid_str not in self.watchlist_alerted_states:
                                self.watchlist_alerted_states[uid_str] = True
                                
                                wl_webhook = self.settings.get("watchlist_webhook_url", "").strip()
                                if wl_webhook:
                                    status_names_map = {0: "Offline", 1: "Online", 3: "InStudio"}
                                    status_str = status_names_map.get(status, f"Unknown ({status})")
                                    
                                    def _fetch_and_alert(uid_str_val, username_val, status_str_val):
                                        avatar_url = None
                                        try:
                                            thumb_url = f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={uid_str_val}&size=150x150&format=Png&isCircular=false"
                                            r = requests.get(thumb_url, timeout=5)
                                            if r.status_code == 200:
                                                thumb_data = r.json()
                                                if "data" in thumb_data and thumb_data["data"]:
                                                    avatar_url = thumb_data["data"][0].get("imageUrl")
                                        except:
                                            pass
                                        self.send_presence_alert(username_val, uid_str_val, status_str_val, avatar_url)
                                        
                                    threading.Thread(target=_fetch_and_alert, args=(uid_str, username, status_str), daemon=True).start()
                        
                    self.root.after(0, self.refresh_watchlist_ui)
            except Exception as e:
                print(f"[ERROR] Watchlist tracker error: {e}")

            interval = max(5, self.settings.get("watchlist_interval", 300))
            self.watchlist_tracker_stop.wait(float(interval))

    def send_dashboard_telemetry(self):
        url = self.settings.get("dashboard_webhook_url", "").strip()
        if not url:
            return

        active_entries = list(self.instances_data)
        if not active_entries:
            return

        embeds = []
        for entry in active_entries:
            username = entry.get("username")
            user_id = entry.get("user_id")
            avatar_url = entry.get("avatar_url") or self.instances_cache["user_id_to_avatar"].get(user_id)
            create_time = entry.get("create_time")
            mem_val = entry.get("memory_mb", 0.0)
            cpu_val = entry.get("cpu_percent", 0.0)

            status_name = "Offline"
            status = 0
            game_name = "N/A"
            place_id = "N/A"
            if hasattr(self, 'presence_statuses') and username in self.presence_statuses:
                presence = self.presence_statuses[username]
                status = presence.get('status', 0)
                status_names = {0: "Offline", 1: "Online", 2: "InGame", 3: "InStudio"}
                status_name = status_names.get(status, "Offline")
                if status == 2:
                    p_id = presence.get('place_id')
                    if p_id:
                        place_id = str(p_id)
                        cached_name = RobloxAPI.get_game_name(place_id)
                        game_name = cached_name if cached_name else f"Place ID: {place_id}"

            uptime_str = "00:00:00"
            if create_time:
                try:
                    elapsed = int(time.time() - create_time)
                    h = elapsed // 3600
                    m = (elapsed % 3600) // 60
                    s = elapsed % 60
                    uptime_str = f"{h:02d}:{m:02d}:{s:02d}"
                except:
                    pass

            desc = f"**Status**: {status_name}\n**Uptime**: {uptime_str}\n**CPU**: {cpu_val:.1f}%\n**Memory/RAM**: {mem_val:.1f} MB"
            if status == 2:
                desc += f"\n**Game**: {game_name}"
                if place_id != "N/A":
                    desc += f"\n**Place ID**: {place_id}"

            embed = {
                "title": f"🎮 Active: {username}",
                "description": desc,
                "color": 0x2ECC71 if status == 2 else 0xF1C40F,
                "thumbnail": {"url": avatar_url} if avatar_url else None
            }
            embeds.append(embed)

        for i in range(0, len(embeds), 10):
            chunk = embeds[i:i+10]
            payload = {
                "embeds": chunk
            }
            try:
                requests.post(url, json=payload, timeout=5)
            except:
                pass

    def send_presence_alert(self, username, user_id, status_str, avatar_url):
        wl_webhook = self.settings.get("watchlist_webhook_url", "").strip()
        if not wl_webhook:
            return

        ping_id = self.settings.get("watchlist_ping_id", "").strip()
        payload = {
            "content": f"<@{ping_id}>" if ping_id else "",
            "embeds": [{
                "title": "🚨 Watchlist Presence Alert",
                "description": f"Account **{username}** (ID: `{user_id}`) is not in-game.\n**Current Status**: {status_str}",
                "color": 0xE74C3C,
                "thumbnail": {"url": avatar_url} if avatar_url else None,
                "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
            }]
        }
        try:
            requests.post(wl_webhook, json=payload, timeout=5)
        except:
            pass

    def send_active_report_webhook(self):
        url = self.db_webhook_entry.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please enter a valid Discord Webhook URL.")
            return

        self.db_webhook_btn.config(state="disabled")
        
        def worker():
            try:
                self.send_dashboard_telemetry()
                self.root.after(0, lambda: messagebox.showinfo("Success", "Webhook report sent successfully!"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to send webhook report: {e}"))
            finally:
                self.root.after(0, lambda: self.db_webhook_btn.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def start_dashboard_report_automation(self):
        if hasattr(self, 'db_auto_thread') and self.db_auto_thread and self.db_auto_thread.is_alive():
            return
        self.db_auto_stop = threading.Event()
        self.db_auto_thread = threading.Thread(target=self._dashboard_report_worker, daemon=True)
        self.db_auto_thread.start()

    def stop_dashboard_report_automation(self):
        if hasattr(self, 'db_auto_thread') and self.db_auto_thread:
            self.db_auto_stop.set()
            self.db_auto_thread = None

    def _dashboard_report_worker(self):
        while not self.db_auto_stop.is_set():
            try:
                is_auto = self.settings.get("dashboard_auto_report", False)
                if is_auto:
                    self.send_dashboard_telemetry()
            except:
                pass
            
            interval = max(5, self.settings.get("dashboard_report_interval", 60))
            self.db_auto_stop.wait(float(interval))