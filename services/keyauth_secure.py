import os
import json
import sys
import requests
import win32crypt
import base64
import hashlib
from Crypto.Cipher import AES

# ── Storage paths ─────────────────────────────────────────────────────────────
SECURE_DIR  = os.path.join(os.environ.get("APPDATA", ""), "RobloxAccountManager")
SECURE_FILE = os.path.join(SECURE_DIR, "license.enc")
ENTROPY     = b"RAM_KeyAuth_DPAPI_Entropy_9832"

# ── AES-256-GCM credential decryption ─────────────────────────────────────────
_CUSTOM_SALT = b"ram_auth_secure_salt_2026"
_CUSTOM_PASS = b"Krishnadiscord929_Secret_Passphrase_!!!"
_KEY         = hashlib.sha256(_CUSTOM_PASS + _CUSTOM_SALT).digest()

_ENCRYPTED_CREDS = {
    "ciphertext": "ej3qLB7xfwVgK27Sy0mi4ThDrJp9cVcn9d3+14Sr1xLCL43V94xQAVjJCsED/sIZY8Gkak0hj3pqq8t+NH8WSesPTy0wpMQC0zi+LA9hJ9xGswl3dL+Ft/6puZfzCCLXddc3YzKO3Rg5iEvfNZF8eB4Sm/wPvubwAeoRmHVWFv5Ek8rMvKtuB/wmwFQva90fy4qM+b4DhieZQwgobwer8VWiT7LG4/1G6w==",
    "tag":        "nnTrtHxeAkMu1dRK/HGn6w==",
    "nonce":      "ztcjTPay/u/+aIXrwWRzgw=="
}

def _decrypt_creds() -> dict:
    try:
        nonce      = base64.b64decode(_ENCRYPTED_CREDS["nonce"])
        tag        = base64.b64decode(_ENCRYPTED_CREDS["tag"])
        ciphertext = base64.b64decode(_ENCRYPTED_CREDS["ciphertext"])
        cipher     = AES.new(_KEY, AES.MODE_GCM, nonce=nonce)
        return json.loads(cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8'))
    except Exception as e:
        print(f"[KeyAuth] Credential decryption failed: {e}")
        return {"app_name": "", "owner_id": "", "secret": "", "version": ""}

KEYAUTH_CREDS = _decrypt_creds()

# ── KeyAuth response classification ───────────────────────────────────────────
# Returned as the second element of verify_license() so callers can branch
# without string-matching raw server messages.
class AuthResult:
    SUCCESS       = "success"        # Key valid, HWID accepted/latched
    HWID_MISMATCH = "hwid_mismatch"  # Key is valid but bound to a different machine
    HWID_LATCHED  = "hwid_latched"   # Fresh key: HWID was blank, now locked to this machine
    INVALID_KEY   = "invalid_key"    # Key does not exist or has expired
    NETWORK_ERROR = "network_error"  # Could not reach KeyAuth servers
    SERVER_ERROR  = "server_error"   # KeyAuth session/init failure

# Exact substrings returned by keyauth.win/api that indicate HWID state.
# These are matched case-insensitively against the server's "message" field.
_HWID_MISMATCH_MARKERS = ("hwid doesn't match", "hwid mismatch", "invalid hwid")
_HWID_BLANK_MARKERS    = ("hwid is blank", "no hwid", "hwid not set", "hwid updated")


class SecureKeyAuth:
    def __init__(self):
        self.session_id = None

    # ── Disk helpers ──────────────────────────────────────────────────────────

    def _ensure_dir(self):
        if not os.path.exists(SECURE_DIR):
            try:
                os.makedirs(SECURE_DIR)
            except Exception as e:
                print(f"[KeyAuth] Failed to create storage folder: {e}")

    def save_license_key(self, license_key: str) -> bool:
        """Encrypts and persists the license key via Windows DPAPI."""
        self._ensure_dir()
        try:
            raw = json.dumps({"license_key": license_key}).encode('utf-8')
            blob = win32crypt.CryptProtectData(raw, "RAM License System", ENTROPY, None, None, 1)
            with open(SECURE_FILE, "wb") as f:
                f.write(blob)
            return True
        except Exception as e:
            print(f"[KeyAuth] Save failed: {e}")
            return False

    def load_license_key(self) -> str:
        """Decrypts and returns the saved license key, or empty string if absent."""
        if not os.path.exists(SECURE_FILE):
            return ""
        try:
            with open(SECURE_FILE, "rb") as f:
                blob = f.read()
            _, raw = win32crypt.CryptUnprotectData(blob, ENTROPY, None, None, 1)
            return json.loads(raw.decode('utf-8')).get("license_key", "")
        except Exception as e:
            print(f"[KeyAuth] Load failed: {e}")
            return ""

    def clear_license_key(self):
        """Removes any stored license key from disk (used on HWID mismatch reset)."""
        try:
            if os.path.exists(SECURE_FILE):
                os.remove(SECURE_FILE)
        except Exception as e:
            print(f"[KeyAuth] Could not clear stored key: {e}")

    # ── KeyAuth session ───────────────────────────────────────────────────────

    def init_keyauth(self) -> bool:
        """Opens a KeyAuth API session. Must succeed before license verification."""
        url  = "https://keyauth.win/api/1.2/"
        data = {
            "type":    "init",
            "name":    KEYAUTH_CREDS["app_name"],
            "ownerid": KEYAUTH_CREDS["owner_id"],
            "secret":  KEYAUTH_CREDS["secret"],
            "version": KEYAUTH_CREDS["version"]
        }
        try:
            res = requests.post(url, data=data, timeout=10).json()
            if res.get("success"):
                self.session_id = res.get("sessionid")
                return True
            print(f"[KeyAuth] Session init rejected: {res.get('message', 'unknown')}")
            return False
        except requests.Timeout:
            print("[KeyAuth] Session init timed out.")
            return False
        except Exception as e:
            print(f"[KeyAuth] Session init error: {e}")
            return False

    def _get_hwid(self) -> str:
        """Returns a stable hardware fingerprint from the Windows MachineGuid registry."""
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(k, "MachineGuid")
            return str(guid).strip()
        except Exception:
            pass
        try:
            import subprocess
            out = subprocess.check_output(
                "wmic csproduct get uuid",
                creationflags=subprocess.CREATE_NO_WINDOW
            ).decode().split('\n')[1].strip()
            if out:
                return out
        except Exception:
            pass
        return "fallback_ram_hwid_key"

    # ── License verification with HWID classification ─────────────────────────

    def verify_license(self, license_key: str) -> tuple[bool, str, str]:
        """
        Verifies a license key against KeyAuth with full HWID-state classification.

        Returns:
            (success: bool, message: str, result_code: AuthResult)

        Result codes:
            AuthResult.SUCCESS       — key valid, proceed to app.
            AuthResult.HWID_LATCHED  — fresh key; HWID was blank and has now been
                                       locked to this machine. Treat as success.
            AuthResult.HWID_MISMATCH — key is bound to a different machine.
                                       User needs an HWID reset from the panel.
            AuthResult.INVALID_KEY   — key does not exist, expired, or banned.
            AuthResult.NETWORK_ERROR — could not reach KeyAuth servers.
            AuthResult.SERVER_ERROR  — session/init failure.
        """
        if not self.session_id and not self.init_keyauth():
            return False, "Could not connect to the authentication server.", AuthResult.SERVER_ERROR

        url  = "https://keyauth.win/api/1.2/"
        data = {
            "type":      "license",
            "key":       license_key,
            "hwid":      self._get_hwid(),
            "sessionid": self.session_id,
            "name":      KEYAUTH_CREDS["app_name"],
            "ownerid":   KEYAUTH_CREDS["owner_id"]
        }

        try:
            res = requests.post(url, data=data, timeout=10).json()
        except requests.Timeout:
            return False, "Authentication server timed out. Check your internet connection.", AuthResult.NETWORK_ERROR
        except Exception as e:
            return False, f"Network error: {e}", AuthResult.NETWORK_ERROR

        success = res.get("success", False)
        message = res.get("message", "Unknown response")
        msg_lower = message.lower()

        if success:
            # KeyAuth returns success=True both when the HWID was already correct
            # AND when it was blank and has just been latched for the first time.
            if any(marker in msg_lower for marker in _HWID_BLANK_MARKERS):
                print(f"[KeyAuth] HWID latched to this machine for the first time.")
                return True, message, AuthResult.HWID_LATCHED
            return True, message, AuthResult.SUCCESS

        # Server returned success=False — classify the failure precisely.
        if any(marker in msg_lower for marker in _HWID_MISMATCH_MARKERS):
            print(f"[KeyAuth] HWID mismatch detected: {message}")
            return False, message, AuthResult.HWID_MISMATCH

        print(f"[KeyAuth] License rejected: {message}")
        return False, message, AuthResult.INVALID_KEY
