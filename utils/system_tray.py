import os
import sys
import threading
import win32api
import win32con
import win32gui

class WindowsSystemTray:
    def __init__(self, root, on_open, on_exit, icon_path=None):
        self.root = root
        self.on_open = on_open
        self.on_exit = on_exit
        self.icon_path = icon_path or ""
        self.hwnd = None
        self.notify_id = None
        self._start_tray()

    def _start_tray(self):
        self.thread = threading.Thread(target=self._create_hidden_window, daemon=True)
        self.thread.start()

    def _create_hidden_window(self):
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = "RobloxAccountManagerTrayWindow"
        wc.lpfnWndProc = self._wnd_proc
        try:
            class_atom = win32gui.RegisterClass(wc)
        except Exception:
            class_atom = None
        self.hwnd = win32gui.CreateWindow(
            "RobloxAccountManagerTrayWindow",
            "TrayWindow",
            0,
            0, 0, 0, 0,
            0, 0,
            wc.hInstance,
            None
        )
        win32gui.UpdateWindow(self.hwnd)
        hicon = None
        if self.icon_path and os.path.exists(self.icon_path):
            try:
                hicon = win32gui.LoadImage(
                    0, self.icon_path, win32con.IMAGE_ICON,
                    0, 0, win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
                )
            except Exception:
                pass
        if not hicon:
            hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        self.notify_id = (
            self.hwnd,
            0,
            win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            win32con.WM_USER + 20,
            hicon,
            "Roblox Account Manager"
        )
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, self.notify_id)
        win32gui.PumpMessages()

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_USER + 20:
            if lparam == win32con.WM_LBUTTONDBLCLK:
                self.root.after(0, self.on_open)
            elif lparam == win32con.WM_RBUTTONUP:
                self._show_menu()
        elif msg == win32con.WM_DESTROY:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, self.notify_id)
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _show_menu(self):
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1, "Open Manager")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 2, "Exit Completely")
        pos = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        selection = win32gui.TrackPopupMenu(
            menu,
            win32con.TPM_LEFTALIGN | win32con.TPM_RETURNCMD | win32con.TPM_NONOTIFY,
            pos[0], pos[1], 0,
            self.hwnd,
            None
        )
        win32gui.DestroyMenu(menu)
        if selection == 1:
            self.root.after(0, self.on_open)
        elif selection == 2:
            self.root.after(0, self.on_exit)

    def destroy(self):
        if self.hwnd:
            win32gui.PostMessage(self.hwnd, win32con.WM_DESTROY, 0, 0)
