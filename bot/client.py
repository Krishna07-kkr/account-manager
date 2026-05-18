import asyncio
import json
import threading
import time
import subprocess
import requests
import websockets
import sys
from .commands import get_commands_definition, handle_interaction
from .commands.deployment import send_paginated_accounts, send_paginated_list_join

class DiscordLogRedirector:
    def __init__(self, bot, original_stream, prefix_tag=""):
        self.bot = bot
        self.original_stream = original_stream
        self.prefix_tag = prefix_tag
        self.in_write = False

    def write(self, message):
        self.original_stream.write(message)
        stripped = message.strip()
        if not self.in_write and stripped and self.bot.log_mirror_enabled:
            if any(stripped.startswith(prefix) for prefix in ["[SUCCESS]", "[ERROR]", "[WARNING]", "[INFO]"]):
                self.in_write = True
                try:
                    color = 0x2ECC71 if "[SUCCESS]" in stripped else (0xE74C3C if "[ERROR]" in stripped else (0xF1C40F if "[WARNING]" in stripped else 0x3498DB))
                    self.bot._send_activity_log(f"{self.prefix_tag} RAM System Log", stripped, color)
                except:
                    pass
                finally:
                    self.in_write = False

    def flush(self):
        self.original_stream.flush()

class DiscordBot:
    def __init__(self, ui_app):
        self.ui = ui_app
        self.thread = None
        self.stop_event = None
        self.orig_stdout = None
        self.orig_stderr = None
        self.log_mirror_enabled = True

    def start(self):
        self.stop()
        if not self.ui.settings.get("discord_bot_enabled", False):
            return
        token = self.ui.settings.get("discord_bot_token", "").strip()
        if not token:
            print("[WARNING] Discord Bot token is missing or empty")
            return
        self.orig_stdout = sys.stdout
        self.orig_stderr = sys.stderr
        sys.stdout = DiscordLogRedirector(self, sys.stdout, "[STDOUT]")
        sys.stderr = DiscordLogRedirector(self, sys.stderr, "[STDERR]")
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._thread_main,
            args=(token, self.stop_event),
            name="DiscordBotServer",
            daemon=True
        )
        self.thread.start()

    def stop(self):
        if self.stop_event:
            self.stop_event.set()
        if self.orig_stdout:
            sys.stdout = self.orig_stdout
        if self.orig_stderr:
            sys.stderr = self.orig_stderr
        self.thread = None

    def _send_callback(self, url, headers, payload):
        def do_post():
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=5)
                if res.status_code not in (200, 201, 204):
                    print(f"[ERROR] Discord API callback rejected ({res.status_code}): {res.text}")
            except Exception as e:
                print(f"[ERROR] Discord API callback connection failed: {e}")
        threading.Thread(target=do_post, daemon=True).start()

    def _send_followup(self, app_id, token, payload):
        def do_post():
            try:
                url = f"https://discord.com/api/v10/webhooks/{app_id}/{token}"
                res = requests.post(url, json=payload, timeout=5)
                if res.status_code not in (200, 201, 204):
                    print(f"[ERROR] Discord API followup rejected ({res.status_code}): {res.text}")
            except Exception as e:
                print(f"[ERROR] Discord API followup connection failed: {e}")
        threading.Thread(target=do_post, daemon=True).start()

    def _send_webhook_embed(self, title, description, color, fields=None):
        webhook_url = self.ui.settings.get("discord_webhook", {}).get("url", "").strip()
        if not webhook_url:
            return False
        try:
            embed = {
                "title": title,
                "description": description,
                "color": color,
                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            }
            if fields:
                embed["fields"] = fields
            payload = {"embeds": [embed]}
            def do_post():
                try:
                    requests.post(webhook_url, json=payload, timeout=5)
                except:
                    pass
            threading.Thread(target=do_post, daemon=True).start()
            return True
        except:
            return False

    def _thread_main(self, token, stop_event):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main_loop(token, stop_event))
        except:
            pass
        finally:
            try:
                loop.close()
            except:
                pass

    async def _main_loop(self, token, stop_event):
        gateway_url = "wss://gateway.discord.gg/?v=10&encoding=json"
        application_id = None
        while not stop_event.is_set():
            try:
                async with websockets.connect(gateway_url) as ws:
                    hello_packet = await ws.recv()
                    hello_data = json.loads(hello_packet)
                    heartbeat_interval = hello_data["d"]["heartbeat_interval"] / 1000.0
                    last_sequence = None
                    async def heartbeat_loop():
                        while not stop_event.is_set():
                            try:
                                await asyncio.sleep(heartbeat_interval)
                                await ws.send(json.dumps({"op": 1, "d": last_sequence}))
                            except:
                                break
                    asyncio.create_task(heartbeat_loop())
                    identify_payload = {
                        "op": 2,
                        "d": {
                            "token": token,
                            "intents": 33280,
                            "properties": {
                                "os": "windows",
                                "browser": "custom",
                                "device": "custom"
                            }
                        }
                    }
                    await ws.send(json.dumps(identify_payload))
                    while not stop_event.is_set():
                        try:
                            msg_raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            msg = json.loads(msg_raw)
                            if "s" in msg and msg["s"] is not None:
                                last_sequence = msg["s"]
                            op = msg.get("op")
                            t = msg.get("t")
                            d = msg.get("d")
                            if op == 0:
                                if t == "READY":
                                    application_id = d["application"]["id"]
                                    await self._register_slash_commands(application_id, token)
                                elif t == "GUILD_CREATE":
                                    if application_id:
                                        await self._sync_guild_slash_commands(application_id, token, d.get("id"))
                                elif t == "MESSAGE_CREATE":
                                    await self._handle_message(d, token)
                                elif t == "INTERACTION_CREATE":
                                    await self._handle_interaction(d, token, application_id)
                        except asyncio.TimeoutError:
                            continue
                        except:
                            break
            except:
                await asyncio.sleep(5)

    def _send_activity_log(self, title, description, color):
        webhook_url = self.ui.settings.get("discord_webhook", {}).get("url", "").strip()
        if not webhook_url:
            return
        try:
            payload = {
                "embeds": [
                    {
                        "title": title,
                        "description": description,
                        "color": color,
                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                    }
                ]
            }
            requests.post(webhook_url, json=payload, timeout=5)
        except:
            pass

    async def _register_slash_commands(self, application_id, token):
        if "--sync" not in sys.argv:
            print("[INFO] Discord slash commands loaded locally (use --sync on launch to register new commands)")
            return
        try:
            url = f"https://discord.com/api/v10/applications/{application_id}/commands"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            commands = get_commands_definition()
            res = requests.put(url, headers=headers, json=commands, timeout=5)
            if res.status_code == 429:
                try:
                    retry_after = res.json().get("retry_after", 5.0)
                except:
                    retry_after = 5.0
                print(f"[WARNING] Discord command sync rate-limited. Retry after {retry_after}s.")
                return
            print(f"[INFO] Global command registration status: {res.status_code}")
            if res.status_code not in (200, 201):
                print(f"[ERROR] Global registry rejected: {res.text}")
        except Exception as e:
            print(f"[ERROR] Global registry exception: {e}")

    async def _sync_guild_slash_commands(self, application_id, token, guild_id):
        if not guild_id or "--sync" not in sys.argv:
            return
        try:
            url = f"https://discord.com/api/v10/applications/{application_id}/guilds/{guild_id}/commands"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            res = requests.put(url, headers=headers, json=[], timeout=5)
            if res.status_code == 429:
                try:
                    retry_after = res.json().get("retry_after", 5.0)
                except:
                    retry_after = 5.0
                print(f"[WARNING] Discord command guild sync rate-limited. Retry after {retry_after}s.")
                return
        except:
            pass

    async def _handle_message(self, d, token):
        try:
            author_id = d.get("author", {}).get("id")
            content = str(d.get("content", "")).strip()
            channel_id = d.get("channel_id")
            if not channel_id:
                return
            authorized_id = self.ui.settings.get("discord_bot_authorized_id", "").strip()
            if authorized_id and author_id != authorized_id:
                return
            if not content.startswith("!"):
                return
            parts = content.split()
            if not parts:
                return
            command = parts[0].lower()
            def send_reply(text):
                try:
                    headers = {
                        "Authorization": f"Bot {token}",
                        "Content-Type": "application/json"
                    }
                    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                    requests.post(url, headers=headers, json={"content": text}, timeout=5)
                except:
                    pass
            if command == "!launch":
                if len(parts) < 3:
                    send_reply("Usage: `!launch <username> <place_id>`")
                    return
                account_name = parts[1]
                place_id = parts[2]
                if account_name not in self.ui.manager.accounts:
                    send_reply(f"Error: Account not found: `{account_name}`")
                    return
                send_reply(f"[INFO] Launching Roblox for {account_name}...")
                self._send_activity_log(
                    "[LAUNCH SEQUENCE]",
                    f"Programmatic launcher initiated from chat command for account **{account_name}** into Place ID `{place_id}`.",
                    0x95A5A6
                )
                launcher_pref, custom_launcher_path = self.ui._get_roblox_launcher_config()
                def run_launch():
                    try:
                        self.ui.manager.launch_roblox(
                            username=account_name,
                            game_id=place_id,
                            launcher_preference=launcher_pref,
                            custom_launcher_path=custom_launcher_path
                        )
                        self._send_activity_log(
                            "[LAUNCH SUCCESS]",
                            f"Roblox account **{account_name}** launched successfully into Place ID `{place_id}`.",
                            0x2ECC71
                        )
                    except Exception as le:
                        self._send_activity_log(
                            "[LAUNCH ERROR]",
                            f"Launch sequence failed for account **{account_name}**: {le}",
                            0xE74C3C
                        )
                threading.Thread(target=run_launch, daemon=True).start()
            elif command == "!kill":
                if len(parts) < 2:
                    send_reply("Usage: `!kill <username>`")
                    return
                account_name = parts[1]
                if account_name.lower() in ("all", "ram"):
                    active_sessions = list(self.ui.instances_data)
                    count = 0
                    for entry in active_sessions:
                        pid = entry.get("pid")
                        if pid:
                            try:
                                subprocess.run(['taskkill', '/F', '/PID', str(pid)], creationflags=subprocess.CREATE_NO_WINDOW)
                                count += 1
                            except:
                                pass
                    send_reply(f"[SUCCESS] Terminated all {count} running Roblox client player tabs.")
                    return
                resolved_pid = None
                for entry in list(self.ui.instances_data):
                    if entry.get("username") == account_name:
                        resolved_pid = entry.get("pid")
                        break
                if resolved_pid:
                    try:
                        import psutil
                        if psutil.pid_exists(resolved_pid):
                            subprocess.run(['taskkill', '/F', '/PID', str(resolved_pid)], creationflags=subprocess.CREATE_NO_WINDOW)
                            try:
                                proc = psutil.Process(resolved_pid)
                                proc.terminate()
                            except:
                                pass
                            send_reply(f"[SUCCESS] Process for {account_name} (PID: {resolved_pid}) terminated.")
                        else:
                            send_reply(f"Session for {account_name} was already offline.")
                    except Exception as e:
                        send_reply(f"Failed to terminate process for {account_name}: {e}")
                else:
                    send_reply(f"Session for {account_name} was already offline.")
            elif command == "!status":
                active_sessions = list(self.ui.instances_data)
                if not active_sessions:
                    send_reply("No active Roblox sessions running.")
                    return
                lines = ["**Active Roblox Sessions:**"]
                for entry in active_sessions:
                    create_time = entry.get("create_time", 0.0)
                    uptime_str = "00:00:00"
                    if create_time:
                        try:
                            elapsed = int(time.time() - create_time)
                            h = elapsed // 3600
                            m = (elapsed % 3600) // 60
                            s = elapsed % 60
                            uptime_str = f"{h:02d}:{m:02d}:{s:02d}"
                        except:
                            pass
                    lines.append(
                        f"• **{entry.get('username', 'Unknown')}** (PID: `{entry.get('pid')}`) | Game ID: `{entry.get('place_id', 'Unknown')}` | Uptime: `{uptime_str}`"
                    )
                send_reply("\n".join(lines))
            elif command == "!help":
                help_text = (
                    "**Roblox Account Manager Chat Commands Help Directory:**\n\n"
                    "• **!launch <username> <place_id>**\n"
                    "  *Use Case*: Programmatically launches a specific Roblox account into the specified Place ID.\n\n"
                    "• **!kill <username | all>**\n"
                    "  *Use Case*: Force-closes Roblox players. Type username to terminate just that player, or 'all' to close all Roblox client player tabs.\n\n"
                    "• **!status**\n"
                    "  *Use Case*: Returns a list of all active game player sessions, including PIDs, running Place IDs, and precise uptimes.\n\n"
                    "• **!help**\n"
                    "  *Use Case*: Shows this beautiful commands cheat-sheet and usage directory.\n\n"
                    "*(Note: You can also use Slash Commands like `/admin_abuse`, `/free_memory`, `/accounts`, `/join`, `/kill`, `/antiafk`, `/settings`, `/addaccount`, `/list`, `/status`, and `/help` directly in Discord!)*"
                )
                send_reply(help_text)
        except:
            pass

    async def _handle_interaction(self, d, token, application_id):
        try:
            author_id = d.get("member", {}).get("user", {}).get("id") or d.get("user", {}).get("id")
            authorized_id = self.ui.settings.get("discord_bot_authorized_id", "").strip()
            interaction_type = d.get("type")
            interaction_id = d.get("id")
            interaction_token = d.get("token")
            resolved_app_id = d.get("application_id") or application_id
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            if authorized_id and author_id != authorized_id:
                url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                self._send_callback(url, headers, {
                    "type": 4,
                    "data": {
                        "content": f"[ERROR] You are not authorized to interact with this application.\n\nAuthorized ID configured in Settings: `{authorized_id}`\nYour Discord User ID: `{author_id}`\n\nPlease copy your Discord User ID and paste it into the Authorized ID field in your Roblox Account Manager Settings panel to enable access!",
                        "flags": 64
                    }
                })
                return
            if interaction_type == 5:
                custom_id = d.get("data", {}).get("custom_id", "")
                if custom_id.startswith("list_join_submit_modal:"):
                    selected_accounts_str = custom_id.split(":")[1]
                    selected_accounts = selected_accounts_str.split(",")
                    place_id = ""
                    components = d.get("data", {}).get("components", [])
                    for row in components:
                        for comp in row.get("components", []):
                            if comp.get("custom_id") == "place_input":
                                place_id = comp.get("value", "").strip()
                                break
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    hook_ok = self._send_webhook_embed(
                        "Launch Sequence Initiated",
                        f"Programmatic batch launch sequence started for **{len(selected_accounts)}** accounts into Place ID `{place_id}`.",
                        0x95A5A6
                    )
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "content": f"[INFO] Programmatic launch sequence started for {len(selected_accounts)} accounts into Place ID `{place_id}`! Details sent to Webhook." if hook_ok else f"[INFO] Programmatic launch sequence started for {len(selected_accounts)} accounts into Place ID `{place_id}`..."
                        }
                    })
                    launcher_pref, custom_launcher_path = self.ui._get_roblox_launcher_config()
                    for idx, account_name in enumerate(selected_accounts):
                        if account_name in self.ui.manager.accounts:
                            try:
                                self.ui.manager.launch_roblox(
                                    username=account_name,
                                    game_id=place_id,
                                    launcher_preference=launcher_pref,
                                    custom_launcher_path=custom_launcher_path
                                )
                                self._send_webhook_embed(
                                    "Launch Successful",
                                    f"Staggered launch sequence successful for account **{account_name}**.",
                                    0x2ECC71
                                )
                            except Exception as e:
                                self._send_webhook_embed(
                                    "Launch Failure",
                                    f"Staggered launch sequence failed for account **{account_name}**: {e}",
                                    0xE74C3C
                                )
                        await asyncio.sleep(0.01)
                    hook_end = self._send_webhook_embed(
                        "Launch Sequence Completed",
                        f"Finished staggered launch process for all **{len(selected_accounts)}** accounts into Place ID `{place_id}`.",
                        0x2ECC71
                    )
                    self._send_followup(resolved_app_id, interaction_token, {
                        "content": f"[SUCCESS] Finished launching {len(selected_accounts)} accounts into Place ID `{place_id}`! Details sent to Webhook." if hook_end else f"[SUCCESS] Finished launching {len(selected_accounts)} accounts into Place ID `{place_id}`!"
                    })
                return

            if interaction_type == 2:
                command_name = d.get("data", {}).get("name")
                await handle_interaction(self, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token)
                return

            if interaction_type == 3:
                custom_id = d.get("data", {}).get("custom_id", "")
                if custom_id.startswith("launch_select:"):
                    place_id = custom_id.split(":")[1]
                    selected_accounts = d.get("data", {}).get("values", [])
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    hook_ok = self._send_webhook_embed(
                        "Launch Sequence Initiated",
                        f"Programmatic batch launch sequence started for **{len(selected_accounts)}** accounts into Place ID `{place_id}`.",
                        0x95A5A6
                    )
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "content": f"[INFO] Programmatic launch sequence started for {len(selected_accounts)} accounts into Place ID `{place_id}`! Detailed status dispatched to Webhook." if hook_ok else f"[INFO] Programmatic launch sequence started for {len(selected_accounts)} accounts into Place ID `{place_id}`...",
                            "components": []
                        }
                    })
                    launcher_pref, custom_launcher_path = self.ui._get_roblox_launcher_config()
                    for idx, account_name in enumerate(selected_accounts):
                        if account_name in self.ui.manager.accounts:
                            try:
                                self.ui.manager.launch_roblox(
                                    username=account_name,
                                    game_id=place_id,
                                    launcher_preference=launcher_pref,
                                    custom_launcher_path=custom_launcher_path
                                )
                                self._send_webhook_embed(
                                    "Launch Successful",
                                    f"Staggered launch sequence successful for account **{account_name}**.",
                                    0x2ECC71
                                )
                            except Exception as e:
                                self._send_webhook_embed(
                                    "Launch Failure",
                                    f"Staggered launch sequence failed for account **{account_name}**: {e}",
                                    0xE74C3C
                                )
                        await asyncio.sleep(0.01)
                    hook_end = self._send_webhook_embed(
                        "Launch Sequence Completed",
                        f"Finished staggered launch process for all **{len(selected_accounts)}** accounts into Place ID `{place_id}`.",
                        0x2ECC71
                    )
                    self._send_followup(resolved_app_id, interaction_token, {
                        "content": f"[SUCCESS] Finished launching {len(selected_accounts)} accounts into Place ID `{place_id}`! Details sent to Webhook." if hook_end else f"[SUCCESS] Finished launching {len(selected_accounts)} accounts into Place ID `{place_id}`!"
                    })
                elif custom_id.startswith("list_join_select:"):
                    selected_accounts = d.get("data", {}).get("values", [])
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    selected_str = ",".join(selected_accounts)
                    components = [
                        {
                            "type": 1,
                            "components": [
                                {
                                    "type": 2,
                                    "style": 1,
                                    "label": "Next (Enter Place ID)",
                                    "custom_id": f"list_join_next_btn:{selected_str}"
                                }
                            ]
                        }
                    ]
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "content": f"Selected **{len(selected_accounts)}** accounts. Click the Next button below to set Roblox Place ID and launch them all:",
                            "components": components
                        }
                    })
                elif custom_id.startswith("list_join_next_btn:"):
                    selected_str = custom_id.split(":")[1]
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    modal_payload = {
                        "type": 9,
                        "data": {
                            "title": "Join Selected Accounts",
                            "custom_id": f"list_join_submit_modal:{selected_str}",
                            "components": [
                                {
                                    "type": 1,
                                    "components": [
                                        {
                                            "type": 4,
                                            "custom_id": "place_input",
                                            "style": 1,
                                            "label": "Enter Roblox Place ID",
                                            "min_length": 1,
                                            "max_length": 30,
                                            "placeholder": "e.g. 185655138",
                                            "required": True
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                    self._send_callback(url, headers, modal_payload)
                elif custom_id.startswith("bot_page:"):
                    parts = custom_id.split(":")
                    action = parts[1]
                    place_id = parts[2]
                    current_page = int(parts[3])
                    new_page = current_page + 1 if action == "next" else current_page - 1
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    all_accounts = list(self.ui.manager.accounts.keys())
                    select_options = [{"label": acc[:100], "value": acc[:100]} for acc in all_accounts[new_page*25 : (new_page+1)*25]]
                    components = [
                        {
                            "type": 1,
                            "components": [
                                {
                                    "type": 3,
                                    "custom_id": f"launch_select:{place_id}",
                                    "placeholder": "Select accounts...",
                                    "min_values": 1,
                                    "max_values": min(25, len(select_options)),
                                    "options": select_options
                                }
                            ]
                        }
                    ]
                    if len(all_accounts) > 25:
                        components.append({
                            "type": 1,
                            "components": [
                                {
                                    "type": 2,
                                    "style": 2,
                                    "label": "◀ Prev",
                                    "custom_id": f"bot_page:prev:{place_id}:{new_page}",
                                    "disabled": new_page == 0
                                },
                                {
                                    "type": 2,
                                    "style": 2,
                                    "label": "Next ▶",
                                    "custom_id": f"bot_page:next:{place_id}:{new_page}",
                                    "disabled": (new_page+1)*25 >= len(all_accounts)
                                }
                            ]
                        })
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "content": f"Select the Roblox accounts you want to launch into Place ID `{place_id}` (Page {new_page + 1}):",
                            "components": components
                        }
                    })
                elif custom_id.startswith("list_join_page:"):
                    parts = custom_id.split(":")
                    action = parts[1]
                    current_page = int(parts[2])
                    new_page = current_page + 1 if action == "next" else current_page - 1
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    all_accounts = list(self.ui.manager.accounts.keys())
                    select_options = [{"label": acc[:100], "value": acc[:100]} for acc in all_accounts[new_page*25 : (new_page+1)*25]]
                    components = [
                        {
                            "type": 1,
                            "components": [
                                {
                                    "type": 3,
                                    "custom_id": "list_join_select:",
                                    "placeholder": "Select accounts...",
                                    "min_values": 1,
                                    "max_values": min(25, len(select_options)),
                                    "options": select_options
                                }
                            ]
                        }
                    ]
                    if len(all_accounts) > 25:
                        components.append({
                            "type": 1,
                            "components": [
                                {
                                    "type": 2,
                                    "style": 2,
                                    "label": "◀ Prev",
                                    "custom_id": f"list_join_page:prev:{new_page}",
                                    "disabled": new_page == 0
                                },
                                {
                                    "type": 2,
                                    "style": 2,
                                    "label": "Next ▶",
                                    "custom_id": f"list_join_page:next:{new_page}",
                                    "disabled": (new_page+1)*25 >= len(all_accounts)
                                }
                            ]
                        })
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "content": f"Select the Roblox accounts you want to launch (Page {new_page + 1}):",
                            "components": components
                        }
                    })
        except Exception as err:
            print(f"[ERROR] Discord Bot interaction handling failed: {err}")
