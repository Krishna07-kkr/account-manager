import asyncio
import json
import threading
import time
import subprocess
import requests
import websockets
import sys

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
        
        def register_immediately():
            try:
                headers = {
                    "Authorization": f"Bot {token}",
                    "Content-Type": "application/json"
                }
                res = requests.get("https://discord.com/api/v10/oauth2/applications/@me", headers=headers, timeout=5)
                if res.status_code == 200:
                    app_id = res.json()["id"]
                    commands = self._get_commands_definition()
                    requests.put(f"https://discord.com/api/v10/applications/{app_id}/commands", headers=headers, json=commands, timeout=5)
                    res_guilds = requests.get("https://discord.com/api/v10/users/@me/guilds", headers=headers, timeout=5)
                    if res_guilds.status_code == 200:
                        for guild in res_guilds.json():
                            guild_id = guild["id"]
                            requests.put(f"https://discord.com/api/v10/applications/{app_id}/guilds/{guild_id}/commands", headers=headers, json=commands, timeout=5)
            except:
                pass
        
        threading.Thread(target=register_immediately, daemon=True).start()
        
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
        except Exception as exc:
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
        try:
            url = f"https://discord.com/api/v10/applications/{application_id}/commands"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            commands = self._get_commands_definition()
            res = requests.put(url, headers=headers, json=commands, timeout=5)
            print(f"[INFO] Global command registration status: {res.status_code}")
            if res.status_code not in (200, 201):
                print(f"[ERROR] Global registry rejected: {res.text}")
        except Exception as e:
            print(f"[ERROR] Global registry exception: {e}")

    async def _sync_guild_slash_commands(self, application_id, token, guild_id):
        if not guild_id:
            return
        try:
            url = f"https://discord.com/api/v10/applications/{application_id}/guilds/{guild_id}/commands"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            commands = self._get_commands_definition()
            requests.put(url, headers=headers, json=commands, timeout=5)
        except:
            pass

    def _get_commands_definition(self):
        return [
            {
                "name": "admin_abuse",
                "description": "Clean reset, update framerate, and sequential launch all accounts",
                "options": [
                    {
                        "type": 4,
                        "name": "fps_cap",
                        "description": "Target frame rate cap for the session",
                        "required": True
                    },
                    {
                        "type": 3,
                        "name": "place_id",
                        "description": "Target Roblox experience Place ID",
                        "required": True
                    },
                    {
                        "type": 4,
                        "name": "launch_delay",
                        "description": "Interval delay in seconds between launches",
                        "required": True
                    }
                ]
            },
            {
                "name": "free_memory",
                "description": "Flush idle pages out of physical RAM for all active game clients"
            },
            {
                "name": "accounts",
                "description": "Select accounts to launch Roblox",
                "options": [
                    {
                        "type": 3,
                        "name": "place_id",
                        "description": "The Roblox Place ID to join",
                        "required": True
                    }
                ]
            },
            {
                "name": "list_join",
                "description": "Interactive list to select accounts, then enter place ID to launch"
            },
            {
                "name": "kill_all",
                "description": "Terminate all active Roblox player tab sessions instantly"
            },
            {
                "name": "activity_log",
                "description": "Enable or disable mirroring of application console logs to Discord",
                "options": [
                    {
                        "type": 3,
                        "name": "status",
                        "description": "Select 'enable' or 'disable'",
                        "required": True,
                        "choices": [
                            {"name": "Enable", "value": "enable"},
                            {"name": "Disable", "value": "disable"}
                        ]
                    }
                ]
            },
            {
                "name": "active_accounts",
                "description": "Show all currently active online Roblox accounts"
            },
            {
                "name": "join_all",
                "description": "Sequential-launch all available accounts into Roblox",
                "options": [
                    {
                        "type": 3,
                        "name": "place_id",
                        "description": "The Roblox Place ID to join",
                        "required": True
                    }
                ]
            },
            {
                "name": "validity_check",
                "description": "Check the authentication status and validity of all cookies"
            },
            {
                "name": "resource",
                "description": "Get current system RAM and CPU usage statistics"
            },
            {
                "name": "join",
                "description": "Launch accounts into Roblox game Place ID",
                "options": [
                    {
                        "type": 3,
                        "name": "target",
                        "description": "Specify 'all' to launch all accounts, or enter a specific Roblox username",
                        "required": True
                    },
                    {
                        "type": 3,
                        "name": "place_id",
                        "description": "The Roblox Place ID to join",
                        "required": True
                    }
                ]
            },
            {
                "name": "kill",
                "description": "Terminate Roblox session player tab",
                "options": [
                    {
                        "type": 3,
                        "name": "target",
                        "description": "Specify 'all' or 'ram' to terminate all sessions, or enter a Roblox username",
                        "required": True
                    }
                ]
            },
            {
                "name": "addaccount",
                "description": "Add a new Roblox account profile to RAM",
                "options": [
                    {
                        "type": 3,
                        "name": "method",
                        "description": "Select 'Cookie' or 'Credentials'",
                        "required": True,
                        "choices": [
                            {"name": "Cookie", "value": "Cookie"},
                            {"name": "Credentials", "value": "Credentials"}
                        ]
                    },
                    {
                        "type": 3,
                        "name": "cookie",
                        "description": "The Roblox .ROBLOSECURITY cookie (required for Cookie method)",
                        "required": False
                    },
                    {
                        "type": 3,
                        "name": "username",
                        "description": "The Roblox account username (required for Credentials method)",
                        "required": False
                    },
                    {
                        "type": 3,
                        "name": "password",
                        "description": "The Roblox account password (required for Credentials method)",
                        "required": False
                    }
                ]
            },
            {
                "name": "list",
                "description": "Get a checklist summary of all accounts stored inside RAM"
            },
            {
                "name": "antiafk",
                "description": "Enable or disable RAM's built-in Anti-AFK engine",
                "options": [
                    {
                        "type": 3,
                        "name": "status",
                        "description": "Select 'enable' or 'disable'",
                        "required": True,
                        "choices": [
                            {"name": "Enable", "value": "enable"},
                            {"name": "Disable", "value": "disable"}
                        ]
                    }
                ]
            },
            {
                "name": "settings",
                "description": "Configure Account Manager settings remotely",
                "options": [
                    {
                        "type": 3,
                        "name": "setting",
                        "description": "Select setting to modify",
                        "required": True,
                        "choices": [
                            {"name": "Anti-AFK Engine", "value": "anti_afk_enabled"},
                            {"name": "Discord Bot Enabled", "value": "discord_bot_enabled"},
                            {"name": "WebSocket Port", "value": "websocket_port"},
                            {"name": "Launch Delay", "value": "launch_delay"}
                        ]
                    },
                    {
                        "type": 3,
                        "name": "value",
                        "description": "The new value to set",
                        "required": True
                    }
                ]
            },
            {
                "name": "status",
                "description": "Get real-time performance snapshot of all active sessions"
            },
            {
                "name": "grab_place_id",
                "description": "Show all saved Roblox game Place IDs"
            },
            {
                "name": "help",
                "description": "Show available remote commands and usage details"
            },
            {
                "name": "summary",
                "description": "Displays detailed visual summary, tracking data, and dynamic uptimes for all accounts"
            }
        ]

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
                if command_name == "admin_abuse":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    self._send_callback(url, headers, {"type": 5})
                    options = {o["name"]: o["value"] for o in d["data"].get("options", [])}
                    fps_cap = int(options.get("fps_cap"))
                    place_id = str(options.get("place_id")).strip()
                    launch_delay = int(options.get("launch_delay"))
                    def run_admin_abuse():
                        try:
                            import psutil
                            terminated_count = 0
                            for proc in psutil.process_iter(['name']):
                                try:
                                    if proc.info['name'] and proc.info['name'].lower() in ('robloxplayerbeta.exe', 'robloxplayerlauncher.exe'):
                                        proc.terminate()
                                        terminated_count += 1
                                except:
                                    pass
                            import os
                            import json
                            local_appdata = os.getenv('LOCALAPPDATA')
                            if local_appdata:
                                versions_dir = os.path.join(local_appdata, 'Roblox', 'Versions')
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
                                                except:
                                                    pass
                                            settings["DFIntTaskSchedulerTargetFps"] = fps_cap
                                            try:
                                                with open(settings_file, 'w', encoding='utf-8') as f:
                                                    json.dump(settings, f, indent=2)
                                            except:
                                                pass
                            all_accounts = list(self.ui.manager.accounts.keys())
                            launcher_pref, custom_launcher_path = self.ui._get_roblox_launcher_config()
                            self._send_webhook_embed(
                                "Admin Abuse Execution Started",
                                f"Terminated {terminated_count} active Roblox clients. Target FPS cap set to **{fps_cap}**. Commencing sequential launch of **{len(all_accounts)}** accounts into Place ID `{place_id}` with **{launch_delay}s** delay.",
                                0x95A5A6
                            )
                            for idx, account_name in enumerate(all_accounts):
                                try:
                                    self.ui.manager.launch_roblox(
                                        username=account_name,
                                        game_id=place_id,
                                        launcher_preference=launcher_pref,
                                        custom_launcher_path=custom_launcher_path
                                    )
                                    self._send_webhook_embed(
                                        "Admin Abuse Launch Success",
                                        f"Account **{account_name}** successfully deployed.",
                                        0x2ECC71
                                    )
                                except Exception as le:
                                    self._send_webhook_embed(
                                        "Admin Abuse Launch Failure",
                                        f"Account **{account_name}** deployment failed: {le}",
                                        0xE74C3C
                                    )
                                if idx < len(all_accounts) - 1:
                                    time.sleep(launch_delay)
                            self._send_webhook_embed(
                                "Admin Abuse Execution Completed",
                                f"Sequential deployment of all **{len(all_accounts)}** accounts completed successfully.",
                                0x2ECC71
                            )
                            self._send_followup(resolved_app_id, interaction_token, {
                                "embeds": [
                                    {
                                        "title": "⚔️ Admin Abuse Execution Completed",
                                        "description": f"Sequential launch of **{len(all_accounts)}** accounts completed successfully under FPS Cap **{fps_cap}**.",
                                        "color": 0x2ECC71,
                                        "fields": [
                                            {"name": "🎮 Target Experience", "value": f"`{place_id}`", "inline": True},
                                            {"name": "⚡ Engine FPS Cap", "value": f"`{fps_cap} FPS`", "inline": True},
                                            {"name": "⏱️ Stagger Delay", "value": f"`{launch_delay} seconds`", "inline": True},
                                            {"name": "👥 Total Deployments", "value": f"**{len(all_accounts)}** accounts launched", "inline": False}
                                        ],
                                        "footer": {"text": "Roblox Account Manager | Admin Abuse Engine"},
                                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                    }
                                ]
                            })
                        except Exception as e:
                            self._send_followup(resolved_app_id, interaction_token, {
                                "embeds": [
                                    {
                                        "title": "❌ Admin Abuse Execution Failed",
                                        "description": f"An error occurred during the admin abuse sequential launch sequence:\n```python\n{e}\n```",
                                        "color": 0xE74C3C,
                                        "footer": {"text": "Roblox Account Manager | Admin Abuse Engine"},
                                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                    }
                                ]
                            })
                    threading.Thread(target=run_admin_abuse, daemon=True).start()
                elif command_name == "free_memory":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    self._send_callback(url, headers, {"type": 5})
                    def run_free_memory():
                        try:
                            import ctypes
                            import psutil
                            PROCESS_SET_QUOTA = 0x0100
                            PROCESS_QUERY_INFORMATION = 0x0400
                            kernel32 = ctypes.windll.kernel32
                            count = 0
                            failed_count = 0
                            for proc in psutil.process_iter(['pid', 'name']):
                                try:
                                    if proc.info['name'] and proc.info['name'].lower() == 'robloxplayerbeta.exe':
                                        pid = proc.info['pid']
                                        h_process = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION, False, pid)
                                        if h_process:
                                            try:
                                                result = kernel32.SetProcessWorkingSetSize(h_process, -1, -1)
                                                if result:
                                                    count += 1
                                                else:
                                                    failed_count += 1
                                            finally:
                                                kernel32.CloseHandle(h_process)
                                        else:
                                            failed_count += 1
                                except Exception:
                                    failed_count += 1
                            self._send_webhook_embed(
                                "RAM Optimization Completed",
                                f"Flushed memory pages for **{count}** active Roblox game client processes successfully. (Failed/Access Denied: **{failed_count}**)",
                                0x2ECC71
                            )
                            self._send_followup(resolved_app_id, interaction_token, {
                                "embeds": [
                                    {
                                        "title": "🧹 RAM Trim Optimization Completed",
                                        "description": "Successfully flushed idle memory pages out of physical RAM back into system standby/paging storage.",
                                        "color": 0x2ECC71,
                                        "fields": [
                                            {"name": "🟢 Optimized Clients", "value": f"**{count}** Roblox processes flushed", "inline": True},
                                            {"name": "🔴 Skipped/Access Denied", "value": f"**{failed_count}** clients skipped", "inline": True}
                                        ],
                                        "footer": {"text": "Roblox Account Manager | RAM Trim Engine"},
                                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                    }
                                ]
                            })
                        except Exception as e:
                            self._send_followup(resolved_app_id, interaction_token, {
                                "embeds": [
                                    {
                                        "title": "❌ RAM Trim Optimization Failed",
                                        "description": f"An error occurred during the RAM trim sequence:\n```python\n{e}\n```",
                                        "color": 0xE74C3C,
                                        "footer": {"text": "Roblox Account Manager | RAM Trim Engine"},
                                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                    }
                                ]
                            })
                    threading.Thread(target=run_free_memory, daemon=True).start()
                elif command_name == "accounts":
                    place_id = d["data"]["options"][0]["value"]
                    await self._send_paginated_accounts(interaction_id, interaction_token, place_id, 0, headers)
                elif command_name == "list_join":
                    await self._send_paginated_list_join(interaction_id, interaction_token, 0, headers)
                elif command_name == "kill_all":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "embeds": [{
                                "title": "⚠️ Terminating All Active Sessions",
                                "description": "Command received. Commencing force-termination of all active Roblox client players...",
                                "color": 0xF1C40F,
                                "footer": {"text": "Roblox Account Manager | Process Management"}
                            }]
                        }
                    })
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
                    self._send_webhook_embed(
                        "Roblox Instances Force-Closed",
                        f"Force-closed all active Roblox game client sessions (Closed tabs: **{count}**). Physical memory (RAM) has been flushed.",
                        0xE74C3C
                    )
                    self._send_followup(resolved_app_id, interaction_token, {
                        "embeds": [{
                            "title": "💥 Process Cleanup Completed",
                            "description": f"Successfully force-closed all active Roblox game client sessions and flushed physical memory (RAM).",
                            "color": 0xE74C3C,
                            "fields": [
                                {"name": "🔴 Terminated Player Clients", "value": f"**{count}** game clients terminated", "inline": True}
                            ],
                            "footer": {"text": "Roblox Account Manager | Process Management"},
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        }]
                    })
                elif command_name == "activity_log":
                    status = d["data"]["options"][0]["value"]
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    if status == "enable":
                        self.log_mirror_enabled = True
                        self._send_webhook_embed(
                            "Console Log Mirroring Enabled",
                            "Real-time console log mirroring to Discord has been enabled successfully.",
                            0x2ECC71
                        )
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "🔔 Console Log Mirroring Enabled",
                                    "description": "Real-time standard output (STDOUT) and error streams (STDERR) are now programmatically mirrored to your Discord bot server channel.",
                                    "color": 0x2ECC71,
                                    "footer": {"text": "Roblox Account Manager | Telemetry System"}
                                }]
                            }
                        })
                    else:
                        self.log_mirror_enabled = False
                        self._send_webhook_embed(
                            "Console Log Mirroring Disabled",
                            "Real-time console log mirroring to Discord has been disabled successfully.",
                            0xE74C3C
                        )
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "🔕 Console Log Mirroring Disabled",
                                    "description": "Real-time standard output and error stream mirroring to Discord has been successfully disabled.",
                                    "color": 0xE74C3C,
                                    "footer": {"text": "Roblox Account Manager | Telemetry System"}
                                }]
                            }
                        })
                elif command_name == "active_accounts":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    active_sessions = list(self.ui.instances_data)
                    if not active_sessions:
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "🟢 Live Active Online Roblox Accounts",
                                    "description": "No Roblox accounts are currently online or active inside client windows.",
                                    "color": 0x95A5A6,
                                    "footer": {"text": "Roblox Account Manager | Active Accounts"}
                                }],
                                "flags": 64
                            }
                        })
                        return
                    fields = []
                    for idx, entry in enumerate(active_sessions):
                        fields.append({
                            "name": f"{idx + 1}. {entry.get('username', 'Unknown')}",
                            "value": f"PID: `{entry.get('pid')}` | Place ID: `{entry.get('place_id', 'Unknown')}`",
                            "inline": True
                        })
                    self._send_webhook_embed(
                        "Live Active Online Roblox Accounts",
                        f"Directory of all Roblox accounts currently online and active inside client windows (Total: **{len(active_sessions)}**).",
                        0x1ABC9C,
                        fields=fields
                    )
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "embeds": [{
                                "title": "🟢 Live Active Online Roblox Accounts",
                                "description": f"Directory of all Roblox accounts currently online and active inside client windows (Total: **{len(active_sessions)}**).",
                                "color": 0x1ABC9C,
                                "fields": fields,
                                "footer": {"text": "Roblox Account Manager | Active Accounts"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        }
                    })
                elif command_name == "join_all":
                    place_id = d["data"]["options"][0]["value"].strip()
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    self._send_webhook_embed(
                        "Launch Sequence Initiated",
                        f"Programmatic batch launch sequence initiated for **ALL** accounts into Place ID `{place_id}`.",
                        0x95A5A6
                    )
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "embeds": [{
                                "title": "🚀 Staggered Join Sequence Initiated",
                                "description": f"Programmatic batch launch sequence started to launch **ALL** registered profiles into Experience ID `{place_id}`.",
                                "color": 0xF1C40F,
                                "footer": {"text": "Roblox Account Manager | Batch Launcher"}
                            }]
                        }
                    })
                    launcher_pref, custom_launcher_path = self.ui._get_roblox_launcher_config()
                    all_accounts = list(self.ui.manager.accounts.keys())
                    async def run_batch_join():
                        for account_name in all_accounts:
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
                        self._send_webhook_embed(
                            "Launch Sequence Completed",
                            f"Finished staggered launch process for all **{len(all_accounts)}** accounts into Place ID `{place_id}`.",
                            0x2ECC71
                        )
                        self._send_followup(resolved_app_id, interaction_token, {
                            "embeds": [{
                                "title": "🚀 Staggered Join Sequence Completed",
                                "description": f"Finished staggered launch process for all **{len(all_accounts)}** accounts into Place ID `{place_id}`.",
                                "color": 0x2ECC71,
                                "footer": {"text": "Roblox Account Manager | Batch Launcher"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        })
                    asyncio.create_task(run_batch_join())
                elif command_name == "validity_check":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "embeds": [{
                                "title": "🔍 Verifying Session Cookie Health",
                                "description": "Triggered background authentication session validity checks for all accounts. Please wait...",
                                "color": 0xF1C40F,
                                "footer": {"text": "Roblox Account Manager | Authentication Health"}
                            }]
                        }
                    })
                    def run_checks():
                        valid_list = []
                        invalid_list = []
                        all_accounts = list(self.ui.manager.accounts.keys())
                        for acc in all_accounts:
                            try:
                                if self.ui.manager.validate_account(acc):
                                    valid_list.append(acc)
                                else:
                                    invalid_list.append(acc)
                            except:
                                invalid_list.append(acc)
                        fields = []
                        if valid_list:
                            fields.append({
                                "name": f"✓ Valid Cookies ({len(valid_list)})",
                                "value": ", ".join(f"`{x}`" for x in valid_list),
                                "inline": False
                            })
                        if invalid_list:
                            fields.append({
                                "name": f"✗ Expired/Invalid Cookies ({len(invalid_list)})",
                                "value": ", ".join(f"`{x}`" for x in invalid_list),
                                "inline": False
                            })
                        if not valid_list and not invalid_list:
                            fields.append({
                                "name": "Status",
                                "value": "No registered account profiles found.",
                                "inline": False
                            })
                        color = 0x2ECC71 if not invalid_list else 0xE74C3C
                        self._send_webhook_embed(
                            "Roblox Account Session Validity Report",
                            "Background authentication verification completed for all registered accounts.",
                            color,
                            fields=fields
                        )
                        self._send_followup(resolved_app_id, interaction_token, {
                            "embeds": [{
                                "title": "🔍 Roblox Account Session Validity Report",
                                "description": "Background authentication verification completed for all registered accounts.",
                                "color": color,
                                "fields": fields,
                                "footer": {"text": "Roblox Account Manager | Authentication Health"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        })
                    threading.Thread(target=run_checks, daemon=True).start()
                elif command_name == "resource":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    cpu_percent = 0.0
                    total_gb, used_gb, free_gb, mem_percent = 0.0, 0.0, 0.0, 0.0
                    try:
                        import psutil
                        cpu_percent = psutil.cpu_percent(interval=None)
                        virtual_mem = psutil.virtual_memory()
                        total_gb = virtual_mem.total / (1024 ** 3)
                        used_gb = virtual_mem.used / (1024 ** 3)
                        free_gb = virtual_mem.available / (1024 ** 3)
                        mem_percent = virtual_mem.percent
                    except:
                        pass
                    fields = [
                        {"name": "CPU Load", "value": f"`{cpu_percent}%` usage", "inline": True},
                        {"name": "RAM Memory Percent", "value": f"`{mem_percent}%` loaded", "inline": True},
                        {"name": "RAM Capacity Usage", "value": f"`{used_gb:.2f} GB` used / `{free_gb:.2f} GB` free (`{total_gb:.2f} GB` total)", "inline": False}
                    ]
                    self._send_webhook_embed(
                        "System Resource Statistics Report",
                        "Real-time physical hardware metrics from the host computer.",
                        0x9B59B6,
                        fields=fields
                    )
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "embeds": [{
                                "title": "📊 System Resource Statistics Report",
                                "description": "Real-time physical hardware metrics from the host computer.",
                                "color": 0x9B59B6,
                                "fields": fields,
                                "footer": {"text": "Roblox Account Manager | System Monitor"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        }
                    })
                elif command_name == "join":
                    target = d["data"]["options"][0]["value"].strip()
                    place_id = d["data"]["options"][1]["value"].strip()
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    if target.lower() == "all":
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "🚀 Staggered Join Sequence Initiated",
                                    "description": f"Programmatic batch launch sequence started to launch **ALL** registered profiles into Experience ID `{place_id}`.",
                                    "color": 0xF1C40F,
                                    "footer": {"text": "Roblox Account Manager | Launcher"}
                                }]
                            }
                        })
                        self._send_webhook_embed(
                            "Launch Sequence Initiated",
                            f"Programmatic batch launch sequence initiated for **ALL** accounts into Place ID `{place_id}`.",
                            0x95A5A6
                        )
                        launcher_pref, custom_launcher_path = self.ui._get_roblox_launcher_config()
                        all_accounts = list(self.ui.manager.accounts.keys())
                        async def run_batch_join():
                            for account_name in all_accounts:
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
                            self._send_webhook_embed(
                                "Launch Sequence Completed",
                                f"Finished staggered launch process for all **{len(all_accounts)}** accounts into Place ID `{place_id}`.",
                                0x2ECC71
                            )
                            self._send_followup(resolved_app_id, interaction_token, {
                                "embeds": [{
                                    "title": "🚀 Staggered Join Sequence Completed",
                                    "description": f"Finished staggered launch process for all **{len(all_accounts)}** accounts into Place ID `{place_id}`.",
                                    "color": 0x2ECC71,
                                    "footer": {"text": "Roblox Account Manager | Launcher"},
                                    "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                }]
                            })
                        asyncio.create_task(run_batch_join())
                    else:
                        if target in self.ui.manager.accounts:
                            self._send_callback(url, headers, {
                                "type": 4,
                                "data": {
                                    "embeds": [{
                                        "title": "🚀 Spawning Game Session",
                                        "description": f"Launching Roblox player client for account **{target}** into Place ID `{place_id}`...",
                                        "color": 0xF1C40F,
                                        "footer": {"text": "Roblox Account Manager | Launcher"}
                                    }]
                                }
                            })
                            launcher_pref, custom_launcher_path = self.ui._get_roblox_launcher_config()
                            def run_single():
                                try:
                                    self.ui.manager.launch_roblox(
                                        username=target,
                                        game_id=place_id,
                                        launcher_preference=launcher_pref,
                                        custom_launcher_path=custom_launcher_path
                                    )
                                    self._send_webhook_embed(
                                        "Launch Successful",
                                        f"Roblox account **{target}** launched successfully into Place ID `{place_id}`.",
                                        0x2ECC71
                                    )
                                    self._send_followup(resolved_app_id, interaction_token, {
                                        "embeds": [{
                                            "title": "🚀 Launch Sequence Completed",
                                            "description": f"Roblox account **{target}** successfully deployed into Experience ID `{place_id}`.",
                                            "color": 0x2ECC71,
                                            "footer": {"text": "Roblox Account Manager | Launcher"},
                                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                        }]
                                    })
                                except Exception as e:
                                    self._send_webhook_embed(
                                        "Launch Failure",
                                        f"Launch sequence failed for account **{target}**: {e}",
                                        0xE74C3C
                                    )
                                    self._send_followup(resolved_app_id, interaction_token, {
                                        "embeds": [{
                                            "title": "❌ Launch Sequence Failed",
                                            "description": f"Launch sequence failed for account **{target}**:\n```python\n{e}\n```",
                                            "color": 0xE74C3C,
                                            "footer": {"text": "Roblox Account Manager | Launcher"},
                                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                        }]
                                    })
                            threading.Thread(target=run_single, daemon=True).start()
                        else:
                            self._send_callback(url, headers, {
                                "type": 4,
                                "data": {
                                    "embeds": [{
                                        "title": "❌ Account Not Found",
                                        "description": f"Error: Account profile **{target}** is not registered inside the database.",
                                        "color": 0xE74C3C,
                                        "footer": {"text": "Roblox Account Manager | Launcher"}
                                    }],
                                    "flags": 64
                                }
                            })
                elif command_name == "kill":
                    target = d["data"]["options"][0]["value"].strip()
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    if target.lower() in ("ram", "all"):
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "⚠️ Terminating All Active Sessions",
                                    "description": "Command received. Commencing force-termination of all active Roblox client players...",
                                    "color": 0xF1C40F,
                                    "footer": {"text": "Roblox Account Manager | Process Management"}
                                }]
                            }
                        })
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
                        self._send_webhook_embed(
                            "Roblox Instances Force-Closed",
                            f"Force-closed all active Roblox game client sessions (Closed tabs: **{count}**). Physical memory (RAM) has been flushed.",
                            0xE74C3C
                        )
                        self._send_followup(resolved_app_id, interaction_token, {
                            "embeds": [{
                                "title": "💥 Process Cleanup Completed",
                                "description": f"Successfully force-closed all active Roblox game client sessions and flushed physical memory (RAM).",
                                "color": 0xE74C3C,
                                "fields": [
                                    {"name": "🔴 Terminated Player Clients", "value": f"**{count}** game clients terminated", "inline": True}
                                ],
                                "footer": {"text": "Roblox Account Manager | Process Management"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        })
                    else:
                        resolved_pid = None
                        for entry in list(self.ui.instances_data):
                            if entry.get("username") == target:
                                resolved_pid = entry.get("pid")
                                break
                        if resolved_pid:
                            self._send_callback(url, headers, {
                                "type": 4,
                                "data": {
                                    "embeds": [{
                                        "title": "🛑 Terminating Session",
                                        "description": f"Command received. Commencing force-termination of Roblox session for account **{target}** (PID: `{resolved_pid}`)...",
                                        "color": 0xF1C40F,
                                        "footer": {"text": "Roblox Account Manager | Process Management"}
                                    }]
                                }
                            })
                            try:
                                subprocess.run(['taskkill', '/F', '/PID', str(resolved_pid)], creationflags=subprocess.CREATE_NO_WINDOW)
                                try:
                                    import psutil
                                    proc = psutil.Process(resolved_pid)
                                    proc.terminate()
                                except:
                                    pass
                                self._send_webhook_embed(
                                    "Roblox Instance Terminated",
                                    f"Roblox game client session for account **{target}** (PID: `{resolved_pid}`) force-closed successfully.",
                                    0xE74C3C
                                )
                                self._send_followup(resolved_app_id, interaction_token, {
                                    "embeds": [{
                                        "title": "💥 Session Terminated",
                                        "description": f"Roblox game client session for account **{target}** (PID: `{resolved_pid}`) force-closed successfully.",
                                        "color": 0xE74C3C,
                                        "footer": {"text": "Roblox Account Manager | Process Management"},
                                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                    }]
                                })
                            except Exception as e:
                                self._send_followup(resolved_app_id, interaction_token, {
                                    "embeds": [{
                                        "title": "❌ Session Termination Failed",
                                        "description": f"Failed to terminate session for account **{target}**:\n```python\n{e}\n```",
                                        "color": 0xE74C3C,
                                        "footer": {"text": "Roblox Account Manager | Process Management"},
                                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                    }]
                                })
                        else:
                            self._send_callback(url, headers, {
                                "type": 4,
                                "data": {
                                    "embeds": [{
                                        "title": "❌ Session Not Found",
                                        "description": f"No active game session found for Roblox account **{target}**.",
                                        "color": 0xE74C3C,
                                        "footer": {"text": "Roblox Account Manager | Process Management"}
                                    }],
                                    "flags": 64
                                }
                            })
                elif command_name == "addaccount":
                    options = d["data"].get("options", [])
                    opts_dict = {o["name"]: o["value"] for o in options}
                    method = opts_dict.get("method")
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    if method == "Cookie":
                        cookie = opts_dict.get("cookie", "").strip()
                        if not cookie:
                            self._send_callback(url, headers, {
                                "type": 4,
                                "data": {
                                    "embeds": [{
                                        "title": "❌ Import Refused",
                                        "description": "Roblox `.ROBLOSECURITY` cookie is required for the Cookie import method.",
                                        "color": 0xE74C3C,
                                        "footer": {"text": "Roblox Account Manager | Profile Importer"}
                                    }],
                                    "flags": 64
                                }
                            })
                            return
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "📥 Importing Cookie Profile",
                                    "description": "Validating and importing Roblox cookie profile...",
                                    "color": 0xF1C40F,
                                    "footer": {"text": "Roblox Account Manager | Profile Importer"}
                                }]
                            }
                        })
                        def run_import():
                            try:
                                success = self.ui.manager.import_cookie_account(cookie)
                                if success:
                                    self._send_webhook_embed(
                                        "Roblox Profile Imported",
                                        "Roblox account profile cookie has been validated and imported successfully into Roblox Account Manager!",
                                        0x2ECC71
                                    )
                                    self._send_followup(resolved_app_id, interaction_token, {
                                        "embeds": [{
                                            "title": "✓ Roblox Profile Imported",
                                            "description": "Roblox account profile cookie has been validated and imported successfully into Roblox Account Manager!",
                                            "color": 0x2ECC71,
                                            "footer": {"text": "Roblox Account Manager | Profile Importer"},
                                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                        }]
                                    })
                                else:
                                    self._send_webhook_embed(
                                        "Profile Import Failed",
                                        "Attempted to import cookie profile but validation failed. Cookie may be invalid or expired.",
                                        0xE74C3C
                                    )
                                    self._send_followup(resolved_app_id, interaction_token, {
                                        "embeds": [{
                                            "title": "❌ Profile Import Failed",
                                            "description": "Attempted to import cookie profile but validation failed. The cookie may be invalid or expired.",
                                            "color": 0xE74C3C,
                                            "footer": {"text": "Roblox Account Manager | Profile Importer"},
                                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                        }]
                                    })
                            except Exception as import_err:
                                self._send_followup(resolved_app_id, interaction_token, {
                                    "embeds": [{
                                        "title": "❌ Profile Import Failed",
                                        "description": f"An unexpected error occurred while importing:\n```python\n{import_err}\n```",
                                        "color": 0xE74C3C,
                                        "footer": {"text": "Roblox Account Manager | Profile Importer"},
                                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                    }]
                                })
                        threading.Thread(target=run_import, daemon=True).start()
                    else:
                        username = opts_dict.get("username", "").strip()
                        password = opts_dict.get("password", "").strip()
                        if not username or not password:
                            self._send_callback(url, headers, {
                                "type": 4,
                                "data": {
                                    "embeds": [{
                                        "title": "❌ Import Refused",
                                        "description": "Both 'username' and 'password' options are required for the Credentials import method.",
                                        "color": 0xE74C3C,
                                        "footer": {"text": "Roblox Account Manager | Profile Importer"}
                                    }],
                                    "flags": 64
                                }
                            })
                            return
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "📥 Spawning Browser Login Window",
                                    "description": f"Chrome browser login window spawned. Autofill sequence initiated for user **{username}**...",
                                    "color": 0x3498DB,
                                    "footer": {"text": "Roblox Account Manager | Profile Importer"}
                                }]
                            }
                        })
                        js_injection = (
                            "setTimeout(function() { "
                            "  var u = document.getElementById('login-username'); "
                            "  var p = document.getElementById('login-password'); "
                            "  if (u && p) { "
                            f"    u.value = '{username.replace(chr(39), chr(92)+chr(39))}'; "
                            f"    p.value = '{password.replace(chr(39), chr(92)+chr(39))}'; "
                            "    var b = document.getElementById('login-button'); "
                            "    if (b) b.click(); "
                            "  } "
                            "}, 2000);"
                        )
                        def run_selenium():
                            try:
                                self.ui.manager.add_account(amount=1, javascript=js_injection)
                                self._send_webhook_embed(
                                    "Chrome Autofill Spawned",
                                    f"Autofill sequence initiated successfully for user **{username}**.",
                                    0x3498DB
                                )
                            except Exception as selenium_err:
                                self._send_webhook_embed(
                                    "Chrome Autofill Spawn Failed",
                                    f"Autofill sequence failed for user **{username}**: {selenium_err}",
                                    0xE74C3C
                                )
                        threading.Thread(target=run_selenium, daemon=True).start()
                elif command_name == "list":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    all_accounts = list(self.ui.manager.accounts.keys())
                    if not all_accounts:
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "📋 Saved Accounts Directory",
                                    "description": "No registered Roblox accounts found registered inside RAM.",
                                    "color": 0x95A5A6,
                                    "footer": {"text": "Roblox Account Manager | Saved Accounts"}
                                }],
                                "flags": 64
                            }
                        })
                        return
                    fields = []
                    chunk_size = 15
                    for i in range(0, len(all_accounts), chunk_size):
                        chunk = all_accounts[i:i+chunk_size]
                        fields.append({
                            "name": f"Profiles {i+1} - {min(i+chunk_size, len(all_accounts))}",
                            "value": "\n".join(f"• **{acc}**" for acc in chunk),
                            "inline": True
                        })
                    self._send_webhook_embed(
                        "Roblox Account Manager Saved Profiles Directory",
                        f"Complete catalog index of all registered account profiles inside Roblox Account Manager (Total: **{len(all_accounts)}**).",
                        0x34495E,
                        fields=fields
                    )
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "embeds": [{
                                "title": "📋 Roblox Account Manager Saved Profiles Directory",
                                "description": f"Complete catalog index of all registered account profiles inside Roblox Account Manager (Total: **{len(all_accounts)}**).",
                                "color": 0x34495E,
                                "fields": fields,
                                "footer": {"text": "Roblox Account Manager | Saved Accounts"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        }
                    })
                elif command_name == "antiafk":
                    status = d["data"]["options"][0]["value"]
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    if status == "enable":
                        self.ui.settings["anti_afk_enabled"] = True
                        self.ui.save_settings()
                        self.ui.start_anti_afk()
                        self._send_webhook_embed(
                            "RAM Anti-AFK Engine Enabled",
                            "RAM's built-in Anti-AFK engine has been programmatically enabled! Connected game clients will no longer time out.",
                            0x3498DB
                        )
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "✓ RAM Anti-AFK Engine Enabled",
                                    "description": "RAM's built-in Anti-AFK keystroke simulation engine has been programmatically enabled! Connected game clients will no longer time out.",
                                    "color": 0x2ECC71,
                                    "footer": {"text": "Roblox Account Manager | Anti-AFK Engine"}
                                }],
                                "flags": 64
                            }
                        })
                    else:
                        self.ui.settings["anti_afk_enabled"] = False
                        self.ui.save_settings()
                        self.ui.stop_anti_afk()
                        self._send_webhook_embed(
                            "RAM Anti-AFK Engine Disabled",
                            "RAM's built-in Anti-AFK engine has been programmatically disabled! Connected game clients will no longer simulate keystrokes.",
                            0x3498DB
                        )
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "✓ RAM Anti-AFK Engine Disabled",
                                    "description": "RAM's built-in Anti-AFK keystroke simulation engine has been programmatically disabled! Connected game clients will no longer simulate keystrokes.",
                                    "color": 0xE74C3C,
                                    "footer": {"text": "Roblox Account Manager | Anti-AFK Engine"}
                                }],
                                "flags": 64
                            }
                        })
                elif command_name == "settings":
                    options = d["data"]["options"]
                    setting = options[0]["value"]
                    val_str = str(options[1]["value"]).strip()
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    parsed_val = val_str
                    if val_str.lower() == "true":
                        parsed_val = True
                    elif val_str.lower() == "false":
                        parsed_val = False
                    elif val_str.isdigit():
                        parsed_val = int(val_str)
                    self.ui.settings[setting] = parsed_val
                    self.ui.save_settings()
                    if setting == "anti_afk_enabled":
                        if parsed_val:
                            self.ui.start_anti_afk()
                        else:
                            self.ui.stop_anti_afk()
                    self._send_webhook_embed(
                        "Remote Configuration Update",
                        f"Remote Settings Override: set `{setting}` parameter to `{parsed_val}` successfully.",
                        0x3498DB
                    )
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "embeds": [{
                                "title": "🔧 Remote Configuration Update",
                                "description": f"Successfully updated settings configuration parameter **{setting}** to value `{parsed_val}`.",
                                "color": 0x3498DB,
                                "footer": {"text": "Roblox Account Manager | Remote Configuration"}
                            }],
                            "flags": 64
                        }
                    })
                elif command_name == "status":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    active_sessions = list(self.ui.instances_data)
                    if not active_sessions:
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "📈 Live Active Online Roblox Accounts",
                                    "description": "No active Roblox game sessions running.",
                                    "color": 0x95A5A6,
                                    "footer": {"text": "Roblox Account Manager | Performance Dashboard"}
                                }],
                                "flags": 64
                            }
                        })
                        return
                    fields = []
                    for entry in active_sessions:
                        username = entry.get("username", "Unknown")
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
                        fields.append({
                            "name": f"🎮 {username}",
                            "value": f"PID: `{entry.get('pid')}` | Place ID: `{entry.get('place_id', 'Unknown')}` | Uptime: `{uptime_str}`",
                            "inline": False
                        })
                    self._send_webhook_embed(
                        "Roblox Account Manager Performance Dashboard",
                        "Live metrics and performance snapshot of all active Roblox game client sessions.",
                        0x2ECC71,
                        fields=fields
                    )
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "embeds": [{
                                "title": "📈 Roblox Account Manager Performance Dashboard",
                                "description": "Live metrics and performance snapshot of all active Roblox game client sessions.",
                                "color": 0x2ECC71,
                                "fields": fields,
                                "footer": {"text": "Roblox Account Manager | Performance Dashboard"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        }
                    })
                elif command_name == "grab_place_id":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    saved_games = self.ui.settings.get("game_list", [])
                    if not saved_games:
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "embeds": [{
                                    "title": "🔒 Saved Roblox Game Place IDs",
                                    "description": "No saved Roblox game Place IDs found in the saved list.",
                                    "color": 0x95A5A6,
                                    "footer": {"text": "Roblox Account Manager | Saved Games"}
                                }],
                                "flags": 64
                            }
                        })
                        return
                    lines = []
                    for idx, game in enumerate(saved_games):
                        place_id = game.get("place_id", "Unknown")
                        name = game.get("name", "Unknown Game")
                        private_server = game.get("private_server", "")
                        ps_tag = " 🔒 *Private Server*" if private_server else ""
                        lines.append(f"**{idx + 1}. {name}**\n• Place ID: `{place_id}`{ps_tag}")
                    desc = "\n\n".join(lines)
                    if len(desc) > 3800:
                        desc = desc[:3800] + "\n\n*...and more (list truncated due to character limit)*"
                    self._send_webhook_embed(
                        "Saved Roblox Game Place IDs",
                        desc,
                        0x34495E
                    )
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "embeds": [{
                                "title": "🔒 Saved Roblox Game Place IDs",
                                "description": desc,
                                "color": 0x34495E,
                                "footer": {"text": "Roblox Account Manager | Saved Games"}
                            }],
                            "flags": 64
                        }
                    })
                elif command_name == "help":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    help_embed = {
                        "title": "📚 Roblox Account Manager Remote Commands Help Directory",
                        "description": (
                            "Welcome to the **Roblox Account Manager** remote control interface! "
                            "Below is a complete directory of all available slash commands registered on this server.\n\n"
                            "### ⚔️ Administrative & Maintenance\n"
                            "• **/admin_abuse <fps_cap> <place_id> <launch_delay>**\n"
                            "  *Use*: Resets Roblox clients, updates FPS cap engine configs, and stagger-launches all accounts.\n"
                            "• **/free_memory**\n"
                            "  *Use*: Trims working RAM sets for all active Roblox game client processes.\n"
                            "• **/kill_all**\n"
                            "  *Use*: Clears physical RAM by force-closing open Roblox player processes.\n"
                            "• **/kill <target>**\n"
                            "  *Use*: Force-closes specific player or `'all'` client tabs.\n\n"
                            "### 🚀 Multi-Launch & Deployment\n"
                            "• **/accounts <place_id>**\n"
                            "  *Use*: Select accounts paginated, launches stagger-joined (10ms stagger).\n"
                            "• **/list_join**\n"
                            "  *Use*: Select profiles via checkboxes, transitions to native input place modals.\n"
                            "• **/join_all <place_id>**\n"
                            "  *Use*: Stagger-joins all saved account profiles instantly.\n"
                            "• **/join <target> <place_id>**\n"
                            "  *Use*: Stagger-launches designated profile or `'all'` players.\n\n"
                            "### 📈 Diagnostics & Remote Controls\n"
                            "• **/active_accounts**\n"
                            "  *Use*: Displays active online profiles including operating PIDs.\n"
                            "• **/validity_check**\n"
                            "  *Use*: Authenticates and parses session validities background-threaded.\n"
                            "• **/resource**\n"
                            "  *Use*: Retrieves host PC CPU loads and memory (RAM) volumes.\n"
                            "• **/status**\n"
                            "  *Use*: Telemetry logs of online uptimes and places.\n"
                            "• **/grab_place_id**\n"
                            "  *Use*: Show all saved Roblox game Place IDs and details.\n\n"
                            "### ⚙️ System Profiles & Configs\n"
                            "• **/addaccount <method>**\n"
                            "  *Use*: Remotely imports profile via cookie or credentials JS injection.\n"
                            "• **/list**\n"
                            "  *Use*: Lists all registered profiles inside catalog.\n"
                            "• **/antiafk <status>**\n"
                            "  *Use*: Activates keypress simulator to bypass idle kick limits.\n"
                            "• **/settings <setting> <value>**\n"
                            "  *Use*: Configures application preferences in real-time remotely.\n"
                            "• **/activity_log <status>**\n"
                            "  *Use*: Enables/disables live standard stream mirroring to webhook channels.\n"
                            "• **/help**\n"
                            "  *Use*: Shows this command directory panel."
                        ),
                        "color": 0x34495E,
                        "footer": {"text": "Roblox Account Manager | Remote Controller Help"},
                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                    }
                    self._send_webhook_embed(
                        "Roblox Account Manager Remote Commands Help Directory",
                        help_embed["description"],
                        0x34495E
                    )
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "embeds": [help_embed],
                            "flags": 64
                        }
                    })
                elif command_name == "summary":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    self._send_callback(url, headers, {
                        "type": 5,
                        "data": {"flags": 64}
                    })
                    def run_summary_worker():
                        try:
                            summaries = self.ui.summary_service.get_all_summaries()
                            embeds = []
                            if not summaries:
                                embeds.append({
                                    "title": "📋 Accounts Overview Summary",
                                    "description": "No accounts found registered in the Account Manager catalog.",
                                    "color": 0x95A5A6,
                                    "footer": {"text": "Roblox Account Manager | Summary Engine"},
                                    "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                })
                            else:
                                accounts_list = list(summaries.items())
                                if len(accounts_list) <= 9:
                                    for username, state in accounts_list:
                                        user_id = state.get("user_id") or "Unknown"
                                        st = state.get("start_time")
                                        uptime = state.get("uptime") or "00:00:00"
                                        pfp_url = state.get("pfp_url")
                                        status_indicator = "🟢 Online" if st is not None else "🔴 Offline"
                                        color = 0x2ECC71 if st is not None else 0xE74C3C
                                        embed = {
                                            "title": f"👤 Profile: {username}",
                                            "color": color,
                                            "fields": [
                                                {"name": "Username", "value": f"`{username}`", "inline": True},
                                                {"name": "User ID", "value": f"`{user_id}`", "inline": True},
                                                {"name": "Status", "value": f"**{status_indicator}**", "inline": True}
                                            ],
                                            "footer": {"text": "Roblox Account Manager | Profiler"},
                                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                        }
                                        if st is not None:
                                            embed["fields"].append({"name": "Uptime", "value": f"`{uptime}`", "inline": True})
                                        if pfp_url:
                                            embed["thumbnail"] = {"url": pfp_url}
                                        embeds.append(embed)
                                else:
                                    for username, state in accounts_list[:8]:
                                        user_id = state.get("user_id") or "Unknown"
                                        st = state.get("start_time")
                                        uptime = state.get("uptime") or "00:00:00"
                                        pfp_url = state.get("pfp_url")
                                        status_indicator = "🟢 Online" if st is not None else "🔴 Offline"
                                        color = 0x2ECC71 if st is not None else 0xE74C3C
                                        embed = {
                                            "title": f"👤 Profile: {username}",
                                            "color": color,
                                            "fields": [
                                                {"name": "Username", "value": f"`{username}`", "inline": True},
                                                {"name": "User ID", "value": f"`{user_id}`", "inline": True},
                                                {"name": "Status", "value": f"**{status_indicator}**", "inline": True}
                                            ],
                                            "footer": {"text": "Roblox Account Manager | Profiler"},
                                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                        }
                                        if st is not None:
                                            embed["fields"].append({"name": "Uptime", "value": f"`{uptime}`", "inline": True})
                                        if pfp_url:
                                            embed["thumbnail"] = {"url": pfp_url}
                                        embeds.append(embed)
                                    remaining_lines = []
                                    for username, state in accounts_list[8:]:
                                        user_id = state.get("user_id") or "Unknown"
                                        st = state.get("start_time")
                                        uptime = state.get("uptime") or "00:00:00"
                                        status_indicator = "🟢 Online" if st is not None else "🔴 Offline"
                                        status_text = f"{status_indicator} (`{uptime}`)" if st is not None else status_indicator
                                        remaining_lines.append(f"• **{username}** (ID: `{user_id}`): {status_text}")
                                    desc = "\n".join(remaining_lines)
                                    if len(desc) > 3800:
                                        desc = desc[:3800] + "\n*(list truncated)*"
                                    embeds.append({
                                        "title": f"📁 Additional Accounts ({len(accounts_list) - 8} Profiles)",
                                        "description": desc,
                                        "color": 0x34495E,
                                        "footer": {"text": "Roblox Account Manager | Summary Engine"},
                                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                                    })
                            followup_url = f"https://discord.com/api/v10/webhooks/{resolved_app_id}/{interaction_token}"
                            requests.post(followup_url, json={"embeds": embeds}, timeout=10)
                        except:
                            pass
                    threading.Thread(target=run_summary_worker, daemon=True).start()
            elif interaction_type == 3:
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

    async def _send_paginated_accounts(self, interaction_id, interaction_token, place_id, page_index, headers):
        all_accounts = list(self.ui.manager.accounts.keys())
        if not all_accounts:
            url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
            self._send_callback(url, headers, {
                "type": 4,
                "data": {
                    "content": "No Roblox accounts found in the application.",
                    "flags": 64
                }
            })
            return
        select_options = [{"label": acc[:100], "value": acc[:100]} for acc in all_accounts[page_index*25 : (page_index+1)*25]]
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
                        "custom_id": f"bot_page:prev:{place_id}:{page_index}",
                        "disabled": page_index == 0
                    },
                    {
                        "type": 2,
                        "style": 2,
                        "label": "Next ▶",
                        "custom_id": f"bot_page:next:{place_id}:{page_index}",
                        "disabled": (page_index+1)*25 >= len(all_accounts)
                    }
                ]
            })
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        self._send_callback(url, headers, {
            "type": 4,
            "data": {
                "content": f"Select the Roblox accounts you want to launch into Place ID `{place_id}` (Page {page_index + 1}):",
                "components": components,
                "flags": 64
            }
        })

    async def _send_paginated_list_join(self, interaction_id, interaction_token, page_index, headers):
        all_accounts = list(self.ui.manager.accounts.keys())
        if not all_accounts:
            url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
            self._send_callback(url, headers, {
                "type": 4,
                "data": {
                    "content": "No Roblox accounts found registered in the application.",
                    "flags": 64
                }
            })
            return
        select_options = [{"label": acc[:100], "value": acc[:100]} for acc in all_accounts[page_index*25 : (page_index+1)*25]]
        components = [
            {
                "type": 1,
                "components": [
                    {
                        "type": 3,
                        "custom_id": "list_join_select:",
                        "placeholder": "Select accounts to join...",
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
                        "custom_id": f"list_join_page:prev:{page_index}",
                        "disabled": page_index == 0
                    },
                    {
                        "type": 2,
                        "style": 2,
                        "label": "Next ▶",
                        "custom_id": f"list_join_page:next:{page_index}",
                        "disabled": (page_index+1)*25 >= len(all_accounts)
                    }
                ]
            })
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        self._send_callback(url, headers, {
            "type": 4,
            "data": {
                "content": f"Select the Roblox accounts you want to launch (Page {page_index + 1}):",
                "components": components,
                "flags": 64
            }
        })
