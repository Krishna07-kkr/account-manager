import asyncio
import json
import threading
import time
import subprocess
import requests
import websockets
import sys
import psutil
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
        if "interactions/prefix_msg/" in url:
            channel_id = url.split("interactions/prefix_msg/")[1].split("/")[0]
            bot_token = headers.get("Authorization", "").replace("Bot ", "").strip()
            self._send_prefix_response(channel_id, bot_token, payload)
            return
        def do_post():
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=5)
                if res.status_code not in (200, 201, 204):
                    print(f"[ERROR] Discord API callback rejected ({res.status_code}): {res.text}")
            except Exception as e:
                print(f"[ERROR] Discord API callback connection failed: {e}")
        threading.Thread(target=do_post, daemon=True).start()

    def _send_followup(self, app_id, token, payload):
        if token and token.isdigit():
            bot_token = self.ui.settings.get("discord_bot_token", "").strip()
            self._send_prefix_response(token, bot_token, payload)
            return
        def do_post():
            try:
                url = f"https://discord.com/api/v10/webhooks/{app_id}/{token}"
                res = requests.post(url, json=payload, timeout=5)
                if res.status_code not in (200, 201, 204):
                    print(f"[ERROR] Discord API followup rejected ({res.status_code}): {res.text}")
            except Exception as e:
                print(f"[ERROR] Discord API followup connection failed: {e}")
        threading.Thread(target=do_post, daemon=True).start()

    def _send_prefix_response(self, channel_id, token, payload):
        try:
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            data = payload
            if "data" in payload:
                data = payload["data"]
            if payload.get("type") == 5:
                return
            content = data.get("content", "")
            embeds = data.get("embeds", [])
            components = data.get("components", [])
            if not content and not embeds:
                return
            post_payload = {}
            if content:
                post_payload["content"] = content
            if embeds:
                post_payload["embeds"] = embeds
            if components:
                post_payload["components"] = components
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            def do_post():
                try:
                    res = requests.post(url, headers=headers, json=post_payload, timeout=5)
                    if res.status_code not in (200, 201, 204):
                        print(f"[ERROR] Prefix response rejected ({res.status_code}): {res.text}")
                except Exception as e:
                    print(f"[ERROR] Prefix response connection failed: {e}")
            threading.Thread(target=do_post, daemon=True).start()
        except Exception as e:
            print(f"[ERROR] Failed to send prefix response: {e}")

    def _commands_need_sync(self, local_cmds, registered_cmds):
        if len(local_cmds) != len(registered_cmds):
            return True
        reg_map = {c["name"]: c for c in registered_cmds}
        for lc in local_cmds:
            rc = reg_map.get(lc["name"])
            if not rc:
                return True
            if lc.get("description") != rc.get("description"):
                return True
            local_opts = lc.get("options", [])
            reg_opts = rc.get("options", [])
            if len(local_opts) != len(reg_opts):
                return True
            for lo, ro in zip(local_opts, reg_opts):
                if lo.get("name") != ro.get("name") or lo.get("description") != ro.get("description") or lo.get("type") != ro.get("type") or lo.get("required", False) != ro.get("required", False):
                    return True
                local_choices = lo.get("choices", [])
                reg_choices = ro.get("choices", [])
                if len(local_choices) != len(reg_choices):
                    return True
                for lch, rch in zip(local_choices, reg_choices):
                    if lch.get("name") != rch.get("name") or lch.get("value") != rch.get("value"):
                        return True
        return False

    def _parse_prefix_args(self, command_name, parts):
        commands = get_commands_definition()
        cmd_def = next((c for c in commands if c["name"] == command_name), None)
        if not cmd_def:
            return {}
        
        args = parts[1:]
        
        def parse_options_list(options, arg_list):
            parsed = []
            arg_idx = 0
            for opt in options:
                opt_type = opt.get("type")
                if opt_type == 1:  # SUB_COMMAND
                    if arg_idx < len(arg_list) and arg_list[arg_idx].lower() == opt["name"].lower():
                        arg_idx += 1
                        sub_options = opt.get("options", [])
                        sub_parsed = parse_options_list(sub_options, arg_list[arg_idx:])
                        if sub_parsed is None:
                            return None
                        parsed.append({
                            "name": opt["name"],
                            "type": 1,
                            "options": sub_parsed
                        })
                        return parsed
                    elif opt.get("required", False):
                        return None
                else:
                    if arg_idx < len(arg_list):
                        val = arg_list[arg_idx]
                        arg_idx += 1
                        if opt_type == 4:  # INTEGER
                            try:
                                val = int(val)
                            except:
                                pass
                        elif opt_type == 5:  # BOOLEAN
                            val = val.lower() in ("true", "1", "yes", "enable", "on")
                        parsed.append({
                            "name": opt["name"],
                            "value": val
                        })
                    elif opt.get("required", False):
                        return None
            return parsed

        return parse_options_list(cmd_def.get("options", []), args)

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
        try:
            url = f"https://discord.com/api/v10/applications/{application_id}/commands"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            commands = get_commands_definition()
            
            need_sync = "--sync" in sys.argv
            if not need_sync:
                res_get = requests.get(url, headers=headers, timeout=5)
                if res_get.status_code == 200:
                    registered = res_get.json()
                    need_sync = self._commands_need_sync(commands, registered)
                else:
                    need_sync = True

            if need_sync:
                print("[INFO] Registering Discord slash commands globally...")
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
            else:
                print("[INFO] Discord slash commands are already up-to-date globally.")
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
            for attempt in range(3):
                res_get = requests.get(url, headers=headers, timeout=5)
                if res_get.status_code == 429:
                    try:
                        retry_after = res_get.json().get("retry_after", 5.0)
                    except:
                        retry_after = 5.0
                    print(f"[WARNING] Discord guild command get rate-limited. Retrying in {retry_after}s... (attempt {attempt + 1}/3)")
                    await asyncio.sleep(retry_after)
                    continue
                if res_get.status_code == 200:
                    guild_cmds = res_get.json()
                    if guild_cmds:
                        print(f"[INFO] Clearing legacy guild-level commands for guild {guild_id}...")
                        for put_attempt in range(3):
                            res = requests.put(url, headers=headers, json=[], timeout=5)
                            if res.status_code == 429:
                                try:
                                    retry_after = res.json().get("retry_after", 5.0)
                                except:
                                    retry_after = 5.0
                                print(f"[WARNING] Discord guild command clear rate-limited. Retrying in {retry_after}s... (attempt {put_attempt + 1}/3)")
                                await asyncio.sleep(retry_after)
                                continue
                            print(f"[INFO] Guild-level commands cleared status for guild {guild_id}: {res.status_code}")
                            break
                break
        except Exception as e:
            print(f"[ERROR] Guild command sync exception: {e}")

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
            command_name = parts[0][1:].lower()
            
            commands = get_commands_definition()
            cmd_def = next((c for c in commands if c["name"] == command_name), None)
            
            if not cmd_def and command_name == "launch":
                cmd_def = next((c for c in commands if c["name"] == "join"), None)
                
            if not cmd_def:
                return
                
            parsed_opts = self._parse_prefix_args(cmd_def["name"], parts)
            if parsed_opts is None:
                options = cmd_def.get("options", [])
                usage_parts = []
                for opt in options:
                    if opt.get("required", False):
                        usage_parts.append(f"<{opt['name']}>")
                    else:
                        usage_parts.append(f"[{opt['name']}]")
                usage = f"Usage: `!{command_name} " + " ".join(usage_parts) + "`"
                
                headers = {
                    "Authorization": f"Bot {token}",
                    "Content-Type": "application/json"
                }
                url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                requests.post(url, headers=headers, json={"content": usage}, timeout=5)
                return
            
            mock_d = {
                "type": 2,
                "id": "prefix_msg",
                "token": channel_id,
                "application_id": None,
                "user": {"id": author_id},
                "member": {"user": {"id": author_id}},
                "data": {
                    "name": cmd_def["name"],
                    "options": parsed_opts
                }
            }
            
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            
            await handle_interaction(self, cmd_def["name"], mock_d, token, headers, None, "prefix_msg", channel_id)
        except Exception as e:
            print(f"[ERROR] Prefix command dispatch error: {e}")

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
                    private_server = ""
                    components = d.get("data", {}).get("components", [])
                    for row in components:
                        for comp in row.get("components", []):
                            if comp.get("custom_id") == "place_input":
                                place_id = comp.get("value", "").strip()
                            elif comp.get("custom_id") == "private_server_input":
                                private_server = comp.get("value", "").strip()
                    
                    if not place_id and not private_server:
                        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                        self._send_callback(url, headers, {
                            "type": 4,
                            "data": {
                                "content": "[ERROR] You must specify either a Roblox Place ID or a Private Server Link/Code.",
                                "flags": 64
                            }
                        })
                        return

                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    hook_ok = self._send_webhook_embed(
                        "Launch Sequence Initiated",
                        "Programmatic batch launch sequence started.",
                        0x95A5A6,
                        fields=[
                            {"name": "🎮 Launch Mode", "value": "`PLACE_ID`" if place_id else "`PRIVATE_SERVER`", "inline": True},
                            {"name": "📍 Target", "value": f"`{place_id or private_server}`", "inline": True},
                            {"name": "👥 Total Accounts", "value": f"**{len(selected_accounts)}**", "inline": True}
                        ]
                    )
                    target_display = f"Place ID `{place_id}`" if place_id else f"Private Server `{private_server}`"
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "content": f"[INFO] Programmatic launch sequence started for {len(selected_accounts)} accounts into {target_display}! Details sent to Webhook." if hook_ok else f"[INFO] Programmatic launch sequence started for {len(selected_accounts)} accounts into {target_display}..."
                        }
                    })
                    launcher_pref, custom_launcher_path = self.ui._get_roblox_launcher_config()
                    for idx, account_name in enumerate(selected_accounts):
                        if account_name in self.ui.manager.accounts:
                            try:
                                self.ui.manager.launch_roblox(
                                    username=account_name,
                                    game_id=place_id,
                                    private_server_id=private_server,
                                    launcher_preference=launcher_pref,
                                    custom_launcher_path=custom_launcher_path
                                )
                                self._send_webhook_embed(
                                    "Launch Successful",
                                    f"Profile **{account_name}** launched successfully.",
                                    0x2ECC71,
                                    fields=[
                                        {"name": "👤 Account", "value": f"**{account_name}**", "inline": True},
                                        {"name": "🔌 Status", "value": "🟢 Online", "inline": True}
                                    ]
                                )
                            except Exception as e:
                                self._send_webhook_embed(
                                    "Launch Failure",
                                    f"Profile **{account_name}** failed to launch.",
                                    0xE74C3C,
                                    fields=[
                                        {"name": "👤 Account", "value": f"**{account_name}**", "inline": True},
                                        {"name": "❌ Error Detail", "value": f"```{e}```", "inline": False}
                                    ]
                                )
                        await asyncio.sleep(0.01)
                    hook_end = self._send_webhook_embed(
                        "Launch Sequence Completed",
                        "Finished staggered launch process.",
                        0x2ECC71,
                        fields=[
                            {"name": "🟢 Launched Successfully", "value": f"**{len(selected_accounts)}** accounts", "inline": True}
                        ]
                    )
                    self._send_followup(resolved_app_id, interaction_token, {
                        "content": f"[SUCCESS] Finished launching {len(selected_accounts)} accounts into {target_display}! Details sent to Webhook." if hook_end else f"[SUCCESS] Finished launching {len(selected_accounts)} accounts into {target_display}!"
                    })
                elif custom_id.startswith("interactive_join_modal:"):
                    parts = custom_id.split(":")
                    mode = parts[1]
                    accounts = parts[2].split(",")
                    input_val = ""
                    components = d.get("data", {}).get("components", [])
                    for row in components:
                        for comp in row.get("components", []):
                            if comp.get("custom_id") == "join_input_value":
                                input_val = comp.get("value", "").strip()
                                break
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    place_id = input_val if mode == "place_id" else ""
                    private_server_id = input_val if mode == "private_server" else ""
                    target_display = f"Place ID `{place_id}`" if mode == "place_id" else "Private Server link/code"
                    self._send_callback(url, headers, {
                        "type": 4,
                        "data": {
                            "content": f"⌛ Launch sequence initiated for **{len(accounts)}** accounts into {target_display}. Progress is being reported via webhook."
                        }
                    })
                    self._send_webhook_embed(
                        "Launch Sequence Initiated",
                        "Staggered launch sequence started.",
                        0x95A5A6,
                        fields=[
                            {"name": "🎮 Launch Mode", "value": f"`{mode.upper()}`", "inline": True},
                            {"name": "📍 Target", "value": f"`{input_val}`", "inline": True},
                            {"name": "👥 Total Accounts", "value": f"**{len(accounts)}**", "inline": True}
                        ]
                    )
                    launcher_pref, custom_launcher_path = self.ui._get_roblox_launcher_config()
                    async def run_batch():
                        success_count = 0
                        fail_count = 0
                        for account_name in accounts:
                            if account_name in self.ui.manager.accounts:
                                try:
                                    self.ui.manager.launch_roblox(
                                        username=account_name,
                                        game_id=place_id,
                                        private_server_id=private_server_id,
                                        launcher_preference=launcher_pref,
                                        custom_launcher_path=custom_launcher_path
                                    )
                                    success_count += 1
                                    self._send_webhook_embed(
                                        "Launch Successful",
                                        f"Profile **{account_name}** launched successfully.",
                                        0x2ECC71,
                                        fields=[
                                            {"name": "👤 Account", "value": f"**{account_name}**", "inline": True},
                                            {"name": "🔌 Status", "value": "🟢 Online", "inline": True}
                                        ]
                                    )
                                except Exception as e:
                                    fail_count += 1
                                    self._send_webhook_embed(
                                        "Launch Failure",
                                        f"Profile **{account_name}** failed to launch.",
                                        0xE74C3C,
                                        fields=[
                                            {"name": "👤 Account", "value": f"**{account_name}**", "inline": True},
                                            {"name": "❌ Error Detail", "value": f"```{e}```", "inline": False}
                                        ]
                                    )
                            await asyncio.sleep(0.01)
                        self._send_webhook_embed(
                            "Launch Sequence Completed",
                            "Staggered launch process completed.",
                            0x2ECC71,
                            fields=[
                                {"name": "🟢 Launched Successfully", "value": f"**{success_count}** accounts", "inline": True},
                                {"name": "🔴 Failed to Launch", "value": f"**{fail_count}** accounts", "inline": True}
                            ]
                        )
                        self._send_followup(resolved_app_id, interaction_token, {
                            "embeds": [{
                                "title": "🚀 Staggered Join Sequence Completed",
                                "description": "Finished launching all selected accounts.",
                                "color": 0x2ECC71 if fail_count == 0 else 0xF1C40F,
                                "fields": [
                                    {"name": "🟢 Launched Successfully", "value": f"**{success_count}**", "inline": True},
                                    {"name": "🔴 Failed to Launch", "value": f"**{fail_count}**", "inline": True},
                                    {"name": "📍 Target Experience", "value": f"`{input_val[:100]}`", "inline": False}
                                ],
                                "footer": {"text": "Roblox Account Manager | Batch Launcher"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        })
                    asyncio.create_task(run_batch())
                return

            if interaction_type == 2:
                command_name = d.get("data", {}).get("name")
                await handle_interaction(self, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token)
                return

            if interaction_type == 3:
                custom_id = d.get("data", {}).get("custom_id", "")
                if custom_id.startswith("launch_select:"):
                    parts = custom_id.split(":")
                    place_id = parts[1]
                    private_server = parts[2] if len(parts) > 2 else ""
                    selected_accounts = d.get("data", {}).get("values", [])
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    target_display = f"Place ID `{place_id}`" if place_id else f"Private Server `{private_server}`"
                    hook_ok = self._send_webhook_embed(
                        "Launch Sequence Initiated",
                        "Programmatic batch launch sequence started.",
                        0x95A5A6,
                        fields=[
                            {"name": "🎮 Launch Mode", "value": "`PLACE_ID`" if place_id else "`PRIVATE_SERVER`", "inline": True},
                            {"name": "📍 Target", "value": f"`{place_id or private_server}`", "inline": True},
                            {"name": "👥 Total Accounts", "value": f"**{len(selected_accounts)}**", "inline": True}
                        ]
                    )
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "content": f"[INFO] Programmatic launch sequence started for {len(selected_accounts)} accounts into {target_display}! Detailed status dispatched to Webhook." if hook_ok else f"[INFO] Programmatic launch sequence started for {len(selected_accounts)} accounts into {target_display}...",
                            "components": []
                        }
                    })
                    launcher_pref, custom_launcher_path = self.ui._get_roblox_launcher_config()
                    async def run_batch_launch_select():
                        success_count = 0
                        fail_count = 0
                        for idx, account_name in enumerate(selected_accounts):
                            if account_name in self.ui.manager.accounts:
                                try:
                                    self.ui.manager.launch_roblox(
                                        username=account_name,
                                        game_id=place_id,
                                        private_server_id=private_server,
                                        launcher_preference=launcher_pref,
                                        custom_launcher_path=custom_launcher_path
                                    )
                                    success_count += 1
                                    self._send_webhook_embed(
                                        "Launch Successful",
                                        f"Profile **{account_name}** launched successfully.",
                                        0x2ECC71,
                                        fields=[
                                            {"name": "👤 Account", "value": f"**{account_name}**", "inline": True},
                                            {"name": "🔌 Status", "value": "🟢 Online", "inline": True}
                                        ]
                                    )
                                except Exception as e:
                                    fail_count += 1
                                    self._send_webhook_embed(
                                        "Launch Failure",
                                        f"Profile **{account_name}** failed to launch.",
                                        0xE74C3C,
                                        fields=[
                                            {"name": "👤 Account", "value": f"**{account_name}**", "inline": True},
                                            {"name": "❌ Error Detail", "value": f"```{e}```", "inline": False}
                                        ]
                                    )
                            await asyncio.sleep(0.01)
                        self._send_webhook_embed(
                            "Launch Sequence Completed",
                            "Finished staggered launch process.",
                            0x2ECC71,
                            fields=[
                                {"name": "🟢 Launched Successfully", "value": f"**{success_count}** accounts", "inline": True},
                                {"name": "🔴 Failed to Launch", "value": f"**{fail_count}** accounts", "inline": True}
                            ]
                        )
                        self._send_followup(resolved_app_id, interaction_token, {
                            "embeds": [{
                                "title": "🚀 Staggered Join Sequence Completed",
                                "description": f"Finished launching all **{len(selected_accounts)}** accounts.",
                                "color": 0x2ECC71 if fail_count == 0 else 0xF1C40F,
                                "fields": [
                                    {"name": "🟢 Launched Successfully", "value": f"**{success_count}**", "inline": True},
                                    {"name": "🔴 Failed to Launch", "value": f"**{fail_count}**", "inline": True},
                                    {"name": "📍 Target", "value": f"`{place_id or private_server}`", "inline": False}
                                ],
                                "footer": {"text": "Roblox Account Manager | Launcher"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        })
                    asyncio.create_task(run_batch_launch_select())
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
                                            "min_length": 0,
                                            "max_length": 30,
                                            "placeholder": "e.g. 185655138",
                                            "required": False
                                        }
                                    ]
                                },
                                {
                                    "type": 1,
                                    "components": [
                                        {
                                            "type": 4,
                                            "custom_id": "private_server_input",
                                            "style": 1,
                                            "label": "Enter Private Server Link or Code",
                                            "min_length": 0,
                                            "max_length": 300,
                                            "placeholder": "e.g. private server link/code",
                                            "required": False
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
                    private_server = parts[3]
                    current_page = int(parts[4])
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
                                    "custom_id": f"launch_select:{place_id}:{private_server}",
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
                                    "custom_id": f"bot_page:prev:{place_id}:{private_server}:{new_page}",
                                    "disabled": new_page == 0
                                },
                                {
                                    "type": 2,
                                    "style": 2,
                                    "label": "Next ▶",
                                    "custom_id": f"bot_page:next:{place_id}:{private_server}:{new_page}",
                                    "disabled": (new_page+1)*25 >= len(all_accounts)
                                }
                            ]
                        })
                    target_display = f"Place ID `{place_id}`" if place_id else f"Private Server `{private_server}`"
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "content": f"Select the Roblox accounts you want to launch into {target_display} (Page {new_page + 1}):",
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
                elif custom_id.startswith("interactive_join_select:"):
                    parts = custom_id.split(":")
                    page_index = int(parts[1])
                    mode = parts[2]
                    new_values = d.get("data", {}).get("values", [])
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    all_accounts = list(self.ui.manager.accounts.keys())
                    selected = self._update_selected_accounts(d.get("message"), new_values, page_index, all_accounts)
                    embed = self._build_interactive_join_embed(selected, mode)
                    components = self._build_interactive_join_components(all_accounts, page_index, selected, mode)
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "embeds": [embed],
                            "components": components
                        }
                    })
                elif custom_id.startswith("interactive_join_page:"):
                    parts = custom_id.split(":")
                    action = parts[1]
                    current_page = int(parts[2])
                    mode = parts[3]
                    new_page = current_page + 1 if action == "next" else current_page - 1
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    all_accounts = list(self.ui.manager.accounts.keys())
                    selected = self._get_selected_accounts_from_message(d.get("message"))
                    embed = self._build_interactive_join_embed(selected, mode)
                    components = self._build_interactive_join_components(all_accounts, new_page, selected, mode)
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "embeds": [embed],
                            "components": components
                        }
                    })
                elif custom_id.startswith("interactive_join_toggle:"):
                    parts = custom_id.split(":")
                    page_index = int(parts[1])
                    mode = parts[2]
                    new_mode = "private_server" if mode == "place_id" else "place_id"
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    all_accounts = list(self.ui.manager.accounts.keys())
                    selected = self._get_selected_accounts_from_message(d.get("message"))
                    embed = self._build_interactive_join_embed(selected, new_mode)
                    components = self._build_interactive_join_components(all_accounts, page_index, selected, new_mode)
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "embeds": [embed],
                            "components": components
                        }
                    })
                elif custom_id == "interactive_join_launch":
                    selected = self._get_selected_accounts_from_message(d.get("message"))
                    mode = "place_id"
                    for row in d.get("message", {}).get("components", []):
                        for comp in row.get("components", []):
                            if comp.get("custom_id", "").startswith("interactive_join_toggle:"):
                                mode = comp.get("custom_id").split(":")[2]
                                break
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    selected_str = ",".join(selected)
                    label_text = "Enter Roblox Place ID" if mode == "place_id" else "Enter Private Server Link or Code"
                    placeholder_text = "e.g. 185655138" if mode == "place_id" else "e.g. private server link"
                    modal_payload = {
                        "type": 9,
                        "data": {
                            "title": "Configure Launch Target",
                            "custom_id": f"interactive_join_modal:{mode}:{selected_str}",
                            "components": [
                                {
                                    "type": 1,
                                    "components": [
                                        {
                                            "type": 4,
                                            "custom_id": "join_input_value",
                                            "style": 1,
                                            "label": label_text,
                                            "min_length": 1,
                                            "max_length": 300,
                                            "placeholder": placeholder_text,
                                            "required": True
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                    self._send_callback(url, headers, modal_payload)
                elif custom_id == "interactive_kill_select":
                    selected_values = d.get("data", {}).get("values", [])
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    running_accounts = [entry.get("username") for entry in self.ui.instances_data if entry.get("username")]
                    embed = self._build_interactive_kill_embed(selected_values)
                    components = self._build_interactive_kill_components(running_accounts, selected_values)
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "embeds": [embed],
                            "components": components
                        }
                    })
                elif custom_id == "interactive_kill_selected":
                    selected = self._get_selected_accounts_from_message(d.get("message"))
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "content": f"⌛ Terminating **{len(selected)}** selected Roblox player client sessions...",
                            "embeds": [],
                            "components": []
                        }
                    })
                    killed_count = 0
                    for username in selected:
                        for entry in list(self.ui.instances_data):
                            if entry.get("username") == username:
                                pid = entry.get("pid")
                                if pid:
                                    try:
                                        subprocess.run(['taskkill', '/F', '/PID', str(pid)], creationflags=subprocess.CREATE_NO_WINDOW)
                                        try:
                                            proc = psutil.Process(pid)
                                            proc.terminate()
                                        except:
                                            pass
                                        killed_count += 1
                                    except:
                                        pass
                                    break
                    self._send_webhook_embed(
                        "Roblox Instances Terminated",
                        f"Interactive termination sequence force-closed **{killed_count}** player sessions.",
                        0xE74C3C,
                        fields=[
                            {"name": "👥 Requested Accounts", "value": ", ".join(selected), "inline": False},
                            {"name": "🔴 Closed Sessions", "value": f"**{killed_count}** clients", "inline": True},
                            {"name": "🔌 Status", "value": "🔴 Terminated", "inline": True}
                        ]
                    )
                    self._send_followup(resolved_app_id, interaction_token, {
                        "embeds": [{
                            "title": "💥 Process Cleanup Completed",
                            "description": f"Successfully force-terminated **{killed_count}** selected Roblox game player clients.",
                            "color": 0xE74C3C,
                            "footer": {"text": "Roblox Account Manager | Process Management"},
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        }]
                    })
                elif custom_id == "interactive_kill_all":
                    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
                    self._send_callback(url, headers, {
                        "type": 7,
                        "data": {
                            "content": "⌛ Terminating all active Roblox player client sessions...",
                            "embeds": [],
                            "components": []
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
                        "Force-closed all active Roblox game client sessions.",
                        0xE74C3C,
                        fields=[
                            {"name": "🔴 Terminated Player Clients", "value": f"**{count}** game clients terminated", "inline": True},
                            {"name": "⚙️ Status", "value": "Flushed memory (RAM)", "inline": True}
                        ]
                    )
                    self._send_followup(resolved_app_id, interaction_token, {
                        "embeds": [{
                            "title": "💥 Process Cleanup Completed",
                            "description": "Successfully force-closed all active Roblox game client sessions and flushed physical memory (RAM).",
                            "color": 0xE74C3C,
                            "fields": [
                                {"name": "🔴 Terminated Player Clients", "value": f"**{count}** game clients terminated", "inline": True}
                            ],
                            "footer": {"text": "Roblox Account Manager | Process Management"},
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        }]
                    })
        except Exception as err:
            print(f"[ERROR] Discord Bot interaction handling failed: {err}")

    def _get_selected_accounts_from_message(self, msg):
        selected = []
        if not msg or "components" not in msg:
            return selected
        for row in msg.get("components", []):
            for comp in row.get("components", []):
                if comp.get("type") == 3:
                    for opt in comp.get("options", []):
                        if opt.get("default"):
                            selected.append(opt.get("value"))
        return selected

    def _update_selected_accounts(self, msg, new_values, page_index, all_accounts):
        current_page_accounts = set(all_accounts[page_index*25 : (page_index+1)*25])
        previous_selected = set(self._get_selected_accounts_from_message(msg))
        other_page_selected = previous_selected - current_page_accounts
        final_selected = list(other_page_selected | set(new_values))
        return final_selected

    def _build_interactive_join_embed(self, selected_accounts, mode):
        sel_display = ", ".join(f"**{acc}**" for acc in selected_accounts) if selected_accounts else "*None selected*"
        mode_display = "📍 **Roblox Place ID**" if mode == "place_id" else "🔑 **Private Server Link/Code**"
        return {
            "title": "🎮 Experiential Join Panel",
            "description": "Interactive launcher setup. Choose accounts, toggle target type, and spawn clients.",
            "color": 0x3498DB,
            "fields": [
                {"name": "👥 Target Profiles", "value": sel_display, "inline": False},
                {"name": "🎯 Target Type", "value": mode_display, "inline": True}
            ],
            "footer": {"text": "Roblox Account Manager | Interactive Join"},
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }

    def _build_interactive_join_components(self, all_accounts, page_index, selected_accounts, mode):
        start = page_index * 25
        end = (page_index + 1) * 25
        chunk = all_accounts[start:end]
        select_options = []
        for acc in chunk:
            is_default = acc in selected_accounts
            select_options.append({
                "label": acc[:100],
                "value": acc[:100],
                "default": is_default
            })
        components = [
            {
                "type": 1,
                "components": [
                    {
                        "type": 3,
                        "custom_id": f"interactive_join_select:{page_index}:{mode}",
                        "placeholder": "Select accounts to join...",
                        "min_values": 0,
                        "max_values": len(select_options),
                        "options": select_options
                    }
                ]
            }
        ]
        nav_buttons = []
        if len(all_accounts) > 25:
            nav_buttons.append({
                "type": 2,
                "style": 2,
                "label": "◀ Prev",
                "custom_id": f"interactive_join_page:prev:{page_index}:{mode}",
                "disabled": page_index == 0
            })
            nav_buttons.append({
                "type": 2,
                "style": 2,
                "label": "Next ▶",
                "custom_id": f"interactive_join_page:next:{page_index}:{mode}",
                "disabled": end >= len(all_accounts)
            })
        action_buttons = [
            {
                "type": 2,
                "style": 2,
                "label": "Toggle Mode",
                "emoji": {"name": "📍"} if mode == "place_id" else {"name": "🔑"},
                "custom_id": f"interactive_join_toggle:{page_index}:{mode}"
            },
            {
                "type": 2,
                "style": 1,
                "label": "Launch Selected",
                "emoji": {"name": "🚀"},
                "custom_id": "interactive_join_launch",
                "disabled": len(selected_accounts) == 0
            }
        ]
        if nav_buttons:
            components.append({
                "type": 1,
                "components": nav_buttons
            })
        components.append({
            "type": 1,
            "components": action_buttons
        })
        return components

    def _build_interactive_kill_embed(self, selected_accounts):
        running = [entry.get("username") for entry in self.ui.instances_data if entry.get("username")]
        run_display = ", ".join(f"**{u}**" for u in running) if running else "*No active player processes detected*"
        sel_display = ", ".join(f"**{acc}**" for acc in selected_accounts) if selected_accounts else "*None selected*"
        return {
            "title": "🛑 Session Termination Panel",
            "description": "Select specific player sessions to force-terminate or perform a global process cleanup.",
            "color": 0xE74C3C,
            "fields": [
                {"name": "👥 Active Roblox Clients", "value": run_display, "inline": False},
                {"name": "🎯 Marked for Termination", "value": sel_display, "inline": False}
            ],
            "footer": {"text": "Roblox Account Manager | Process Management"},
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }

    def _build_interactive_kill_components(self, running_accounts, selected_accounts):
        components = []
        if running_accounts:
            select_options = []
            for acc in running_accounts[:25]:
                is_default = acc in selected_accounts
                select_options.append({
                    "label": acc[:100],
                    "value": acc[:100],
                    "default": is_default
                })
            components.append({
                "type": 1,
                "components": [
                    {
                        "type": 3,
                        "custom_id": "interactive_kill_select",
                        "placeholder": "Select running sessions to close...",
                        "min_values": 0,
                        "max_values": len(select_options),
                        "options": select_options
                    }
                ]
            })
        action_buttons = [
            {
                "type": 2,
                "style": 4,
                "label": "Kill Selected",
                "emoji": {"name": "🛑"},
                "custom_id": "interactive_kill_selected",
                "disabled": len(selected_accounts) == 0
            },
            {
                "type": 2,
                "style": 4,
                "label": "Kill All Sessions",
                "emoji": {"name": "💥"},
                "custom_id": "interactive_kill_all",
                "disabled": len(running_accounts) == 0
            }
        ]
        components.append({
            "type": 1,
            "components": action_buttons
        })
        return components

    async def send_interactive_join(self, interaction_id, interaction_token, preselected=None):
        token = self.ui.settings.get("discord_bot_token", "").strip()
        headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json"
        }
        all_accounts = list(self.ui.manager.accounts.keys())
        selected = preselected if preselected is not None else []
        embed = self._build_interactive_join_embed(selected, "place_id")
        components = self._build_interactive_join_components(all_accounts, 0, selected, "place_id")
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        self._send_callback(url, headers, {
            "type": 4,
            "data": {
                "embeds": [embed],
                "components": components,
                "flags": 64
            }
        })

    async def send_interactive_kill(self, interaction_id, interaction_token):
        token = self.ui.settings.get("discord_bot_token", "").strip()
        headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json"
        }
        running_accounts = [entry.get("username") for entry in self.ui.instances_data if entry.get("username")]
        embed = self._build_interactive_kill_embed([])
        components = self._build_interactive_kill_components(running_accounts, [])
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        self._send_callback(url, headers, {
            "type": 4,
            "data": {
                "embeds": [embed],
                "components": components,
                "flags": 64
            }
        })
