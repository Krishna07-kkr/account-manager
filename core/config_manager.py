import os
import json
import base64
import threading
from core.crypto import HardwareEncryption

class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(ConfigManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, config_file=None):
        if self._initialized:
            return
        if config_file is None:
            config_file = os.path.join("AccountManagerData", "AccountData.enc")
        self.config_file = config_file
        self.lock = threading.Lock()
        self.config = {}
        self.accounts_cache = []
        self.load()
        self._initialized = True

    def load(self):
        with self.lock:
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, "rb") as f:
                        encrypted_data = f.read()
                    encryptor = HardwareEncryption()
                    self.config = encryptor.decrypt_data(encrypted_data)
                except:
                    self.config = {}
            else:
                self.config = {}
            accounts_dict = self.config.get('accounts', {})
            self.accounts_cache = [dict(v) for v in accounts_dict.values() if isinstance(v, dict)]

    def get(self, key, default=None):
        with self.lock:
            return self.config.get(key, default)

    def set(self, key, value):
        with self.lock:
            self.config[key] = value
            if key == 'accounts' and isinstance(value, dict):
                self.accounts_cache = [dict(v) for v in value.values() if isinstance(v, dict)]
        self.save_async()

    def save_async(self):
        config_copy = {}
        with self.lock:
            for k, v in self.config.items():
                try:
                    json.dumps({k: v})
                    config_copy[k] = v
                except:
                    pass
        def _write():
            with self.lock:
                try:
                    encryptor = HardwareEncryption()
                    encrypted_data = encryptor.encrypt_data(config_copy)
                    if isinstance(encrypted_data, str):
                        encrypted_data = base64.b64decode(encrypted_data)
                    with open(self.config_file, "wb") as f:
                        f.write(encrypted_data)
                except:
                    pass
        threading.Thread(target=_write, daemon=True).start()
