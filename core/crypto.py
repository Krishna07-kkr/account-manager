import os
import json
import base64
import hashlib
import sys
import win32crypt

class HardwareEncryption:
    def __init__(self):
        self.entropy = b"roblox_account_manager_hardware_entropy"

    def encrypt_data(self, data):
        if isinstance(data, dict):
            data = json.dumps(data, indent=2, ensure_ascii=False)
        data_bytes = data.encode('utf-8')
        protected = win32crypt.CryptProtectData(data_bytes, "RobloxAccountManager", self.entropy, None, None, 1)
        return protected

    def decrypt_data(self, encrypted_package):
        if isinstance(encrypted_package, dict) and "nonce" in encrypted_package and "tag" in encrypted_package and "ciphertext" in encrypted_package:
            try:
                from Crypto.Cipher import AES
                from Crypto.Protocol.KDF import PBKDF2
                import platform
                import subprocess
                identifiers = []
                try:
                    if platform.system() == "Windows":
                        try:
                            result = subprocess.check_output("wmic csproduct get uuid", shell=True)
                            uuid = result.decode().split('\n')[1].strip()
                            identifiers.append(uuid)
                            result = subprocess.check_output("wmic cpu get processorid", shell=True)
                            cpu_id = result.decode().split('\n')[1].strip()
                            identifiers.append(cpu_id)
                            result = subprocess.check_output("wmic baseboard get serialnumber", shell=True)
                            board_serial = result.decode().split('\n')[1].strip()
                            identifiers.append(board_serial)
                        except Exception:
                            identifiers = [platform.node(), platform.machine()]
                    else:
                        identifiers.append(platform.node())
                        identifiers.append(str(os.getuid()) if hasattr(os, 'getuid') else "0")
                except:
                    identifiers = [platform.node(), platform.machine()]
                
                machine_string = "-".join(identifiers)
                machine_id = hashlib.sha256(machine_string.encode()).hexdigest()
                salt = b'roblox_account_manager_salt_v1'
                key = PBKDF2(machine_id, salt, dkLen=32, count=100000)
                nonce = base64.b64decode(encrypted_package['nonce'])
                tag = base64.b64decode(encrypted_package['tag'])
                ciphertext = base64.b64decode(encrypted_package['ciphertext'])
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                data_bytes = cipher.decrypt_and_verify(ciphertext, tag)
                decrypted_str = data_bytes.decode('utf-8')
                try:
                    return json.loads(decrypted_str)
                except:
                    return decrypted_str
            except Exception as e:
                raise ValueError(f"Legacy AES decryption failed: {e}")

        try:
            if isinstance(encrypted_package, dict) and "ciphertext" in encrypted_package:
                protected = base64.b64decode(encrypted_package["ciphertext"])
            elif isinstance(encrypted_package, str):
                protected = base64.b64decode(encrypted_package)
            else:
                protected = encrypted_package
            _, decrypted = win32crypt.CryptUnprotectData(protected, self.entropy, None, None, 1)
            decrypted_str = decrypted.decode('utf-8')
            try:
                return json.loads(decrypted_str)
            except:
                return decrypted_str
        except Exception:
            print("[ERROR] Cryptographic Access Violation: Unauthorized hardware decryption attempt detected.")
            sys.exit(1)

class PasswordEncryption:
    def __init__(self, password, salt=None):
        self.password = password
        self.salt = salt
        if isinstance(password, str):
            password = password.encode('utf-8')
        self.entropy = hashlib.sha256(password).digest()

    def get_salt_b64(self):
        return ""

    def encrypt_data(self, data):
        if isinstance(data, dict):
            data = json.dumps(data, indent=2, ensure_ascii=False)
        data_bytes = data.encode('utf-8')
        protected = win32crypt.CryptProtectData(data_bytes, "RobloxAccountManager", self.entropy, None, None, 1)
        return protected

    def decrypt_data(self, encrypted_package):
        if isinstance(encrypted_package, dict) and "nonce" in encrypted_package and "tag" in encrypted_package and "ciphertext" in encrypted_package:
            try:
                from Crypto.Cipher import AES
                from Crypto.Protocol.KDF import PBKDF2
                salt_bytes = base64.b64decode(self.salt) if isinstance(self.salt, str) else self.salt
                key = PBKDF2(self.password, salt_bytes, dkLen=32, count=100000)
                nonce = base64.b64decode(encrypted_package['nonce'])
                tag = base64.b64decode(encrypted_package['tag'])
                ciphertext = base64.b64decode(encrypted_package['ciphertext'])
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                data_bytes = cipher.decrypt_and_verify(ciphertext, tag)
                decrypted_str = data_bytes.decode('utf-8')
                try:
                    return json.loads(decrypted_str)
                except:
                    return decrypted_str
            except Exception as e:
                raise ValueError(f"Legacy AES password decryption failed: {e}")

        try:
            if isinstance(encrypted_package, dict) and "ciphertext" in encrypted_package:
                protected = base64.b64decode(encrypted_package["ciphertext"])
            elif isinstance(encrypted_package, str):
                protected = base64.b64decode(encrypted_package)
            else:
                protected = encrypted_package
            _, decrypted = win32crypt.CryptUnprotectData(protected, self.entropy, None, None, 1)
            decrypted_str = decrypted.decode('utf-8')
            try:
                return json.loads(decrypted_str)
            except:
                return decrypted_str
        except Exception:
            print("[ERROR] Cryptographic Access Violation: Unauthorized password decryption attempt detected.")
            sys.exit(1)

class EncryptionConfig:
    def __init__(self, config_file="encryption_config.json"):
        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_config(self):
        config_dir = os.path.dirname(self.config_file)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def is_encryption_enabled(self):
        return True

    def is_setup_complete(self):
        return True

    def get_encryption_method(self):
        return self.config.get('encryption_method', 'hardware')

    def get_salt(self):
        return self.config.get('salt', None)

    def get_password_hash(self):
        return self.config.get('password_hash', None)

    def enable_hardware_encryption(self):
        self.config['encryption_enabled'] = True
        self.config['encryption_method'] = 'hardware'
        self.config['setup_completed'] = True
        self.save_config()

    def enable_password_encryption(self, salt, password_hash):
        self.config['encryption_enabled'] = True
        self.config['encryption_method'] = 'password'
        self.config['salt'] = salt
        self.config['password_hash'] = password_hash
        self.config['password_verified'] = True
        self.config['setup_completed'] = True
        self.save_config()

    def is_password_verified(self):
        return self.config.get('password_verified', False)

    def disable_encryption(self):
        pass

    def reset_encryption(self):
        self.config.clear()
        self.save_config()

    def set_encryption_method(self, method):
        if method == 'hardware':
            self.enable_hardware_encryption()
        elif method == 'password':
            pass
        else:
            raise ValueError(f"Invalid encryption method: {method}")
