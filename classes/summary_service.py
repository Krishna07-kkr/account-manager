import asyncio
import aiohttp
import threading
import time
import copy

class AccountSummaryService:
    def __init__(self, ui):
        self.ui = ui
        self.lock = threading.Lock()
        self.accounts_state = {}
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.thread.start()
        self.sync_saved_accounts()

    def _run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def sync_saved_accounts(self):
        with self.lock:
            for username in list(self.ui.manager.accounts.keys()):
                acc_info = self.ui.manager.accounts[username]
                user_id = acc_info.get("user_id")
                if username not in self.accounts_state:
                    self.accounts_state[username] = {
                        "user_id": user_id,
                        "start_time": None,
                        "uptime": "00:00:00",
                        "pfp_url": None
                    }
                elif user_id and not self.accounts_state[username]["user_id"]:
                    self.accounts_state[username]["user_id"] = user_id

                if user_id and not self.accounts_state[username]["pfp_url"]:
                    asyncio.run_coroutine_threadsafe(
                        self.fetch_pfp(username, user_id), self.loop
                    )

    async def fetch_pfp(self, username, user_id):
        if not user_id:
            return
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png&isCircular=false"
                async with session.get(url) as response:
                    if response.status == 200:
                        res = await response.json()
                        data = res.get("data", [])
                        if data:
                            img_url = data[0].get("imageUrl")
                            if img_url:
                                with self.lock:
                                    if username in self.accounts_state:
                                        self.accounts_state[username]["pfp_url"] = img_url
        except:
            pass

    def sync_active_instances(self, active_instances):
        active_usernames = set()
        with self.lock:
            for username in list(self.ui.manager.accounts.keys()):
                acc_info = self.ui.manager.accounts[username]
                user_id = acc_info.get("user_id")
                if username not in self.accounts_state:
                    self.accounts_state[username] = {
                        "user_id": user_id,
                        "start_time": None,
                        "uptime": "00:00:00",
                        "pfp_url": None
                    }
                elif user_id and not self.accounts_state[username]["user_id"]:
                    self.accounts_state[username]["user_id"] = user_id
                    if not self.accounts_state[username]["pfp_url"]:
                        asyncio.run_coroutine_threadsafe(
                            self.fetch_pfp(username, user_id), self.loop
                        )

            for entry in active_instances:
                username = entry.get("username")
                user_id = entry.get("user_id")
                create_time = entry.get("create_time")
                if username:
                    active_usernames.add(username)
                    if username not in self.accounts_state:
                        self.accounts_state[username] = {
                            "user_id": user_id,
                            "start_time": create_time or time.time(),
                            "uptime": "00:00:00",
                            "pfp_url": None
                        }
                    else:
                        state = self.accounts_state[username]
                        if not state["user_id"] and user_id:
                            state["user_id"] = user_id
                        if state["start_time"] is None:
                            state["start_time"] = create_time or time.time()
                    
                    state = self.accounts_state[username]
                    if state["user_id"] and not state["pfp_url"]:
                        asyncio.run_coroutine_threadsafe(
                            self.fetch_pfp(username, state["user_id"]), self.loop
                        )

            for username, state in list(self.accounts_state.items()):
                if username not in active_usernames:
                    state["start_time"] = None
                    state["uptime"] = "00:00:00"
                else:
                    st = state["start_time"]
                    if st:
                        elapsed = int(time.time() - st)
                        h = elapsed // 3600
                        m = (elapsed % 3600) // 60
                        s = elapsed % 60
                        state["uptime"] = f"{h:02d}:{m:02d}:{s:02d}"

    def get_all_summaries(self):
        with self.lock:
            for username, state in self.accounts_state.items():
                st = state["start_time"]
                if st:
                    elapsed = int(time.time() - st)
                    h = elapsed // 3600
                    m = (elapsed % 3600) // 60
                    s = elapsed % 60
                    state["uptime"] = f"{h:02d}:{m:02d}:{s:02d}"
            return copy.deepcopy(self.accounts_state)
