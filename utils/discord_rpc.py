import os
import json
import struct
import time
import threading

class DiscordRPC:
    def __init__(self, client_id, enabled=True):
        self.client_id = str(client_id)
        self._lock = threading.Lock()
        self._enabled = enabled
        self._presence_state = {
            "state": None,
            "details": None,
            "large_image": None,
            "large_text": None,
            "small_image": None,
            "small_text": None,
            "start_time": int(time.time()),
            "dirty": False
        }
        self._shutdown_event = threading.Event()
        self._worker_thread = None
        if self._enabled:
            self._start_worker()

    def _start_worker(self):
        with self._lock:
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._shutdown_event.clear()
                self._worker_thread = threading.Thread(
                    target=self._isolated_presence_worker,
                    daemon=True,
                    name="DiscordPresenceWorker"
                )
                self._worker_thread.start()

    def set_activity(self, state=None, details=None, large_image=None, large_text=None, small_image=None, small_text=None, start_time=None):
        if not self._enabled:
            return False
        with self._lock:
            self._presence_state["state"] = state
            self._presence_state["details"] = details
            self._presence_state["large_image"] = large_image or "https://raw.githubusercontent.com/evanovar/RobloxAccountManager/main/discordlogo.png"
            self._presence_state["large_text"] = large_text or "Account Manager by Nerd"
            self._presence_state["small_image"] = small_image
            self._presence_state["small_text"] = small_text
            if start_time is not None:
                self._presence_state["start_time"] = start_time
            self._presence_state["dirty"] = True
        self._start_worker()
        return True

    def close(self):
        self._shutdown_event.set()
        worker = self._worker_thread
        if worker and worker.is_alive():
            worker.join(timeout=2.0)
        with self._lock:
            self._worker_thread = None
            self._presence_state["dirty"] = False

    def _isolated_presence_worker(self):
        ipc_pipe = None
        last_dispatch_time = 0.0
        backoff_delay = 5.0
        max_backoff = 60.0
        COOLDOWN_WINDOW = 15.0
        
        while not self._shutdown_event.is_set():
            if not self._enabled:
                if ipc_pipe:
                    try:
                        ipc_pipe.close()
                    except:
                        pass
                break
                
            if ipc_pipe is None:
                connected = False
                for i in range(10):
                    if self._shutdown_event.is_set():
                        break
                    pipe_path = f"\\\\.\\pipe\\discord-ipc-{i}"
                    try:
                        ipc_pipe = open(pipe_path, 'r+b', buffering=0)
                        connected = True
                        break
                    except Exception:
                        continue
                
                if not connected:
                    ipc_pipe = None
                    self._shutdown_event.wait(backoff_delay)
                    backoff_delay = min(backoff_delay * 3.0, max_backoff)
                    continue
                else:
                    backoff_delay = 5.0
                    try:
                        handshake_payload = {"v": 1, "client_id": self.client_id}
                        self._send_raw(ipc_pipe, 0, handshake_payload)
                        self._read_raw(ipc_pipe)
                        last_dispatch_time = 0.0
                    except Exception:
                        try:
                            ipc_pipe.close()
                        except:
                            pass
                        ipc_pipe = None
                        continue
            
            current_time = time.time()
            is_dirty = False
            state_copy = {}
            
            with self._lock:
                if self._presence_state["dirty"]:
                    is_dirty = True
                    state_copy = self._presence_state.copy()
            
            if is_dirty:
                time_since_last_dispatch = current_time - last_dispatch_time
                if time_since_last_dispatch >= COOLDOWN_WINDOW:
                    activity = {
                        "timestamps": {"start": state_copy["start_time"]},
                        "assets": {
                            "large_image": state_copy["large_image"],
                            "large_text": state_copy["large_text"]
                        }
                    }
                    if state_copy["state"]:
                        activity["state"] = state_copy["state"]
                    if state_copy["details"]:
                        activity["details"] = state_copy["details"]
                    if state_copy["small_image"]:
                        activity["assets"]["small_image"] = state_copy["small_image"]
                    if state_copy["small_text"]:
                        activity["assets"]["small_text"] = state_copy["small_text"]
                        
                    payload = {
                        "cmd": "SET_ACTIVITY",
                        "args": {
                            "pid": os.getpid(),
                            "activity": activity
                        },
                        "nonce": f"{current_time}"
                    }
                    
                    try:
                        self._send_raw(ipc_pipe, 1, payload)
                        self._read_raw(ipc_pipe)
                        last_dispatch_time = current_time
                        with self._lock:
                            self._presence_state["dirty"] = False
                    except Exception:
                        try:
                            ipc_pipe.close()
                        except:
                            pass
                        ipc_pipe = None
                        last_dispatch_time = 0.0
            
            self._shutdown_event.wait(2.0)
            
        if ipc_pipe:
            try:
                ipc_pipe.close()
            except:
                pass

    def _send_raw(self, pipe, op, payload):
        data = json.dumps(payload).encode('utf-8')
        header = struct.pack('<II', op, len(data))
        pipe.write(header + data)
        pipe.flush()

    def _read_raw(self, pipe):
        try:
            header = pipe.read(8)
            if len(header) < 8:
                return None, None
            op, length = struct.unpack('<II', header)
            data = pipe.read(length)
            return op, json.loads(data.decode('utf-8'))
        except Exception:
            return None, None
