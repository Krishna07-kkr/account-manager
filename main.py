import os
import sys

# Ensure the working directory is set to the folder of the executable/script.
# This prevents Windows API errors (like WinError 2 on directory creation/existence checks)
# if the application is launched with an invalid or deleted current working directory.
try:
    base_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else (sys.argv[0] if (sys.argv and sys.argv[0]) else __file__)))
    os.chdir(base_dir)
except Exception:
    pass

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
    except Exception:
        pass
    return None

def setup_discord_logo(data_folder):
    return None

def apply_icon_to_window(window, icon_path):
    if icon_path and os.path.exists(icon_path):
        try:
            window.iconbitmap(icon_path)
        except Exception:
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
                except Exception:
                    pass
            if needs_discord:
                try:
                    setup_discord_logo(data_folder)
                except Exception:
                    pass
        threading.Thread(target=download_assets, daemon=True).start()
    return icon_path if os.path.exists(icon_path) else None, discord_logo_path

def _show(kind: str, title: str, body: str):
    root = tk.Tk()
    root.withdraw()
    getattr(messagebox, kind)(title, body)
    root.destroy()

def enforce_keyauth():
    from services.keyauth_secure import SecureKeyAuth, AuthResult

    auth = SecureKeyAuth()

    def _attempt(license_key: str) -> bool:
        valid, msg, code = auth.verify_license(license_key)

        if valid or code == AuthResult.HWID_LATCHED:
            if code == AuthResult.HWID_LATCHED:
                _show("showinfo", "HWID Registered",
                      "Your hardware ID has been registered to this license key.\n"
                      "This machine is now permanently linked.")
            auth.save_license_key(license_key)
            return True

        if code == AuthResult.HWID_MISMATCH:
            auth.clear_license_key()
            _show("showerror", "Hardware Mismatch",
                  "This license key is bound to a different machine.\n\n"
                  "To use it on this PC, ask the key owner to reset the HWID\n"
                  "via the KeyAuth dashboard, then try again.")
            sys.exit(0)

        if code == AuthResult.NETWORK_ERROR:
            _show("showerror", "Connection Error",
                  f"Could not reach the authentication server.\n\n{msg}\n\n"
                  "Check your internet connection and restart the application.")
            sys.exit(0)

        if code == AuthResult.SERVER_ERROR:
            _show("showerror", "Server Error",
                  "Authentication server rejected the session handshake.\n\n"
                  "Please try again in a few moments.")
            sys.exit(0)

        # AuthResult.INVALID_KEY — bad / expired key
        _show("showerror", "Invalid License", f"License key rejected:\n{msg}")
        return False

    # Try the saved key first (silently on HWID mismatch to avoid confusing users
    # who are launching on a new machine with an already-bound key).
    saved_key = auth.load_license_key()
    if saved_key:
        valid, msg, code = auth.verify_license(saved_key)
        if valid or code == AuthResult.HWID_LATCHED:
            if code == AuthResult.HWID_LATCHED:
                _show("showinfo", "HWID Registered",
                      "Your hardware ID has been registered to this license key.\n"
                      "This machine is now permanently linked.")
            return True
        if code == AuthResult.HWID_MISMATCH:
            auth.clear_license_key()
            _show("showerror", "Hardware Mismatch",
                  "The saved license key is bound to a different machine.\n\n"
                  "Ask the key owner to reset the HWID via the KeyAuth dashboard,\n"
                  "then enter your key again.")
        elif code == AuthResult.NETWORK_ERROR:
            _show("showerror", "Connection Error",
                  f"Could not reach the authentication server.\n\n{msg}")
            sys.exit(0)
        else:
            _show("showwarning", "License Verification Failed",
                  f"Saved key is no longer valid: {msg}\n\nPlease enter a new license key.")

    # Prompt for a key.
    root = tk.Tk()
    root.withdraw()
    user_key = simpledialog.askstring(
        "License Required",
        "Enter your license key to continue:"
    )
    root.destroy()

    if not user_key or not user_key.strip():
        _show("showerror", "Error", "A valid license key is required to launch.")
        sys.exit(0)

    if not _attempt(user_key.strip()):
        sys.exit(0)

    return True

def main():
    enforce_keyauth()
    base_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else (sys.argv[0] if (sys.argv and sys.argv[0]) else __file__)))
    data_folder = os.path.join(base_dir, "AccountManagerData")
    try:
        if not os.path.exists(data_folder):
            os.makedirs(data_folder)
    except Exception as e:
        import traceback
        error_details = (
            f"Failed to create data folder.\n\n"
            f"Target Path: {data_folder}\n"
            f"Base Dir: {base_dir}\n"
            f"Executable: {sys.executable}\n"
            f"CWD: {os.getcwd()}\n"
            f"Error: {e}\n\n"
            f"Traceback:\n{traceback.format_exc()}"
        )
        _show("showerror", "Folder Creation Error", error_details)
        sys.exit(1)
    password = setup_encryption()
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
            messagebox.showerror(
                "Database Corrupted",
                f"Error: {err_msg}\n\nPlease check your AccountManagerData directory or restore a backup."
            )
        elif "password" in err_msg.lower():
            messagebox.showerror("Error", "Password is invalid. Please try again.")
        else:
            messagebox.showerror("Error", f"Failed to initialize: {err_msg}")
        return
    except Exception as e:
        messagebox.showerror("Error", f"Failed to initialize: {e}")
        return

    with manager._lock:
        manager.accounts_cache = [dict(val) for val in manager.accounts.values()]
    manager._original_save_accounts = manager.save_accounts

    def patched_save_accounts():
        with manager._lock:
            manager.accounts_cache = [dict(val) for val in manager.accounts.values()]
        threading.Thread(target=manager._original_save_accounts, daemon=True).start()
        if hasattr(manager, "ui") and manager.ui:
            try:
                manager.ui.root.after(0, manager.ui.refresh_accounts)
            except Exception:
                pass

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