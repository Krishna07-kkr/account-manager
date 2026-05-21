import time
import threading
import psutil
import ctypes
from ctypes import wintypes
import win32gui
import win32con
import win32process
import autoit

class AntiAFKService:
    def __init__(self, config_manager, show_tooltip_callback=None, hide_tooltip_callback=None):
        self.config = config_manager
        self.show_tooltip = show_tooltip_callback
        self.hide_tooltip = hide_tooltip_callback
        self.thread = None
        self.stop_event = threading.Event()

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
        if self.hide_tooltip:
            self.hide_tooltip()

    def _worker(self):
        while not self.stop_event.is_set():
            try:
                interval_minutes = max(1, int(self.config.get("anti_afk_interval_minutes", 10)))
                press_count = max(1, int(self.config.get("anti_afk_press_count", 1)))
                action_key = str(self.config.get("anti_afk_key", "w") or "w").strip().lower()
                total_seconds = interval_minutes * 60
                countdown_seconds = min(30, total_seconds)
                wait_seconds = max(0, total_seconds - countdown_seconds)
                if wait_seconds > 0 and self.stop_event.wait(wait_seconds):
                    break
                for remaining in range(countdown_seconds, 0, -1):
                    if self.stop_event.is_set():
                        return
                    if self.show_tooltip:
                        self.show_tooltip(f"Anti-AFK Maintenance will start in {remaining}s")
                    if self.stop_event.wait(1):
                        return
                if self.hide_tooltip:
                    self.hide_tooltip()
                self._run_maintenance_cycle(action_key, press_count)
            except Exception:
                time.sleep(5)

    def _get_roblox_pids(self):
        pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'].lower() == 'robloxplayerbeta.exe':
                    pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return pids

    def _get_roblox_hwnds_from_pids(self, pids):
        hwnds = []
        def _cb(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in pids:
                    title = win32gui.GetWindowText(hwnd)
                    if "Roblox" in title:
                        hwnds.append(hwnd)
            return True
        win32gui.EnumWindows(_cb, None)
        return hwnds

    def _run_maintenance_cycle(self, action_key, press_count):
        pids = self._get_roblox_pids()
        if not pids:
            return
        hwnds = self._get_roblox_hwnds_from_pids(pids)
        if not hwnds:
            return
        try:
            original_hwnd = win32gui.GetForegroundWindow()
        except Exception:
            original_hwnd = None
        for hwnd in hwnds:
            if self.stop_event.is_set():
                break
            window_spec = f"[HANDLE:0x{hwnd:08X}]"
            try:
                try:
                    win32gui.SetWindowPos(
                        hwnd, 0,
                        100, 100, 0, 0,
                        win32con.SWP_NOSIZE | win32con.SWP_NOZORDER
                    )
                except Exception:
                    pass
                try:
                    autoit.win_activate(window_spec)
                except Exception:
                    win32gui.ShowWindow(hwnd, 9)
                    win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.15)
                try:
                    autoit.win_maximize(window_spec)
                except Exception:
                    win32gui.ShowWindow(hwnd, 3)
                time.sleep(0.15)
                for _ in range(max(1, int(press_count))):
                    if self.stop_event.is_set():
                        break
                    self._perform_action(action_key)
                    time.sleep(0.15)
                try:
                    win32gui.SetWindowPos(
                        hwnd, 0,
                        -32000, -32000, 0, 0,
                        win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                    )
                    win32gui.ShowWindow(hwnd, 8)
                except Exception:
                    try:
                        autoit.win_minimize(window_spec)
                    except Exception:
                        win32gui.ShowWindow(hwnd, 6)
                time.sleep(0.1)
            except Exception:
                pass
        if original_hwnd and win32gui.IsWindow(original_hwnd):
            try:
                original_spec = f"[HANDLE:0x{original_hwnd:08X}]"
                autoit.win_activate(original_spec)
            except Exception:
                try:
                    win32gui.SetForegroundWindow(original_hwnd)
                except Exception:
                    pass

    def _perform_action(self, action_key):
        mouse_actions = {
            "lmb": "left",
            "rmb": "right",
            "mmb": "middle",
        }
        if action_key in mouse_actions:
            button = mouse_actions[action_key]
            autoit.mouse_down(button)
            time.sleep(0.1)
            autoit.mouse_up(button)
            return
        if action_key == "scroll_up":
            autoit.mouse_wheel("up", 1)
            return
        if action_key == "scroll_down":
            autoit.mouse_wheel("down", 1)
            return
        autoit.send(f"{{{action_key.upper()} down}}")
        time.sleep(0.1)
        autoit.send(f"{{{action_key.upper()} up}}")
