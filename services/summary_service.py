import asyncio
import aiohttp
import threading
import time
import copy

class AccountSummaryService:
    def __init__(self, manager):
        self.manager = manager
        self.lock = threading.Lock()
        self.accounts_state = {}
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.thread.start()
        self.sync_saved_accounts()

    def _run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    @staticmethod
    def _make_state(user_id=None):
        return {"user_id": user_id, "start_time": None, "uptime": "00:00:00", "pfp_url": None}

    @staticmethod
    def _calc_uptime(start_time):
        elapsed = int(time.time() - start_time)
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _fetch_pfp_if_needed(self, username, state):
        if state["user_id"] and not state["pfp_url"]:
            asyncio.run_coroutine_threadsafe(
                self.fetch_pfp(username, state["user_id"]), self.loop
            )

    def sync_saved_accounts(self):
        with self.lock:
            for username, acc_info in self.manager.accounts.items():
                user_id = acc_info.get("user_id")
                if username not in self.accounts_state:
                    self.accounts_state[username] = self._make_state(user_id)
                    self._fetch_pfp_if_needed(username, self.accounts_state[username])
                elif user_id and not self.accounts_state[username]["user_id"]:
                    self.accounts_state[username]["user_id"] = user_id
                    self._fetch_pfp_if_needed(username, self.accounts_state[username])

    async def fetch_pfp(self, username, user_id):
        if not user_id:
            return
        try:
            url = (
                f"https://thumbnails.roblox.com/v1/users/avatar-headshot"
                f"?userIds={user_id}&size=150x150&format=Png&isCircular=false"
            )
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = (await response.json()).get("data", [])
                        if data:
                            img_url = data[0].get("imageUrl")
                            if img_url:
                                with self.lock:
                                    if username in self.accounts_state:
                                        self.accounts_state[username]["pfp_url"] = img_url
        except Exception:
            pass

    def sync_active_instances(self, active_instances):
        active_usernames = set()
        with self.lock:
            for username, acc_info in self.manager.accounts.items():
                user_id = acc_info.get("user_id")
                if username not in self.accounts_state:
                    self.accounts_state[username] = self._make_state(user_id)
                elif user_id and not self.accounts_state[username]["user_id"]:
                    self.accounts_state[username]["user_id"] = user_id
                self._fetch_pfp_if_needed(username, self.accounts_state[username])

            for entry in active_instances:
                username = entry.get("username")
                if not username:
                    continue
                user_id = entry.get("user_id")
                create_time = entry.get("create_time")
                active_usernames.add(username)
                if username not in self.accounts_state:
                    self.accounts_state[username] = self._make_state(user_id)
                    self.accounts_state[username]["start_time"] = create_time or time.time()
                else:
                    state = self.accounts_state[username]
                    if not state["user_id"] and user_id:
                        state["user_id"] = user_id
                    if state["start_time"] is None:
                        state["start_time"] = create_time or time.time()
                self._fetch_pfp_if_needed(username, self.accounts_state[username])

            for username, state in self.accounts_state.items():
                if username not in active_usernames:
                    state["start_time"] = None
                    state["uptime"] = "00:00:00"
                elif state["start_time"]:
                    state["uptime"] = self._calc_uptime(state["start_time"])

    def get_all_summaries(self):
        with self.lock:
            for state in self.accounts_state.values():
                if state["start_time"]:
                    state["uptime"] = self._calc_uptime(state["start_time"])
            return copy.deepcopy(self.accounts_state)
