import os
import sys
import tkinter as tk
import threading
import asyncio
import time
from utils.ui import AccountManagerUI
from ui.system_tray import WindowsSystemTray
from bot.client import DiscordBot

class RefactoredAccountManagerUI(AccountManagerUI):
    def __init__(self, root, manager, icon_path=None, discord_logo_path=None):
        super().__init__(root, manager, icon_path, discord_logo_path)
        if hasattr(self, "discord_bot") and self.discord_bot:
            try:
                self.discord_bot.stop()
            except:
                pass
        self.discord_bot = DiscordBot(self)

        if hasattr(self, "system_tray") and self.system_tray:
            try:
                self.system_tray.destroy()
            except:
                pass
        self.system_tray = WindowsSystemTray(
            root=self.root,
            on_open=self.restore_from_tray,
            on_exit=self.exit_completely,
            icon_path=self.icon_path
        )

    def open_settings(self):
        from ui.settings_window import open_settings_window
        open_settings_window(self)

    def refresh_accounts(self):
        self._clear_active_instance_indicators()
        self.account_list.delete(0, tk.END)
        self._list_row_map = []
        groups = self._get_groups()
        if self.settings.get("active_instances_monitoring", False):
            try:
                self._active_instance_usernames = set([u.lower() for u in self._get_active_instance_usernames()])
            except:
                self._active_instance_usernames = set()
        else:
            self._active_instance_usernames = set()
        grouped_usernames = set()
        for members in groups.values():
            grouped_usernames.update(members)
        
        accounts_list = getattr(self.manager, "accounts_cache", [])
        for account_data in accounts_list:
            username = account_data.get('username')
            if not username or username in grouped_usernames:
                continue
            self._insert_account_row(username, account_data)

        for gname, members in groups.items():
            collapsed = gname in self._collapsed_groups
            visible_members = [u for u in members if any(acc.get('username') == u for acc in accounts_list)]
            header_text = self._build_group_header_text(gname, len(visible_members), collapsed)
            idx = self.account_list.size()
            self.account_list.insert(tk.END, header_text)
            self._list_row_map.append(("group_header", gname))
            self.account_list.itemconfig(
                idx,
                fg=self.FG_ACCENT,
                bg=self.BG_MID,
                selectbackground=self.BG_MID,
                selectforeground=self.FG_ACCENT
            )
            if not collapsed:
                for username in members:
                    acc_data = next((acc for acc in accounts_list if acc.get('username') == username), None)
                    if acc_data:
                        self._insert_account_row(username, acc_data)
        self._schedule_active_instance_indicator_sync()

    def edit_account_note(self):
        def worker():
            try:
                super(RefactoredAccountManagerUI, self).edit_account_note()
            except:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def remove_account(self):
        def worker():
            try:
                super(RefactoredAccountManagerUI, self).remove_account()
            except:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _insert_account_row(self, username, data):
        idx = self.account_list.size()
        self.account_list.insert(tk.END, " " * 45)
        self._list_row_map.append(("account", username))
        self.account_list.itemconfig(
            idx,
            fg=self.FG_TEXT,
            bg=self.BG_DARK,
            selectforeground=self.FG_TEXT,
            selectbackground=self.FG_ACCENT
        )

    def _sync_active_instance_indicators(self):
        self._active_instance_indicator_sync_after = None
        if not hasattr(self, "account_list") or not self.account_list.winfo_exists():
            return
        self._clear_active_instance_indicators()
        active_usernames = getattr(self, "_active_instance_usernames", set()) or set()
        normal_bg = self.account_list.cget("bg")
        selected_bg = self.account_list.cget("selectbackground")
        item_height = 22
        first_visible = self.account_list.nearest(0)
        
        accounts_list = getattr(self.manager, "accounts_cache", [])
        
        for index, (kind, username) in enumerate(self._list_row_map):
            if kind != "account":
                continue
            bbox = self.account_list.bbox(index)
            if not bbox:
                continue
            x, y_bbox, width, height = bbox
            y = (index - first_visible) * item_height
            row_bg = selected_bg if self.account_list.selection_includes(index) else normal_bg
            
            if username.lower() in active_usernames:
                dot = tk.Canvas(
                    self.account_list,
                    width=8,
                    height=8,
                    bg=row_bg,
                    highlightthickness=0,
                    bd=0
                )
                dot.create_oval(0, 0, 7, 7, fill="#3DDC84", outline="#2FAF67")
                dot.place(x=12, y=y + (item_height - 8) // 2)
                self._active_instance_indicators[f"active_{username}_{index}"] = dot
                
            acc_data = next((acc for acc in accounts_list if acc.get('username') == username), None)
            cookie_valid = None
            aging_indicator = ""
            note = ""
            if acc_data:
                note = acc_data.get('note', '')
                cookie_valid = self.cookie_status.get(username)
                if cookie_valid is not False:
                    last_use_str = acc_data.get('last_use')
                    if last_use_str:
                        try:
                            last_use_time = time.strptime(last_use_str, '%Y-%m-%d %H:%M:%S')
                            idle_days = (time.time() - time.mktime(last_use_time)) / 86400.0
                            if idle_days >= 20:
                                if idle_days < 25:
                                    aging_indicator = "🟡"
                                elif idle_days < 30:
                                    aging_indicator = "🟠"
                                else:
                                    aging_indicator = "🔴"
                        except:
                            pass
            
            overlay_char = ""
            overlay_color = self.FG_TEXT
            if cookie_valid is False:
                overlay_char = "\u26a0"
                overlay_color = "#FFB347"
            elif aging_indicator:
                overlay_char = aging_indicator
                
            if overlay_char:
                lbl = tk.Label(
                    self.account_list,
                    text=overlay_char,
                    fg=overlay_color,
                    bg=row_bg,
                    font=("Segoe UI", 9)
                )
                lbl.place(x=20, y=y + (item_height - 18) // 2)
                self._active_instance_indicators[f"overlay_{username}_{index}"] = lbl

            label_text = username
            if note:
                label_text += f" \u2022 {note}"
            
            lbl_name = tk.Label(
                self.account_list,
                text=label_text,
                fg=overlay_color if cookie_valid is False else self.FG_TEXT,
                bg=row_bg,
                font=("Segoe UI", 10)
            )
            lbl_name.place(x=32, y=y + (item_height - 20) // 2)
            self._active_instance_indicators[f"name_{username}_{index}"] = lbl_name

    def _update_active_instance_indicators(self):
        self._sync_active_instance_indicators()
