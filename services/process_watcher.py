import os
import re
import time
import psutil
import ctypes
import threading
from datetime import datetime, timezone, timedelta
import win32api
import win32con
import win32gui
import win32process
from classes.roblox_api import RobloxAPI

class ProcessWatcherService:
    def __init__(self, manager, config_manager, summary_service, refresh_callback=None):
        self.manager = manager
        self.config = config_manager
        self.summary_service = summary_service
        self.refresh_callback = refresh_callback
        self.stop_event = threading.Event()
        self.thread = None
        self.instances_pids = set()
        self.instances_data = []
        self.instances_failed_pids = {}
        self.instances_cache = {"user_id_to_username": {}, "user_id_to_avatar": {}}
        self.proc_cpu_stats = {}
        self.auto_rejoin_pids = {}

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.stop_event.set()
            thread = self.thread
            def _join():
                thread.join(timeout=2)
            threading.Thread(target=_join, daemon=True).start()

    def _worker(self):
        last_memory_refresh = 0.0
        poll_interval_seconds = 4
        failed_retry_delay_seconds = 8
        persistent_procs = {}
        while not self.stop_event.is_set():
            try:
                new_pids = set()
                processes = []
                pid_to_proc = {}
                for proc in psutil.process_iter(['pid', 'name', 'create_time', 'memory_info']):
                    try:
                        if proc.info['name'] and proc.info['name'].lower() == 'robloxplayerbeta.exe':
                            pid = proc.info['pid']
                            if self._is_valid_roblox_game_client(pid, 'robloxplayerbeta.exe'):
                                new_pids.add(pid)
                                if pid not in persistent_procs:
                                    persistent_procs[pid] = proc
                                processes.append(persistent_procs[pid])
                                pid_to_proc[pid] = persistent_procs[pid]
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                active_pids = new_pids
                for cached_pid in list(persistent_procs.keys()):
                    if cached_pid not in active_pids:
                        del persistent_procs[cached_pid]
                        if cached_pid in self.proc_cpu_stats:
                            del self.proc_cpu_stats[cached_pid]
                current_time = time.time()
                for pid in list(self.instances_failed_pids.keys()):
                    if pid not in new_pids:
                        del self.instances_failed_pids[pid]
                self._apply_anti_throttling_offscreen(new_pids)
                if self.config.get("optimize_roblox_ram", False):
                    self._apply_ram_optimization(processes)
                if new_pids != self.instances_pids:
                    self.instances_pids = new_pids.copy()
                    old_data_by_pid = {entry['pid']: entry for entry in self.instances_data}
                    new_data = []
                    for proc in processes:
                        pid = proc.info['pid']
                        try:
                            memory_mb = proc.info['memory_info'].rss / 1024 / 1024
                            create_time = proc.info['create_time']
                        except Exception:
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
                    if self.refresh_callback:
                        self.refresh_callback()
                if current_time - last_memory_refresh >= poll_interval_seconds:
                    last_memory_refresh = current_time
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
                        if self.refresh_callback:
                            self.refresh_callback()
                    else:
                        self.instances_failed_pids[pid] = (current_time, 0)
                if self.summary_service:
                    self.summary_service.sync_active_instances(self.instances_data)
                self.stop_event.wait(1.5)
            except Exception:
                time.sleep(2)

    def _apply_anti_throttling_offscreen(self, pids):
        def _cb(hwnd, extra):
            if win32gui.IsWindow(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in pids:
                    title = win32gui.GetWindowText(hwnd)
                    if "Roblox" in title:
                        if win32gui.IsIconic(hwnd):
                            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                            win32gui.SetWindowPos(
                                hwnd, 0,
                                -32000, -32000, 0, 0,
                                win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                            )
                            win32gui.ShowWindow(hwnd, 8)
            return True
        win32gui.EnumWindows(_cb, None)

    def _apply_ram_optimization(self, processes):
        limit_mb = self.config.get("optimize_roblox_ram_limit_mb", 350)
        for proc in processes:
            try:
                rss = proc.info['memory_info'].rss / 1024 / 1024
                if rss > limit_mb:
                    handle = ctypes.windll.kernel32.OpenProcess(0x0500, False, proc.info['pid'])
                    if handle:
                        ctypes.windll.kernel32.SetProcessWorkingSetSize(handle, -1, -1)
                        ctypes.windll.kernel32.CloseHandle(handle)
            except:
                pass

    def _is_valid_roblox_game_client(self, pid, process_name_lower=None):
        try:
            if process_name_lower is None:
                process = psutil.Process(pid)
                process_name_lower = process.name().lower()
            if process_name_lower != "robloxplayerbeta.exe":
                return False
            desc = self._get_exe_description(pid)
            if desc:
                return "roblox" in desc.lower()
            return True
        except:
            return process_name_lower == "robloxplayerbeta.exe" if process_name_lower else False

    def _get_exe_description(self, pid):
        try:
            proc = psutil.Process(pid)
            exe = proc.exe()
            translations = win32api.GetFileVersionInfo(exe, r'\VarFileInfo\Translation')
            lang, codepage = translations[0]
            key = f'\\StringFileInfo\\{lang:04X}{codepage:04X}\\FileDescription'
            return win32api.GetFileVersionInfo(exe, key) or ""
        except:
            return ""

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
            except Exception:
                pass
            create_time_utc = datetime.fromtimestamp(process.create_time(), tz=timezone.utc).replace(tzinfo=None)
            logs_dir = os.path.join(os.getenv("LOCALAPPDATA"), "Roblox", "logs")
            if not os.path.exists(logs_dir):
                return None, None
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
                except Exception:
                    continue
            return None, None
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None, None
