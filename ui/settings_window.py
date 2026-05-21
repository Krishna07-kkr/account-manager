import os
import json
import sys
import re
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, simpledialog, filedialog
from tkinter import font as tkfont
import requests
import threading
import webbrowser
import time

def open_settings_window(self):
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
    
    license_tab = ttk.Frame(tabs, style="Dark.TFrame")
    tabs.add(license_tab, text="Licensing")
    
    lic_frame = ttk.Frame(license_tab, style="Dark.TFrame")
    lic_frame.pack(fill="both", expand=True, padx=20, pady=15)
    
    ttk.Label(
        lic_frame,
        text="KeyAuth License System",
        style="Dark.TLabel",
        font=(self.FONT_FAMILY, 11, "bold")
    ).pack(anchor="w", pady=(0, 2))
    
    ttk.Label(
        lic_frame,
        text="Manage your application licensing configuration.",
        style="Dark.TLabel",
        font=(self.FONT_FAMILY, 8)
    ).pack(anchor="w", pady=(0, 10))
    
    lic_sep = ttk.Frame(lic_frame, style="Dark.TFrame", height=1)
    lic_sep.pack(fill="x", pady=(0, 8))
    lic_sep.configure(relief="solid", borderwidth=1)
    
    from services.keyauth_secure import SecureKeyAuth
    auth_manager = SecureKeyAuth()
    
    status_label_var = tk.StringVar()
    
    def update_license_status():
        saved_key = auth_manager.load_license_key()
        if saved_key:
            masked = saved_key[:4] + "*" * (len(saved_key) - 4) if len(saved_key) > 4 else "****"
            status_label_var.set(f"Status: 🟢 Active Key ({masked})")
        else:
            status_label_var.set("Status: 🔴 No Active Key")
                
    update_license_status()
    
    ttk.Label(
        lic_frame,
        textvariable=status_label_var,
        style="Dark.TLabel",
        font=(self.FONT_FAMILY, 10, "bold")
    ).pack(anchor="w", pady=(5, 15))
    
    def revoke_license_key():
        saved_key = auth_manager.load_license_key()
        if not saved_key:
            messagebox.showinfo("Info", "No active license key is currently stored.", parent=settings_window)
            return
        if messagebox.askyesno("Confirm Revocation", "Revoke the currently saved license key? The application will prompt for a key on the next launch.", parent=settings_window):
            auth_manager.save_license_key("")
            update_license_status()
            messagebox.showinfo("Revoked", "Saved license key has been cleared.", parent=settings_window)

    def change_license_key():
        new_key = simpledialog.askstring("Change License Key", "Enter new license key:", parent=settings_window)
        if new_key:
            valid, msg = auth_manager.verify_license(new_key.strip())
            if valid:
                auth_manager.save_license_key(new_key.strip())
                update_license_status()
                messagebox.showinfo("Success", "License verified and updated successfully!", parent=settings_window)
            else:
                messagebox.showerror("Error", f"Invalid License Key: {msg}", parent=settings_window)

    ttk.Button(
        lic_frame,
        text="Change/Verify License Key",
        style="Dark.TButton",
        command=change_license_key
    ).pack(fill="x", pady=6)
    
    ttk.Button(
        lic_frame,
        text="Clear Saved License Key",
        style="Dark.TButton",
        command=revoke_license_key
    ).pack(fill="x", pady=6)


    
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
        start_menu = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
        shortcut_path = os.path.join(start_menu, "Roblox Account Manager.lnk")
        return os.path.exists(shortcut_path)
    
    def toggle_start_menu_shortcut():
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
            except Exception as e:
                print(f"[ERROR] Failed to create Start Menu shortcut: {e}")
                start_menu_var.set(False)
        else:
            try:
                if os.path.exists(shortcut_path):
                    os.remove(shortcut_path)
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
    
    roblox_tab_frame = roblox_tab
    roblox_frame = ttk.Frame(roblox_tab_frame, style="Dark.TFrame")
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
            subprocess.run(
                ['taskkill', '/F', '/IM', 'RobloxPlayerBeta.exe'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            messagebox.showinfo("Success", "All Roblox instances have been processed.")
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
        import threading
        threading.Thread(
            target=RobloxAPI.apply_graphics_optimization,
            args=(enabled,),
            daemon=True
        ).start()
    
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
