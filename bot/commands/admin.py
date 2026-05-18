import asyncio
import json
import os
import subprocess
import time
import threading
import psutil
import ctypes

def get_definitions():
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
            "name": "kill_all",
            "description": "Terminate all active Roblox player tab sessions instantly"
        }
    ]

async def handle_interaction(bot, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token):
    if command_name == "admin_abuse":
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        bot._send_callback(url, headers, {"type": 5})
        options = {o["name"]: o["value"] for o in d["data"].get("options", [])}
        fps_cap = int(options.get("fps_cap"))
        place_id = str(options.get("place_id")).strip()
        launch_delay = int(options.get("launch_delay"))
        def run_admin_abuse():
            try:
                terminated_count = 0
                for proc in psutil.process_iter(['name']):
                    try:
                        if proc.info['name'] and proc.info['name'].lower() in ('robloxplayerbeta.exe', 'robloxplayerlauncher.exe'):
                            proc.terminate()
                            terminated_count += 1
                    except:
                        pass
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
                all_accounts = list(bot.ui.manager.accounts.keys())
                launcher_pref, custom_launcher_path = bot.ui._get_roblox_launcher_config()
                bot._send_webhook_embed(
                    "Admin Abuse Execution Started",
                    f"Terminated {terminated_count} active Roblox clients. Target FPS cap set to **{fps_cap}**. Commencing sequential launch of **{len(all_accounts)}** accounts into Place ID `{place_id}` with **{launch_delay}s** delay.",
                    0x95A5A6
                )
                for idx, account_name in enumerate(all_accounts):
                    try:
                        bot.ui.manager.launch_roblox(
                            username=account_name,
                            game_id=place_id,
                            launcher_preference=launcher_pref,
                            custom_launcher_path=custom_launcher_path
                        )
                        bot._send_webhook_embed(
                            "Admin Abuse Launch Success",
                            f"Account **{account_name}** successfully deployed.",
                            0x2ECC71
                        )
                    except Exception as le:
                        bot._send_webhook_embed(
                            "Admin Abuse Launch Failure",
                            f"Account **{account_name}** deployment failed: {le}",
                            0xE74C3C
                        )
                    if idx < len(all_accounts) - 1:
                        time.sleep(launch_delay)
                bot._send_webhook_embed(
                    "Admin Abuse Execution Completed",
                    f"Sequential deployment of all **{len(all_accounts)}** accounts completed successfully.",
                    0x2ECC71
                )
                bot._send_followup(resolved_app_id, interaction_token, {
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
                bot._send_followup(resolved_app_id, interaction_token, {
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
        return True

    elif command_name == "free_memory":
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        bot._send_callback(url, headers, {"type": 5})
        def run_free_memory():
            try:
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
                bot._send_webhook_embed(
                    "RAM Optimization Completed",
                    f"Flushed memory pages for **{count}** active Roblox game client processes successfully. (Failed/Access Denied: **{failed_count}**)",
                    0x2ECC71
                )
                bot._send_followup(resolved_app_id, interaction_token, {
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
                bot._send_followup(resolved_app_id, interaction_token, {
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
        return True

    elif command_name == "kill":
        target = d["data"]["options"][0]["value"].strip()
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        if target.lower() in ("ram", "all"):
            bot._send_callback(url, headers, {
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
            active_sessions = list(bot.ui.instances_data)
            count = 0
            for entry in active_sessions:
                pid = entry.get("pid")
                if pid:
                    try:
                        subprocess.run(['taskkill', '/F', '/PID', str(pid)], creationflags=subprocess.CREATE_NO_WINDOW)
                        count += 1
                    except:
                        pass
            bot._send_webhook_embed(
                "Roblox Instances Force-Closed",
                f"Force-closed all active Roblox game client sessions (Closed tabs: **{count}**). Physical memory (RAM) has been flushed.",
                0xE74C3C
            )
            bot._send_followup(resolved_app_id, interaction_token, {
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
            for entry in list(bot.ui.instances_data):
                if entry.get("username") == target:
                    resolved_pid = entry.get("pid")
                    break
            if resolved_pid:
                bot._send_callback(url, headers, {
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
                        proc = psutil.Process(resolved_pid)
                        proc.terminate()
                    except:
                        pass
                    bot._send_webhook_embed(
                        "Roblox Instance Terminated",
                        f"Roblox game client session for account **{target}** (PID: `{resolved_pid}`) force-closed successfully.",
                        0xE74C3C
                    )
                    bot._send_followup(resolved_app_id, interaction_token, {
                        "embeds": [{
                            "title": "💥 Session Terminated",
                            "description": f"Roblox game client session for account **{target}** (PID: `{resolved_pid}`) force-closed successfully.",
                            "color": 0xE74C3C,
                            "footer": {"text": "Roblox Account Manager | Process Management"},
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        }]
                    })
                except Exception as e:
                    bot._send_followup(resolved_app_id, interaction_token, {
                        "embeds": [{
                            "title": "❌ Session Termination Failed",
                            "description": f"Failed to terminate session for account **{target}**:\n```python\n{e}\n```",
                            "color": 0xE74C3C,
                            "footer": {"text": "Roblox Account Manager | Process Management"},
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        }]
                    })
            else:
                bot._send_callback(url, headers, {
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
        return True

    elif command_name == "kill_all":
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        bot._send_callback(url, headers, {
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
        active_sessions = list(bot.ui.instances_data)
        count = 0
        for entry in active_sessions:
            pid = entry.get("pid")
            if pid:
                try:
                    subprocess.run(['taskkill', '/F', '/PID', str(pid)], creationflags=subprocess.CREATE_NO_WINDOW)
                    count += 1
                except:
                    pass
        bot._send_webhook_embed(
            "Roblox Instances Force-Closed",
            f"Force-closed all active Roblox game client sessions (Closed tabs: **{count}**). Physical memory (RAM) has been flushed.",
            0xE74C3C
        )
        bot._send_followup(resolved_app_id, interaction_token, {
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
        return True

    return False
