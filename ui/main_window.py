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
        self._desired_rows = []
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
        desired_rows = []
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
        account_idx = 0
        for account_data in accounts_list:
            username = account_data.get('username')
            if not username or username in grouped_usernames:
                continue
            desired_rows.append(self._build_row_dict(username, account_data, account_idx))
            account_idx += 1

        for gname, members in groups.items():
            collapsed = gname in self._collapsed_groups
            visible_members = [u for u in members if any(acc.get('username') == u for acc in accounts_list)]
            header_text = self._build_group_header_text(gname, len(visible_members), collapsed)
            
            desired_rows.append({
                "text": header_text,
                "fg": self.FG_ACCENT,
                "bg": self.BG_MID,
                "selectbg": self.BG_MID,
                "selectfg": self.FG_ACCENT,
                "row_map": ("group_header", gname)
            })
            
            if not collapsed:
                for username in members:
                    acc_data = next((acc for acc in accounts_list if acc.get('username') == username), None)
                    if acc_data:
                        desired_rows.append(self._build_row_dict(username, acc_data, account_idx))
                        account_idx += 1

        self._update_listbox_flicker_free(desired_rows)
        self._schedule_active_instance_indicator_sync()

    def _build_row_dict(self, username, data, account_idx=0):
        return {
            "text": " " * 45,
            "fg": self.FG_TEXT,
            "bg": self.BG_DARK,
            "selectbg": self.FG_ACCENT,
            "selectfg": self.FG_TEXT,
            "row_map": ("account", username)
        }

    def _update_listbox_flicker_free(self, desired_rows):
        self._desired_rows = desired_rows
        current_size = self.account_list.size()
        desired_size = len(desired_rows)
        
        self._list_row_map = [row["row_map"] for row in desired_rows]
        
        if current_size != desired_size:
            self.account_list.delete(0, tk.END)
            for i, row in enumerate(desired_rows):
                self.account_list.insert(tk.END, row["text"])
                self.account_list.itemconfig(
                    i,
                    fg=row.get("fg", ""),
                    bg=row.get("bg", ""),
                    selectforeground=row.get("selectfg", ""),
                    selectbackground=row.get("selectbg", "")
                )
        else:
            for i, row in enumerate(desired_rows):
                current_text = self.account_list.get(i)
                desired_text = row["text"]
                if current_text != desired_text:
                    self.account_list.delete(i)
                    self.account_list.insert(i, desired_text)
                
                curr_fg = self.account_list.itemcget(i, "fg")
                curr_bg = self.account_list.itemcget(i, "bg")
                curr_selfg = self.account_list.itemcget(i, "selectforeground")
                curr_selbg = self.account_list.itemcget(i, "selectbackground")
                
                tgt_fg = row.get("fg", "")
                tgt_bg = row.get("bg", "")
                tgt_selfg = row.get("selectfg", "")
                tgt_selbg = row.get("selectbg", "")
                
                style_kwargs = {}
                if curr_fg != tgt_fg:
                    style_kwargs["fg"] = tgt_fg
                if curr_bg != tgt_bg:
                    style_kwargs["bg"] = tgt_bg
                if curr_selfg != tgt_selfg:
                    style_kwargs["selectforeground"] = tgt_selfg
                if curr_selbg != tgt_selbg:
                    style_kwargs["selectbackground"] = tgt_selbg
                    
                if style_kwargs:
                    self.account_list.itemconfig(i, **style_kwargs)

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
        desired_rows = getattr(self, "_desired_rows", [])
        row_dict = {
            "text": " " * 45,
            "fg": self.FG_TEXT,
            "bg": self.BG_DARK,
            "selectbg": self.FG_ACCENT,
            "selectfg": self.FG_TEXT,
            "row_map": ("account", username)
        }
        if len(desired_rows) > idx:
            desired_rows[idx] = row_dict
        else:
            desired_rows.append(row_dict)
        self._desired_rows = desired_rows

    def _sync_active_instance_indicators(self):
        self._active_instance_indicator_sync_after = None
        if not hasattr(self, "account_list") or not self.account_list.winfo_exists():
            return
        
        active_usernames = getattr(self, "_active_instance_usernames", set()) or set()
        
        accounts_list = getattr(self.manager, "accounts_cache", [])
        needed_keys = set()
        
        desired_rows = getattr(self, "_desired_rows", [])
        
        for index, (kind, username) in enumerate(self._list_row_map):
            if kind != "account":
                continue
            bbox = self.account_list.bbox(index)
            if not bbox:
                continue
            x, y_bbox, width, height = bbox
            row_data = desired_rows[index] if index < len(desired_rows) else {}
            if self.account_list.selection_includes(index):
                row_bg = row_data.get("selectbg", "#0078D7")
                row_fg = row_data.get("selectfg", "#ffffff")
            else:
                row_bg = row_data.get("bg", "#2b2b2b")
                row_fg = row_data.get("fg", "#ffffff")
            
            if username.lower() in active_usernames:
                dot_key = f"active_{username}_{index}"
                needed_keys.add(dot_key)
                existing_dot = self._active_instance_indicators.get(dot_key)
                if existing_dot and isinstance(existing_dot, tk.Canvas) and existing_dot.winfo_exists():
                    existing_dot.config(bg=row_bg)
                    existing_dot.place(x=12, y=y_bbox + (height - 8) // 2)
                else:
                    if existing_dot:
                        try: existing_dot.destroy()
                        except: pass
                    dot = tk.Canvas(
                        self.account_list,
                        width=8,
                        height=8,
                        bg=row_bg,
                        highlightthickness=0,
                        bd=0
                    )
                    dot.create_oval(0, 0, 7, 7, fill="#3DDC84", outline="#2FAF67")
                    dot.place(x=12, y=y_bbox + (height - 8) // 2)
                    self._active_instance_indicators[dot_key] = dot
                
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
            overlay_color = row_fg
            if cookie_valid is False:
                overlay_char = "\u26a0"
                overlay_color = "#FFB347"
            elif aging_indicator:
                overlay_char = aging_indicator
                
            if overlay_char:
                overlay_key = f"overlay_{username}_{index}"
                needed_keys.add(overlay_key)
                existing_overlay = self._active_instance_indicators.get(overlay_key)
                if existing_overlay and isinstance(existing_overlay, tk.Label) and existing_overlay.winfo_exists():
                    existing_overlay.config(text=overlay_char, fg=overlay_color, bg=row_bg)
                    existing_overlay.place(x=20, y=y_bbox + (height - 18) // 2)
                else:
                    if existing_overlay:
                        try: existing_overlay.destroy()
                        except: pass
                    lbl = tk.Label(
                        self.account_list,
                        text=overlay_char,
                        fg=overlay_color,
                        bg=row_bg,
                        font=("Segoe UI", 9)
                    )
                    lbl.place(x=20, y=y_bbox + (height - 18) // 2)
                    self._active_instance_indicators[overlay_key] = lbl
 
            label_text = username
            if note:
                label_text += f" \u2022 {note}"
            
            name_key = f"name_{username}_{index}"
            needed_keys.add(name_key)
            tgt_fg = overlay_color if cookie_valid is False else row_fg
            existing_name = self._active_instance_indicators.get(name_key)
            if existing_name and isinstance(existing_name, tk.Label) and existing_name.winfo_exists():
                existing_name.config(text=label_text, fg=tgt_fg, bg=row_bg)
                existing_name.place(x=32, y=y_bbox + (height - 20) // 2)
            else:
                if existing_name:
                    try: existing_name.destroy()
                    except: pass
                lbl_name = tk.Label(
                    self.account_list,
                    text=label_text,
                    fg=tgt_fg,
                    bg=row_bg,
                    font=("Segoe UI", 10)
                )
                lbl_name.place(x=32, y=y_bbox + (height - 20) // 2)
                self._active_instance_indicators[name_key] = lbl_name

        for key in list(self._active_instance_indicators.keys()):
            if key not in needed_keys:
                widget = self._active_instance_indicators.pop(key)
                try:
                    widget.destroy()
                except:
                    pass

    def _update_active_instance_indicators(self):
        self._sync_active_instance_indicators()
