import os
import json
import struct
import time
import threading
import uuid

_HEARTBEAT_INTERVAL = 4.0
_COOLDOWN_WINDOW = 15.0
_INITIAL_BACKOFF = 3.0
_MAX_BACKOFF = 60.0
_PIPE_COUNT = 10

class DiscordRPC:
    def __init__(self, client_id: str, enabled: bool = True):
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
            "buttons": None,
            "start_time": int(time.time()),
            "dirty": False
        }
        self._shutdown_event = threading.Event()
        self._worker_thread = None
        if self._enabled:
            self._start_worker()

    def set_activity(
        self,
        state: str = None,
        details: str = None,
        large_image: str = None,
        large_text: str = None,
        small_image: str = None,
        small_text: str = None,
        buttons: list = None,
        start_time: int = None
    ) -> bool:
        if not self._enabled:
            return False
        with self._lock:
            self._presence_state["state"] = state
            self._presence_state["details"] = details
            self._presence_state["large_image"] = (
                large_image or
                "https://raw.githubusercontent.com/ic3w0lf22/Roblox-Account-Manager/master/"
                "RBX%20Alt%20Manager/Resources/Roblox%20Account%20Manager.png"
            )
            self._presence_state["large_text"] = large_text or "Roblox Account Manager"
            self._presence_state["small_image"] = small_image
            self._presence_state["small_text"] = small_text
            self._presence_state["buttons"] = buttons
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

    def _start_worker(self):
        with self._lock:
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._shutdown_event.clear()
                self._worker_thread = threading.Thread(
                    target=self._presence_worker,
                    daemon=True,
                    name="DiscordPresenceWorker"
                )
                self._worker_thread.start()

    def _connect(self) -> object:
        for i in range(_PIPE_COUNT):
            if self._shutdown_event.is_set():
                return None
            try:
                pipe = open(f"\\\\.\\pipe\\discord-ipc-{i}", 'r+b', buffering=0)
                self._send_raw(pipe, 0, {"v": 1, "client_id": self.client_id})
                self._read_raw(pipe)
                return pipe
            except Exception:
                continue
        return None

    def _build_activity(self, state: dict) -> dict:
        activity = {
            "type": 0,
            "timestamps": {"start": state["start_time"]},
            "assets": {
                "large_image": state["large_image"],
                "large_text": state["large_text"]
            }
        }
        if state["state"]:
            activity["state"] = state["state"]
        if state["details"]:
            activity["details"] = state["details"]
        if state["small_image"]:
            activity["assets"]["small_image"] = state["small_image"]
        if state["small_text"]:
            activity["assets"]["small_text"] = state["small_text"]
        if state["buttons"]:
            activity["buttons"] = [
                {"label": b["label"][:32], "url": b["url"]}
                for b in state["buttons"][:2]
                if b.get("label") and b.get("url")
            ]
        return activity

    def _dispatch(self, pipe, activity: dict, nonce: str) -> bool:
        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {"pid": os.getpid(), "activity": activity},
            "nonce": nonce
        }
        try:
            self._send_raw(pipe, 1, payload)
            self._read_raw(pipe)
            return True
        except Exception:
            return False

    def _presence_worker(self):
        pipe = None
        last_dispatch_time = 0.0
        backoff_delay = _INITIAL_BACKOFF

        while not self._shutdown_event.is_set():
            if not self._enabled:
                break

            if pipe is None:
                pipe = self._connect()
                if pipe is None:
                    self._shutdown_event.wait(backoff_delay)
                    backoff_delay = min(backoff_delay * 2.0, _MAX_BACKOFF)
                    continue
                backoff_delay = _INITIAL_BACKOFF
                last_dispatch_time = 0.0

            with self._lock:
                is_dirty = self._presence_state["dirty"]
                state_copy = self._presence_state.copy() if is_dirty else None

            current_time = time.time()
            time_since_last = current_time - last_dispatch_time

            # Force periodic heartbeat rewrite even without state changes.
            # This prevents Discord's native process hook (Roblox game detection)
            # from bumping our custom presence off the gateway activity stack.
            should_dispatch = is_dirty and time_since_last >= _COOLDOWN_WINDOW
            should_heartbeat = (not is_dirty) and time_since_last >= _HEARTBEAT_INTERVAL

            if should_dispatch or should_heartbeat:
                if state_copy is None:
                    with self._lock:
                        state_copy = self._presence_state.copy()

                activity = self._build_activity(state_copy)
                nonce = str(uuid.uuid4())
                ok = self._dispatch(pipe, activity, nonce)

                if ok:
                    last_dispatch_time = current_time
                    if should_dispatch:
                        with self._lock:
                            self._presence_state["dirty"] = False
                else:
                    try:
                        pipe.close()
                    except Exception:
                        pass
                    pipe = None
                    last_dispatch_time = 0.0
                    self._shutdown_event.wait(backoff_delay)
                    backoff_delay = min(backoff_delay * 2.0, _MAX_BACKOFF)
                    continue

            self._shutdown_event.wait(1.0)

        if pipe:
            try:
                pipe.close()
            except Exception:
                pass

    def _send_raw(self, pipe, op: int, payload: dict):
        data = json.dumps(payload).encode('utf-8')
        pipe.write(struct.pack('<II', op, len(data)) + data)
        pipe.flush()

    def _read_raw(self, pipe):
        try:
            header = pipe.read(8)
            if len(header) < 8:
                return None, None
            op, length = struct.unpack('<II', header)
            return op, json.loads(pipe.read(length).decode('utf-8'))
        except Exception:
            return None, None
