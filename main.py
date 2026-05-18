import os
import warnings
import tkinter as tk
from tkinter import messagebox, simpledialog
import requests
import threading

warnings.filterwarnings("ignore")

from classes import RobloxAccountManager
from classes.encryption import EncryptionConfig
from utils.encryption_setup import setup_encryption
from ui.main_window import RefactoredAccountManagerUI as AccountManagerUI

def setup_icon(data_folder):
    icon_path = os.path.join(data_folder, "icon.ico")
    if os.path.exists(icon_path):
        return icon_path
    try:
        icon_url = "https://raw.githubusercontent.com/evanovar/RobloxAccountManager/main/icon.ico"
        response = requests.get(icon_url, timeout=5)
        if response.status_code == 200:
            with open(icon_path, 'wb') as f:
                f.write(response.content)
            return icon_path
        else:
            return None
    except:
        return None

def setup_discord_logo(data_folder):
    return None

def apply_icon_to_window(window, icon_path):
    if icon_path and os.path.exists(icon_path):
        try:
            window.iconbitmap(icon_path)
        except:
            pass

def apply_icon_async(root, data_folder):
    icon_path = os.path.join(data_folder, "icon.ico")
    discord_logo_path = os.path.join(data_folder, "discordlogo.png")
    if os.path.exists(icon_path):
        apply_icon_to_window(root, icon_path)
    needs_icon = not os.path.exists(icon_path)
    needs_discord = not os.path.exists(discord_logo_path)
    if needs_icon or needs_discord:
        def download_assets():
            if needs_icon:
                try:
                    setup_icon(data_folder)
                except:
                    pass
            if needs_discord:
                try:
                    setup_discord_logo(data_folder)
                except:
                    pass
        threading.Thread(target=download_assets, daemon=True).start()
    return icon_path if os.path.exists(icon_path) else None, discord_logo_path

def main():
    password = setup_encryption()
    data_folder = "AccountManagerData"
    if not os.path.exists(data_folder):
        os.makedirs(data_folder)
    encryption_config = EncryptionConfig(os.path.join(data_folder, "encryption_config.json"))
    if encryption_config.is_encryption_enabled() and encryption_config.get_encryption_method() == 'password':
        if password is None:
            root = tk.Tk()
            root.withdraw()
            password = simpledialog.askstring("Password Required", "Enter your password to unlock:", show='*')
            root.destroy()
            if password is None:
                messagebox.showerror("Error", "Password is required to access encrypted accounts.")
                return
    try:
        manager = RobloxAccountManager(password=password)
    except ValueError as e:
        err_msg = str(e)
        if "corrupted" in err_msg.lower():
            messagebox.showerror("Database Corrupted", f"Error: {err_msg}\n\nPlease check your AccountManagerData directory or restore a backup.")
        elif "password" in err_msg.lower():
            messagebox.showerror("Error", "Password is invalid. Please try again.")
        else:
            messagebox.showerror("Error", f"Failed to initialize: {err_msg}")
        return
    except Exception as e:
        messagebox.showerror("Error", f"Failed to initialize: {e}")
        return

    manager.accounts_cache = [dict(val) for val in manager.accounts.values()]
    manager._original_save_accounts = manager.save_accounts
    def patched_save_accounts():
        manager.accounts_cache = [dict(val) for val in manager.accounts.values()]
        threading.Thread(target=manager._original_save_accounts, daemon=True).start()
        if hasattr(manager, "ui") and manager.ui:
            manager.ui.refresh_accounts()
    manager.save_accounts = patched_save_accounts

    root = tk.Tk()
    root.withdraw()
    icon_path, _ = apply_icon_async(root, data_folder)
    app = AccountManagerUI(root, manager, icon_path=icon_path, discord_logo_path=None)
    manager.ui = app
    root.deiconify()
    root.mainloop()

if __name__ == "__main__":
    main()