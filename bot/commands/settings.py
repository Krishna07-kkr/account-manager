import asyncio
import time
import threading
import requests

def get_definitions():
    return [
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
            "name": "validity_check",
            "description": "Check the authentication status and validity of all cookies"
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
            "name": "grab_place_id",
            "description": "Show all saved Roblox game Place IDs"
        },
        {
            "name": "help",
            "description": "Show available remote commands and usage details"
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
            "name": "set",
            "description": "Set global configurations",
            "options": [
                {
                    "name": "fps",
                    "description": "Set the global Roblox framerate cap",
                    "type": 1,
                    "options": [
                        {
                            "type": 4,
                            "name": "value",
                            "description": "The target framerate cap (e.g., 60, 120, 144, 240)",
                            "required": True
                        }
                    ]
                }
            ]
        }
    ]

async def handle_interaction(bot, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token):
    if command_name == "activity_log":
        status = d["data"]["options"][0]["value"]
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        if status == "enable":
            bot.log_mirror_enabled = True
            bot._send_webhook_embed(
                "Console Log Mirroring Enabled",
                "Real-time console log mirroring to Discord has been enabled successfully.",
                0x2ECC71
            )
            bot._send_callback(url, headers, {
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
            bot.log_mirror_enabled = False
            bot._send_webhook_embed(
                "Console Log Mirroring Disabled",
                "Real-time console log mirroring to Discord has been disabled successfully.",
                0xE74C3C
            )
            bot._send_callback(url, headers, {
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
        return True

    elif command_name == "validity_check":
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        bot._send_callback(url, headers, {
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
            all_accounts = list(bot.ui.manager.accounts.keys())
            for acc in all_accounts:
                try:
                    if bot.ui.manager.validate_account(acc):
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
            bot._send_webhook_embed(
                "Roblox Account Session Validity Report",
                "Background authentication verification completed for all registered accounts.",
                color,
                fields=fields
            )
            bot._send_followup(resolved_app_id, interaction_token, {
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
        return True

    elif command_name == "antiafk":
        status = d["data"]["options"][0]["value"]
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        if status == "enable":
            bot.ui.settings["anti_afk_enabled"] = True
            bot.ui.save_settings()
            bot.ui.start_anti_afk()
            bot._send_webhook_embed(
                "RAM Anti-AFK Engine Enabled",
                "RAM's built-in Anti-AFK engine has been programmatically enabled! Connected game clients will no longer time out.",
                0x3498DB
            )
            bot._send_callback(url, headers, {
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
            bot.ui.settings["anti_afk_enabled"] = False
            bot.ui.save_settings()
            bot.ui.stop_anti_afk()
            bot._send_webhook_embed(
                "RAM Anti-AFK Engine Disabled",
                "RAM's built-in Anti-AFK engine has been programmatically disabled! Connected game clients will no longer simulate keystrokes.",
                0x3498DB
            )
            bot._send_callback(url, headers, {
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
        return True

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
        bot.ui.settings[setting] = parsed_val
        bot.ui.save_settings()
        if setting == "anti_afk_enabled":
            if parsed_val:
                bot.ui.start_anti_afk()
            else:
                bot.ui.stop_anti_afk()
        bot._send_webhook_embed(
            "Remote Configuration Update",
            f"Remote Settings Override: set `{setting}` parameter to `{parsed_val}` successfully.",
            0x3498DB
        )
        bot._send_callback(url, headers, {
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
        return True

    elif command_name == "grab_place_id":
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        saved_games = bot.ui.settings.get("game_list", [])
        if not saved_games:
            bot._send_callback(url, headers, {
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
            return True
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
        bot._send_webhook_embed(
            "Saved Roblox Game Place IDs",
            desc,
            0x34495E
        )
        bot._send_callback(url, headers, {
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
        return True

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
        bot._send_webhook_embed(
            "Roblox Account Manager Remote Commands Help Directory",
            help_embed["description"],
            0x34495E
        )
        bot._send_callback(url, headers, {
            "type": 4,
            "data": {
                "embeds": [help_embed],
                "flags": 64
            }
        })
        return True

    elif command_name == "addaccount":
        options = d["data"].get("options", [])
        opts_dict = {o["name"]: o["value"] for o in options}
        method = opts_dict.get("method")
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        if method == "Cookie":
            cookie = opts_dict.get("cookie", "").strip()
            if not cookie:
                bot._send_callback(url, headers, {
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
                return True
            bot._send_callback(url, headers, {
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
                    import re
                    cookies = [c.strip() for c in re.split(r'[\s,\n\r]+', cookie) if c.strip()]
                    success_count = 0
                    failed_count = 0
                    imported_users = []
                    for c in cookies:
                        success, username = bot.ui.manager.import_cookie_account(c)
                        if success:
                            success_count += 1
                            imported_users.append(username)
                        else:
                            failed_count += 1
                    if success_count > 0:
                        desc = f"Successfully imported {success_count} account(s):\n" + "\n".join(f"- {u}" for u in imported_users)
                        if failed_count > 0:
                            desc += f"\n\nFailed to import {failed_count} cookie(s) (invalid or expired)."
                        bot._send_webhook_embed(
                            "Roblox Profiles Imported",
                            desc,
                            0x2ECC71
                        )
                        bot._send_followup(resolved_app_id, interaction_token, {
                            "embeds": [{
                                "title": "✓ Roblox Profiles Imported",
                                "description": desc,
                                "color": 0x2ECC71,
                                "footer": {"text": "Roblox Account Manager | Profile Importer"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        })
                    else:
                        bot._send_webhook_embed(
                            "Profile Import Failed",
                            f"Attempted to import {failed_count} cookie profile(s) but validation failed for all of them.",
                            0xE74C3C
                        )
                        bot._send_followup(resolved_app_id, interaction_token, {
                            "embeds": [{
                                "title": "❌ Profile Import Failed",
                                "description": f"Attempted to import {failed_count} cookie profile(s) but validation failed. The cookies may be invalid or expired.",
                                "color": 0xE74C3C,
                                "footer": {"text": "Roblox Account Manager | Profile Importer"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        })
                except Exception as import_err:
                    bot._send_followup(resolved_app_id, interaction_token, {
                        "embeds": [{
                            "title": "❌ Profile Import Failed",
                            "description": f"An unexpected error occurred while importing:\n```python\n{import_err}\n```",
                            "color": 0xE74C3C,
                            "footer": {"text": "Roblox Account Manager | Profile Importer"},
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        }]
                    })
            threading.Thread(target=run_import, daemon=True).start()
            return True
        else:
            username = opts_dict.get("username", "").strip()
            password = opts_dict.get("password", "").strip()
            if not username or not password:
                bot._send_callback(url, headers, {
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
                return True
            bot._send_callback(url, headers, {
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
                    bot.ui.manager.add_account(amount=1, javascript=js_injection)
                    bot._send_webhook_embed(
                        "Chrome Autofill Spawned",
                        f"Autofill sequence initiated successfully for user **{username}**.",
                        0x3498DB
                    )
                except Exception as selenium_err:
                    bot._send_webhook_embed(
                        "Chrome Autofill Spawn Failed",
                        f"Autofill sequence failed for user **{username}**: {selenium_err}",
                        0xE74C3C
                    )
            threading.Thread(target=run_selenium, daemon=True).start()
            return True

    elif command_name == "set":
        options = d["data"].get("options", [])
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        if options and options[0]["name"] == "fps":
            sub_options = options[0].get("options", [])
            if sub_options and sub_options[0]["name"] == "value":
                fps_cap = int(sub_options[0]["value"])
                from classes.roblox_api import RobloxAPI
                
                def run_fps_set():
                    success = RobloxAPI.set_xml_framerate_cap(fps_cap)
                    if success:
                        bot._send_webhook_embed(
                            "Roblox Framerate Cap Updated",
                            f"Programmatically set Roblox global FramerateCap to `{fps_cap}` FPS.",
                            0x2ECC71
                        )
                        bot._send_followup(resolved_app_id, interaction_token, {
                            "embeds": [{
                                "title": "✓ Roblox Framerate Cap Updated",
                                "description": f"Roblox global framerate cap has been successfully set to **{fps_cap}** FPS in `GlobalBasicSettings_13.xml`.",
                                "color": 0x2ECC71,
                                "footer": {"text": "Roblox Account Manager | Settings Override"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        })
                    else:
                        bot._send_followup(resolved_app_id, interaction_token, {
                            "embeds": [{
                                "title": "❌ Framerate Cap Update Failed",
                                "description": "Failed to modify `GlobalBasicSettings_13.xml`. See console logs for details.",
                                "color": 0xE74C3C,
                                "footer": {"text": "Roblox Account Manager | Settings Override"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        })
                
                # Acknowledge the interaction first
                bot._send_callback(url, headers, {
                    "type": 4,
                    "data": {
                        "embeds": [{
                            "title": "⚙️ Modifying Roblox Settings",
                            "description": f"Setting Roblox global FramerateCap to `{fps_cap}` FPS...",
                            "color": 0xF1C40F,
                            "footer": {"text": "Roblox Account Manager | Settings Override"}
                        }]
                    }
                })
                
                threading.Thread(target=run_fps_set, daemon=True).start()
                return True
        return False

    return False
