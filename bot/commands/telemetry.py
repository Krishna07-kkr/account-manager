import asyncio
import time
import threading
import requests
import psutil

def get_definitions():
    return [
        {
            "name": "status",
            "description": "Get real-time performance snapshot of all active sessions"
        },
        {
            "name": "list",
            "description": "Get a checklist summary of all accounts stored inside RAM"
        },
        {
            "name": "active_accounts",
            "description": "Show all currently active online Roblox accounts"
        },
        {
            "name": "resource",
            "description": "Get current system RAM and CPU usage statistics"
        },
        {
            "name": "summary",
            "description": "Displays detailed visual summary, tracking data, and dynamic uptimes for all accounts"
        }
    ]

async def handle_interaction(bot, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token):
    if command_name == "status":
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        active_sessions = list(bot.ui.instances_data)
        if not active_sessions:
            bot._send_callback(url, headers, {
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
            return True
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
        bot._send_webhook_embed(
            "Roblox Account Manager Performance Dashboard",
            "Live metrics and performance snapshot of all active Roblox game client sessions.",
            0x2ECC71,
            fields=fields
        )
        bot._send_callback(url, headers, {
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
        return True

    elif command_name == "list":
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        all_accounts = list(bot.ui.manager.accounts.keys())
        if not all_accounts:
            bot._send_callback(url, headers, {
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
            return True
        fields = []
        chunk_size = 15
        for i in range(0, len(all_accounts), chunk_size):
            chunk = all_accounts[i:i+chunk_size]
            fields.append({
                "name": f"Profiles {i+1} - {min(i+chunk_size, len(all_accounts))}",
                "value": "\n".join(f"• **{acc}**" for acc in chunk),
                "inline": True
            })
        bot._send_webhook_embed(
            "Roblox Account Manager Saved Profiles Directory",
            f"Complete catalog index of all registered account profiles inside Roblox Account Manager (Total: **{len(all_accounts)}**).",
            0x34495E,
            fields=fields
        )
        bot._send_callback(url, headers, {
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
        return True

    elif command_name == "active_accounts":
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        active_sessions = list(bot.ui.instances_data)
        if not active_sessions:
            bot._send_callback(url, headers, {
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
            return True
        fields = []
        for idx, entry in enumerate(active_sessions):
            fields.append({
                "name": f"{idx + 1}. {entry.get('username', 'Unknown')}",
                "value": f"PID: `{entry.get('pid')}` | Place ID: `{entry.get('place_id', 'Unknown')}`",
                "inline": True
            })
        bot._send_webhook_embed(
            "Live Active Online Roblox Accounts",
            f"Directory of all Roblox accounts currently online and active inside client windows (Total: **{len(active_sessions)}**).",
            0x1ABC9C,
            fields=fields
        )
        bot._send_callback(url, headers, {
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
        return True

    elif command_name == "resource":
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        cpu_percent = 0.0
        total_gb, used_gb, free_gb, mem_percent = 0.0, 0.0, 0.0, 0.0
        try:
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
        bot._send_webhook_embed(
            "System Resource Statistics Report",
            "Real-time physical hardware metrics from the host computer.",
            0x9B59B6,
            fields=fields
        )
        bot._send_callback(url, headers, {
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
        return True

    elif command_name == "summary":
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        bot._send_callback(url, headers, {
            "type": 5,
            "data": {"flags": 64}
        })
        def run_summary_worker():
            try:
                summaries = bot.ui.summary_service.get_all_summaries()
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
        return True

    return False
