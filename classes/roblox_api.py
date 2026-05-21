"""
Roblox API interaction utilities
Handles authentication, info, and game launching
"""

import os
import re
import json
import time
import random
import requests
import subprocess
import shutil
import threading
from pathlib import Path
from tkinter import messagebox


class RobloxAPI:
    """Handles all Roblox API interactions"""
    
    _rate_limiter_lock = threading.Lock()
    _last_request_time = None
    _min_interval = 6.0
    
    @classmethod
    def _wait_for_rate_limit(cls):
        with cls._rate_limiter_lock:
            if cls._last_request_time is not None:
                elapsed = time.time() - cls._last_request_time
                if elapsed < cls._min_interval:
                    wait_time = cls._min_interval - elapsed
                    print(f"[Rate Limiter] Waiting {wait_time:.1f}s before next API call...")
                    time.sleep(wait_time)
            cls._last_request_time = time.time()
    
    @staticmethod
    def quarantine_installers():
        """Move RobloxPlayerInstaller.exe files to quarantine to prevent installer popups"""
        local_appdata = os.getenv('LOCALAPPDATA')
        if not local_appdata:
            return
        
        versions_path = Path(local_appdata) / 'Roblox' / 'Versions'
        quarantine_path = Path(local_appdata) / 'RobloxAccountManager' / 'Quarantine'
        
        if not versions_path.exists():
            return
        
        quarantine_path.mkdir(parents=True, exist_ok=True)
        
        try:
            for folder in versions_path.iterdir():
                if folder.is_dir() and folder.name.startswith('version-'):
                    installer = folder / 'RobloxPlayerInstaller.exe'
                    if installer.exists():
                        try:
                            version_id = folder.name.split('-')[1]
                            version_quarantine = quarantine_path / version_id
                            version_quarantine.mkdir(exist_ok=True)
                            
                            dest = version_quarantine / 'RobloxPlayerInstaller.exe'
                            if not dest.exists():
                                shutil.move(str(installer), str(dest))
                                print(f"[INFO] Moved installer from {folder.name}")
                        except Exception as e:
                            print(f"[ERROR] Failed to move installer from {folder.name}: {e}")
        except Exception as e:
            print(f"[ERROR] Error accessing versions folder: {e}")
    
    @staticmethod
    def restore_installers():
        """Restore RobloxPlayerInstaller.exe files from quarantine"""
        local_appdata = os.getenv('LOCALAPPDATA')
        if not local_appdata:
            return
        
        versions_path = Path(local_appdata) / 'Roblox' / 'Versions'
        quarantine_path = Path(local_appdata) / 'RobloxAccountManager' / 'Quarantine'
        
        if not quarantine_path.exists():
            return
        
        try:
            for version_folder in quarantine_path.iterdir():
                if not version_folder.is_dir():
                    continue
                
                installer_q = version_folder / 'RobloxPlayerInstaller.exe'
                if not installer_q.exists():
                    continue
                
                roblox_folder = versions_path / f'version-{version_folder.name}'
                if not roblox_folder.exists():
                    continue
                
                installer_restore = roblox_folder / 'RobloxPlayerInstaller.exe'
                try:
                    shutil.move(str(installer_q), str(installer_restore))
                    print(f"[SUCCESS] Restored installer to {roblox_folder.name}")
                except Exception as e:
                    print(f"[ERROR] Failed to restore installer to {roblox_folder.name}: {e}")
            
            try:
                shutil.rmtree(str(quarantine_path), ignore_errors=True)
                print("[SUCCESS] Cleaned up quarantine folder")
            except:
                pass
        except Exception as e:
            print(f"[ERROR] Error restoring installers: {e}")
    
    @staticmethod
    def resolve_share_url(url_or_code, cookie=None):
        if not url_or_code:
            return None, None
        try:
            vip_match = re.search(
                r'roblox\.com/games/(\d+)/[^?#]*\?[^#]*privateServerLinkCode=([A-Za-z0-9]+)',
                url_or_code
            )
            if vip_match:
                return vip_match.group(1), vip_match.group(2)

            share_match = re.search(
                r'roblox\.com/share[^?#]*[?&]code=([A-Za-z0-9]+)',
                url_or_code
            )
            if not share_match:
                return None, None

            code = share_match.group(1)
            print(f"[INFO] Resolving share link code: {code[:8]}...")

            api_headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            if cookie:
                api_headers['Cookie'] = f'.ROBLOSECURITY={cookie}'

            if cookie:
                csrf_token = RobloxAPI.get_csrf_token(cookie)
                if csrf_token:
                    api_headers['X-CSRF-TOKEN'] = csrf_token

            for payload in [
                {"linkId": code, "linkType": "Server"},
                {"code": code, "type": "Server"},
            ]:
                try:
                    api_resp = requests.post(
                        "https://apis.roblox.com/sharelinks/v1/resolve-link",
                        json=payload, headers=api_headers, timeout=10
                    )
                    if api_resp.status_code == 200:
                        raw = api_resp.text
                        pid_m = re.search(r'"placeId"\s*:\s*(\d+)', raw)
                        lc_m = re.search(
                            r'"(?:linkCode|privateServerLinkCode|accessCode|linkcode)"\s*:\s*"([A-Za-z0-9_\-]+)"',
                            raw
                        )
                        if pid_m and lc_m:
                            print(f"[INFO] Resolved share link: placeId={pid_m.group(1)}")
                            return pid_m.group(1), lc_m.group(1)
                    elif api_resp.status_code == 403 and 'x-csrf-token' in api_resp.headers:
                        api_headers['X-CSRF-TOKEN'] = api_resp.headers['x-csrf-token']
                        retry = requests.post(
                            "https://apis.roblox.com/sharelinks/v1/resolve-link",
                            json=payload, headers=api_headers, timeout=10
                        )
                        if retry.status_code == 200:
                            raw = retry.text
                            pid_m = re.search(r'"placeId"\s*:\s*(\d+)', raw)
                            lc_m = re.search(
                                r'"(?:linkCode|privateServerLinkCode|accessCode|linkcode)"\s*:\s*"([A-Za-z0-9_\-]+)"',
                                raw
                            )
                            if pid_m and lc_m:
                                print(f"[INFO] Resolved share link: placeId={pid_m.group(1)}")
                                return pid_m.group(1), lc_m.group(1)
                except Exception as e:
                    print(f"[ERROR] resolve-link request failed: {e}")

        except Exception as e:
            print(f"[ERROR] Failed to resolve share URL: {e}")
        return None, None

    @staticmethod
    def get_username_from_api(roblosecurity_cookie):
        """Get username using Roblox API"""
        try:
            headers = {
                'Cookie': f'.ROBLOSECURITY={roblosecurity_cookie}'
            }
            
            response = requests.get(
                'https://users.roblox.com/v1/users/authenticated',
                headers=headers,
                timeout=3
            )
            
            if response.status_code == 200:
                user_data = response.json()
                return user_data.get('name', 'Unknown')
            
        except Exception as e:
            print(f"[ERROR] Error getting username from API: {e}")
        
        return "Unknown"
    
    @staticmethod
    def get_game_name(place_id):
        """Fetch game name from Roblox API"""
        if not place_id or not place_id.isdigit():
            return None
        
        try:
            place_url = f"https://apis.roblox.com/universes/v1/places/{place_id}/universe"
            place_response = requests.get(place_url, timeout=5)
            
            if place_response.status_code == 200:
                place_data = place_response.json()
                universe_id = place_data.get("universeId")
                
                if universe_id:
                    game_url = f"https://games.roblox.com/v1/games?universeIds={universe_id}"
                    game_response = requests.get(game_url, timeout=5)
                    
                    if game_response.status_code == 200:
                        game_data = game_response.json()
                        if game_data and game_data.get("data") and len(game_data["data"]) > 0:
                            return game_data["data"][0].get("name", None)
        except:
            pass
        return None
    
    @staticmethod
    def get_csrf_token(cookie, proxy=None):
        """Get CSRF token for authenticated requests"""
        url = "https://auth.roblox.com/v2/logout"
        headers = {
            'Cookie': f'.ROBLOSECURITY={cookie}'
        }
        
        try:
            req_proxies = None
            if proxy:
                req_proxies = {
                    "http": proxy if "://" in proxy else f"http://{proxy}",
                    "https": proxy if "://" in proxy else f"http://{proxy}"
                }
            response = requests.post(url, headers=headers, proxies=req_proxies, timeout=5)
            return response.headers.get('x-csrf-token')
        except:
            return None
    
    
    @staticmethod
    def get_user_id_from_username(username, max_retries=3, use_cache=True, cache_dict=None):
        """Get user ID from username"""
        if use_cache and cache_dict and username in cache_dict:
            cached_id = cache_dict[username]
            print(f"[INFO] Using cached user ID for '{username}': {cached_id}")
            return cached_id
        
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {
            "usernames": [username],
            "excludeBannedUsers": False
        }
        
        for attempt in range(max_retries):
            try:
                RobloxAPI._wait_for_rate_limit()
                
                response = requests.post(url, json=payload, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('data') and len(data['data']) > 0:
                        user_id = data['data'][0]['id']
                        
                        if use_cache and cache_dict is not None:
                            cache_dict[username] = user_id
                            print(f"[INFO] Stored user ID for '{username}': {user_id}")
                        
                        return user_id
                    else:
                        print(f"[WARNING] No user data found for username '{username}'")
                        return None
                elif response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 2 ** attempt))
                    print(f"[WARNING] Rate limited getting user ID for '{username}'. Retrying in {retry_after}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_after)
                    continue
                else:
                    print(f"[WARNING] API returned status {response.status_code} for username '{username}'")
                    if attempt < max_retries - 1:
                        delay = 2 ** attempt
                        print(f"[WARNING] Retrying in {delay}s... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
                    
            except requests.exceptions.Timeout:
                print(f"[ERROR] Timeout getting user ID for '{username}' (Attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except Exception as e:
                print(f"[ERROR] Exception getting user ID for '{username}': {e} (Attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
        
        return None
    
    @staticmethod
    def get_username_from_user_id(user_id):
        """Get username from user ID using Roblox API"""
        try:
            url = f"https://users.roblox.com/v1/users/{user_id}"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('name', data.get('displayName', None))
            else:
                print(f"[WARNING] Failed to get username for user ID {user_id}: Status {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Failed to get username for user ID {user_id}: {e}")
        
        return None
    
    @staticmethod
    def get_user_avatar_url(user_id, size="150x150"):
        """Get user avatar/thumbnail URL from Roblox API"""
        try:
            url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size={size}&format=Png&isCircular=false"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('data') and len(data['data']) > 0:
                    image_url = data['data'][0].get('imageUrl')
                    return image_url
            else:
                print(f"[WARNING] Failed to get avatar for user ID {user_id}: Status {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Failed to get avatar for user ID {user_id}: {e}")
        
        return None
    
    @staticmethod
    def get_player_presence(user_id, cookie):
        """Get player's current presence (online status and game info)"""
        url = "https://presence.roblox.com/v1/presence/users"
        
        csrf_token = RobloxAPI.get_csrf_token(cookie)
        if not csrf_token:
            print("[ERROR] Failed to get CSRF token")
            return None
        
        headers = {
            'Cookie': f'.ROBLOSECURITY={cookie}',
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': csrf_token
        }
        
        payload = {
            "userIds": [user_id]
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('userPresences') and len(data['userPresences']) > 0:
                    presence = data['userPresences'][0]
                    
                    result = {
                        'user_id': presence.get('userId'),
                        'in_game': presence.get('userPresenceType') == 2,
                        'status': presence.get('userPresenceType', 0),
                        'last_location': presence.get('lastLocation', 'Unknown')
                    }
                    
                    if presence.get('userPresenceType') == 2:
                        result['place_id'] = presence.get('placeId')
                        result['root_place_id'] = presence.get('rootPlaceId')
                        result['universe_id'] = presence.get('universeId')
                        result['game_id'] = presence.get('gameId')
                    
                    return result
            else:
                print(f"[ERROR] Presence API returned status {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Failed to get player presence: {e}")
        
        return None
    
    @staticmethod
    def get_auth_ticket(roblosecurity_cookie, proxy=None):
        """Get authentication ticket for launching Roblox games"""
        url = "https://auth.roblox.com/v1/authentication-ticket/"
        headers = {
            "User-Agent": "Roblox/WinInet",
            "Referer": "https://www.roblox.com/develop",
            "RBX-For-Gameauth": "true",
            "Content-Type": "application/json",
            "Cookie": f".ROBLOSECURITY={roblosecurity_cookie}"
        }

        req_proxies = None
        if proxy:
            req_proxies = {
                "http": proxy if "://" in proxy else f"http://{proxy}",
                "https": proxy if "://" in proxy else f"http://{proxy}"
            }

        try:
            response = requests.post(url, headers=headers, proxies=req_proxies, timeout=5)
            if response.status_code == 401:
                print("[ERROR] Session expired (401 Unauthorized) for the account.")
                return "EXPIRED"
            if response.status_code == 403 and "x-csrf-token" in response.headers:
                csrf_token = response.headers["x-csrf-token"]
            else:
                print(f"[ERROR] Failed to get CSRF token, status: {response.status_code}")
                return None

            headers["X-CSRF-TOKEN"] = csrf_token

            for attempt in range(4):
                response2 = requests.post(url, headers=headers, proxies=req_proxies, timeout=5)
                if response2.status_code == 401:
                    print("[ERROR] Session expired (401 Unauthorized) for the account.")
                    return "EXPIRED"
                elif response2.status_code == 200:
                    auth_ticket = response2.headers.get("rbx-authentication-ticket")
                    if auth_ticket:
                        return auth_ticket
                    print("[ERROR] Authentication ticket header missing in response.")
                    return None
                elif response2.status_code == 429:
                    wait = 2 ** attempt
                    print(f"[WARNING] Auth ticket rate limited (429), retrying in {wait}s... (attempt {attempt + 1}/4)")
                    time.sleep(wait)
                else:
                    print(f"[ERROR] Failed to get auth ticket, status: {response2.status_code}")
                    return None

            print("[ERROR] Auth ticket still rate limited after retries.")
            return None

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Request failed: {e}")
            return None
    
    @staticmethod
    def get_smallest_server(place_id):
        """Get the game server with the smallest player count for a given place ID"""
        try:
            url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?sortOrder=Asc&limit=100"
            headers = {
                "User-Agent": "Roblox/WinInet"
            }
            
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                servers = data.get('data', [])
                
                if servers:
                    available_servers = [s for s in servers if s.get('playing', 0) < s.get('maxPlayers', 100)]
                    
                    if available_servers:
                        smallest = min(available_servers, key=lambda x: x.get('playing', 0))
                        return smallest.get('id')
                    else:
                        smallest = min(servers, key=lambda x: x.get('playing', 0))
                        return smallest.get('id')
                else:
                    print("[WARNING] No servers found for place")
                    return None
            else:
                print(f"[ERROR] Failed to get servers: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[ERROR] Failed to get smallest server: {e}")
            return None
    
    
    @staticmethod
    def launch_roblox(username, cookie, game_id, private_server_id="", launcher_preference="default", job_id="", custom_launcher_path="", proxy=""):
        """Launch Roblox game with specified account"""

        print(f"[INFO] Getting authentication ticket for {username}...")
        auth_ticket = RobloxAPI.get_auth_ticket(cookie, proxy=proxy)
        if auth_ticket == "EXPIRED":
            messagebox.showerror(
                "Session Expired",
                f"ERROR: Account Session Expired for '{username}'!\n\n"
                "Please log in again or re-import the cookie."
            )
            return "EXPIRED"
        if not auth_ticket:
            print("[ERROR] Failed to get authentication ticket")
            return False

        print("[SUCCESS] Got authentication ticket!")

        browser_tracker_id = random.randint(55393295400, 55393295500)
        if not hasattr(RobloxAPI, "launch_trackers"):
            RobloxAPI.launch_trackers = {}
        RobloxAPI.launch_trackers[str(browser_tracker_id)] = username
        launch_time = int(time.time() * 1000)

        if not game_id and not private_server_id:
            url = (
                "roblox-player:1+launchmode:play+gameinfo:" + auth_ticket +
                "+launchtime:" + str(launch_time) +
                "+browsertrackerid:" + str(browser_tracker_id) +
                "+robloxLocale:en_us+gameLocale:en_us"
            )
            print(f"[INFO] Launching Roblox Home for {username}")
            return RobloxAPI._execute_launch(url, launcher_preference, custom_launcher_path, proxy=proxy)

        link_code = None

        if private_server_id:
            ps = private_server_id.strip()
            if ps.isdigit():
                link_code = ps
            else:
                resolved_pid, resolved_lc = RobloxAPI.resolve_share_url(ps, cookie=cookie)
                if resolved_lc:
                    if not game_id:
                        game_id = resolved_pid
                    link_code = resolved_lc
                    print(f"[INFO] Private server VIP link code resolved")
                else:
                    print("[ERROR] Invalid private server input. Expected a numeric code, VIP URL, or share link.")
                    messagebox.showerror(
                        "Invalid Private Server",
                        "Could not parse the private server input.\n\n"
                        "Accepted formats:\n"
                        "• Numeric link code (e.g. 12345678...)\n"
                        "• VIP URL (.../games/{id}/...?privateServerLinkCode=...)\n"
                        "• Share URL (roblox.com/share?code=...&type=Server)"
                    )
                    return False

        if not game_id:
            print("[ERROR] No Place ID provided.")
            return False

        url = (
            "roblox-player:1+launchmode:play+gameinfo:" + auth_ticket +
            "+launchtime:" + str(launch_time) +
            "+placelauncherurl:https://assetgame.roblox.com/game/PlaceLauncher.ashx?request=RequestGameJob" +
            "&browserTrackerId=" + str(browser_tracker_id) +
            "&placeId=" + str(game_id) +
            "&isPlayTogetherGame=false"
        )

        if link_code:
            url += "&linkCode=" + link_code
        elif job_id:
            url += "&gameId=" + str(job_id)

        url += (
            "+browsertrackerid:" + str(browser_tracker_id) +
            "+robloxLocale:en_us+gameLocale:en_us"
        )

        print(f"[INFO] Launching Roblox for {username}...")
        print(f"[INFO] Place ID: {game_id}")
        if link_code:
            print(f"[INFO] Private server (link code: {link_code})")
        elif job_id:
            print(f"[INFO] Job ID: {job_id}")
        print(f"[INFO] Launcher: {launcher_preference}")

        return RobloxAPI._execute_launch(url, launcher_preference, custom_launcher_path, proxy=proxy)
    
    @staticmethod
    def _execute_launch(url, launcher_preference, custom_launcher_path="", proxy=""):
        """Execute the Roblox launch with the specified launcher"""
        try:
            if proxy and proxy.strip() and launcher_preference == "default":
                print(f"[INFO] Account has proxy configured; falling back to direct client execution to pass --proxy-server argument.")
                launcher_preference = "client"

            if launcher_preference == "custom":
                custom_path = Path(str(custom_launcher_path or "").strip())
                if not custom_path:
                    messagebox.showerror("Custom Launcher Not Set", "Please choose a custom launcher .exe path in Roblox Launcher settings.")
                    return False
                if custom_path.suffix.lower() != ".exe":
                    messagebox.showerror("Invalid Custom Launcher", f"Custom launcher must be an .exe file.\n\nSelected:\n{custom_path}")
                    return False
                if not custom_path.exists():
                    messagebox.showerror("Custom Launcher Not Found", f"Custom launcher executable was not found.\n\nPath:\n{custom_path}")
                    return False

                args = [str(custom_path)]
                if proxy and proxy.strip():
                    args.append(f"--proxy-server={proxy.strip()}")
                args.append(url)
                
                subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
                print(f"[SUCCESS] Launched with Custom Launcher: {custom_path}")
                return True

            if launcher_preference == "bloxstrap":
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    messagebox.showerror("Error", "Could not find LOCALAPPDATA directory.")
                    return False
                
                bloxstrap_path = Path(local_appdata) / 'Bloxstrap' / 'Bloxstrap.exe'
                if not bloxstrap_path.exists():
                    messagebox.showerror(
                        "Bloxstrap Not Found",
                        f"Bloxstrap is not installed.\n\nExpected location:\n{bloxstrap_path}\n\nPlease install Bloxstrap or select a different launcher."
                    )
                    return False
                
                args = [str(bloxstrap_path), "-player"]
                if proxy and proxy.strip():
                    args.append(f"--proxy-server={proxy.strip()}")
                args.append(url)

                subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
                print("[SUCCESS] Launched with Bloxstrap!")
                return True
            
            elif launcher_preference == "fishstrap":
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    messagebox.showerror("Error", "Could not find LOCALAPPDATA directory.")
                    return False
                
                fishstrap_path = Path(local_appdata) / 'Fishstrap' / 'Fishstrap.exe'
                if not fishstrap_path.exists():
                    messagebox.showerror(
                        "Fishstrap Not Found",
                        f"Fishstrap is not installed.\n\nExpected location:\n{fishstrap_path}\n\nPlease install Fishstrap or select a different launcher."
                    )
                    return False
                
                args = [str(fishstrap_path), "-player"]
                if proxy and proxy.strip():
                    args.append(f"--proxy-server={proxy.strip()}")
                args.append(url)

                subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
                print("[SUCCESS] Launched with Fishstrap!")
                return True
            
            elif launcher_preference == "froststrap":
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    messagebox.showerror("Error", "Could not find LOCALAPPDATA directory.")
                    return False
                
                froststrap_path = Path(local_appdata) / 'Froststrap' / 'Froststrap.exe'
                if not froststrap_path.exists():
                    messagebox.showerror(
                        "Froststrap Not Found",
                        f"Froststrap is not installed.\n\nExpected location:\n{froststrap_path}\n\nPlease install Froststrap or select a different launcher."
                    )
                    return False
                
                args = [str(froststrap_path), "-player"]
                if proxy and proxy.strip():
                    args.append(f"--proxy-server={proxy.strip()}")
                args.append(url)

                subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
                print("[SUCCESS] Launched with Froststrap!")
                return True
            
            elif launcher_preference == "voidstrap":
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    messagebox.showerror("Error", "Could not find LOCALAPPDATA directory.")
                    return False
                
                voidstrap_path = Path(local_appdata) / 'Voidstrap' / 'Voidstrap.exe'
                if not voidstrap_path.exists():
                    messagebox.showerror(
                        "Voidstrap Not Found",
                        f"Voidstrap is not installed.\n\nExpected location:\n{voidstrap_path}\n\nPlease install Voidstrap or select a different launcher."
                    )
                    return False
                
                args = [str(voidstrap_path), "-player"]
                if proxy and proxy.strip():
                    args.append(f"--proxy-server={proxy.strip()}")
                args.append(url)

                subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
                print("[SUCCESS] Launched with Voidstrap!")
                return True
            
            elif launcher_preference == "client":
                RobloxAPI.quarantine_installers()
                
                local_appdata = os.getenv('LOCALAPPDATA')
                if not local_appdata:
                    messagebox.showerror("Error", "Could not find LOCALAPPDATA directory.")
                    return False
                
                versions_dir = Path(local_appdata) / 'Roblox' / 'Versions'
                if not versions_dir.exists():
                    messagebox.showerror(
                        "Roblox Client Not Found",
                        f"Roblox client directory not found.\n\nExpected location:\n{versions_dir}\n\nPlease install Roblox or select a different launcher."
                    )
                    return False
                
                version_folders = [d for d in versions_dir.iterdir() if d.is_dir() and d.name.startswith('version-')]
                if not version_folders:
                    messagebox.showerror(
                        "Roblox Client Not Found",
                        f"No Roblox version found in:\n{versions_dir}\n\nPlease reinstall Roblox or select a different launcher."
                    )
                    return False
                
                latest_version = max(version_folders, key=lambda x: x.stat().st_mtime)
                client_path = latest_version / 'RobloxPlayerBeta.exe'
                
                if not client_path.exists():
                    messagebox.showerror(
                        "Roblox Client Not Found",
                        f"RobloxPlayerBeta.exe not found in:\n{latest_version}\n\nPlease reinstall Roblox or select a different launcher."
                    )
                    return False
                
                args = [str(client_path)]
                if proxy and proxy.strip():
                    args.append(f"--proxy-server={proxy.strip()}")
                args.append(url)

                subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
                print(f"[SUCCESS] Launched with Roblox Client from {latest_version.name}!")
                return True
            
            else:
                os.startfile(url)
                print("[SUCCESS] Roblox launched successfully!")
                return True
                
        except Exception as e:
            print(f"[ERROR] Failed to launch Roblox: {e}")
            messagebox.showerror("Launch Error", f"Failed to launch Roblox:\n\n{str(e)}")
            return False
    
    @staticmethod
    def validate_account(username, cookie, proxy=None):
        """Validate if an account's cookie is still valid"""
        try:
            headers = {
                'Cookie': f'.ROBLOSECURITY={cookie}'
            }
            
            req_proxies = None
            if proxy:
                req_proxies = {
                    "http": proxy if "://" in proxy else f"http://{proxy}",
                    "https": proxy if "://" in proxy else f"http://{proxy}"
                }
                
            response = requests.get(
                'https://users.roblox.com/v1/users/authenticated',
                headers=headers,
                proxies=req_proxies,
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False

    @staticmethod
    def set_xml_framerate_cap(fps_cap):
        """Set the Roblox global framerate cap in GlobalBasicSettings_13.xml"""
        try:
            import os
            import stat
            import re
            
            local_appdata = os.getenv('LOCALAPPDATA')
            if not local_appdata:
                print("[ERROR] LOCALAPPDATA environment variable not found.")
                return False
                
            xml_path = os.path.join(local_appdata, 'Roblox', 'GlobalBasicSettings_13.xml')
            
            # Ensure the Roblox folder exists
            os.makedirs(os.path.dirname(xml_path), exist_ok=True)
            
            content = ""
            file_exists = os.path.exists(xml_path)
            original_mode = None
            
            if file_exists:
                # Remove read-only attribute if it is set
                try:
                    original_mode = os.stat(xml_path).st_mode
                    if not (original_mode & stat.S_IWRITE):
                        os.chmod(xml_path, stat.S_IWRITE)
                except Exception as chmod_err:
                    print(f"[WARNING] Failed to query/modify permissions on {xml_path}: {chmod_err}")
                
                try:
                    with open(xml_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                except Exception as e:
                    print(f"[ERROR] Failed to read {xml_path}: {e}")
                    if file_exists and original_mode is not None and not (original_mode & stat.S_IWRITE):
                        try:
                            os.chmod(xml_path, original_mode)
                        except:
                            pass
                    return False
            else:
                # Minimal XML template
                content = (
                    '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
                    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                    'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">\n'
                    '\t<External>null</External>\n'
                    '\t<External>nil</External>\n'
                    '\t<Item class="UserGameSettings" referent="RBX794959B217D94CBE9846638A8FAF70E4">\n'
                    '\t\t<Properties>\n'
                    '\t\t</Properties>\n'
                    '\t</Item>\n'
                    '</roblox>'
                )
            
            # Replace/insert the FramerateCap
            pattern = re.compile(r'<int\s+name="FramerateCap">(\d+)</int>')
            if pattern.search(content):
                new_content = pattern.sub(f'<int name="FramerateCap">{fps_cap}</int>', content)
            else:
                # Insert inside <Properties>
                props_pattern = re.compile(r'<Properties>')
                if props_pattern.search(content):
                    new_content = props_pattern.sub(f'<Properties>\n\t\t\t<int name="FramerateCap">{fps_cap}</int>', content)
                else:
                    print("[ERROR] <Properties> block not found in GlobalBasicSettings_13.xml")
                    if file_exists and original_mode is not None and not (original_mode & stat.S_IWRITE):
                        try:
                            os.chmod(xml_path, original_mode)
                        except:
                            pass
                    return False
            
            try:
                with open(xml_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"[SUCCESS] Set Roblox FramerateCap to {fps_cap} in {xml_path}")
            except Exception as e:
                print(f"[ERROR] Failed to write to {xml_path}: {e}")
                return False
            finally:
                # Always restore read-only attribute if file exists and was read-only
                if file_exists and original_mode is not None and not (original_mode & stat.S_IWRITE):
                    try:
                        os.chmod(xml_path, original_mode)
                    except Exception as chmod_err:
                        print(f"[WARNING] Failed to restore permissions on {xml_path}: {chmod_err}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to set XML framerate cap: {e}")
            return False

    @staticmethod
    def apply_graphics_optimization(enabled=True):
        """Configure local ClientAppSettings.json in active Roblox player version directory to optimize graphics rendering"""
        try:
            import os
            import json
            local_appdata = os.getenv('LOCALAPPDATA')
            if not local_appdata:
                return False
                
            opt_flags = {
                "FIntRomRenderGlobalTextureQualityOverride": 3,
                "FFlagDebugDisableDirect3D11": "True",
                "FFlagRomRenderLightGridShadows": "False",
                "FFlagRomRenderGlobalShadows": "False",
                "FIntRenderLODDistanceScalePercent": 10
            }
            
            applied = False
            launcher_roots = ['Roblox', 'Bloxstrap', 'Fishstrap', 'Froststrap', 'Voidstrap']
            for root in launcher_roots:
                versions_dir = os.path.join(local_appdata, root, 'Versions')
                if os.path.exists(versions_dir):
                    for item in os.listdir(versions_dir):
                        item_path = os.path.join(versions_dir, item)
                        if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, 'RobloxPlayerBeta.exe')):
                            client_settings_dir = os.path.join(item_path, 'ClientSettings')
                            if not os.path.exists(client_settings_dir):
                                os.makedirs(client_settings_dir)
                                
                            settings_file = os.path.join(client_settings_dir, 'ClientAppSettings.json')
                            settings = {}
                            if os.path.exists(settings_file):
                                try:
                                    with open(settings_file, 'r', encoding='utf-8') as f:
                                        settings = json.load(f)
                                except Exception:
                                    settings = {}
                                    
                            if enabled:
                                settings.update(opt_flags)
                                if "DFIntTaskSchedulerTargetFps" in settings:
                                    del settings["DFIntTaskSchedulerTargetFps"]
                                print(f"[Graphics Optimizer] Optimization enabled. Rendering overrides applied to: {settings_file}")
                            else:
                                for k in opt_flags.keys():
                                    if k in settings:
                                        del settings[k]
                                if "DFIntTaskSchedulerTargetFps" in settings:
                                    del settings["DFIntTaskSchedulerTargetFps"]
                                print(f"[Graphics Optimizer] Optimization disabled. Restoring default overrides in: {settings_file}")
                                        
                            with open(settings_file, 'w', encoding='utf-8') as f:
                                json.dump(settings, f, indent=2)
                            applied = True
                
                if root == 'Bloxstrap':
                    mods_client_settings_dir = os.path.join(local_appdata, 'Bloxstrap', 'Modifications', 'ClientSettings')
                    if enabled:
                        if not os.path.exists(mods_client_settings_dir):
                            try:
                                os.makedirs(mods_client_settings_dir)
                            except:
                                pass
                    if os.path.exists(mods_client_settings_dir):
                        mods_settings_file = os.path.join(mods_client_settings_dir, 'ClientAppSettings.json')
                        settings = {}
                        if os.path.exists(mods_settings_file):
                            try:
                                with open(mods_settings_file, 'r', encoding='utf-8') as f:
                                    settings = json.load(f)
                            except Exception:
                                settings = {}
                        if enabled:
                            settings.update(opt_flags)
                            if "DFIntTaskSchedulerTargetFps" in settings:
                                del settings["DFIntTaskSchedulerTargetFps"]
                            print(f"[Graphics Optimizer] Optimization enabled. Rendering overrides applied to Bloxstrap mods: {mods_settings_file}")
                        else:
                            for k in opt_flags.keys():
                                if k in settings:
                                    del settings[k]
                            if "DFIntTaskSchedulerTargetFps" in settings:
                                del settings["DFIntTaskSchedulerTargetFps"]
                            print(f"[Graphics Optimizer] Optimization disabled. Restoring default overrides in Bloxstrap mods: {mods_settings_file}")
                        with open(mods_settings_file, 'w', encoding='utf-8') as f:
                            json.dump(settings, f, indent=2)
                        applied = True
            
            # Apply or revert XML framerate cap
            RobloxAPI.set_xml_framerate_cap(30 if enabled else 60)
            return applied
        except Exception as e:
            print(f"[Graphics Optimizer Error] Failed to configure ClientAppSettings: {e}")
            return False
