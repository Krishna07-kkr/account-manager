import asyncio
import json
import time
import threading

def get_definitions():
    return [
        {
            "name": "accounts",
            "description": "Select accounts to launch Roblox",
            "options": [
                {"type": 3, "name": "place_id", "description": "The Roblox Place ID to join", "required": False},
                {"type": 3, "name": "private_server", "description": "Private server Link or Code", "required": False}
            ]
        },
        {
            "name": "list_join",
            "description": "Interactive list to select accounts, then enter place ID to launch"
        },
        {
            "name": "join_all",
            "description": "Sequential-launch all available accounts into Roblox",
            "options": [
                {"type": 3, "name": "place_id", "description": "The Roblox Place ID to join", "required": False},
                {"type": 3, "name": "private_server", "description": "Private server Link or Code", "required": False}
            ]
        },
        {
            "name": "join",
            "description": "Launch accounts into Roblox game Place ID",
            "options": [
                {"type": 3, "name": "target", "description": "Specify 'all' to launch all accounts, or enter a specific Roblox username", "required": False},
                {"type": 3, "name": "place_id", "description": "The Roblox Place ID to join", "required": False},
                {"type": 3, "name": "private_server", "description": "Private server Link or Code", "required": False}
            ]
        },
        {
            "name": "launch",
            "description": "Launch accounts into Roblox game Place ID",
            "options": [
                {"type": 3, "name": "target", "description": "Specify 'all' to launch all accounts, or enter a specific Roblox username", "required": False},
                {"type": 3, "name": "place_id", "description": "The Roblox Place ID to join", "required": False},
                {"type": 3, "name": "private_server", "description": "Private server Link or Code", "required": False}
            ]
        }
    ]

async def _run_batch_join_task(bot, resolved_app_id, interaction_token, all_accounts, place_id, private_server, target_display):
    launcher_pref, custom_launcher_path = bot.ui._get_roblox_launcher_config()
    success_count = 0
    fail_count = 0
    for account_name in all_accounts:
        try:
            bot.ui.manager.launch_roblox(
                username=account_name,
                game_id=place_id,
                private_server_id=private_server,
                launcher_preference=launcher_pref,
                custom_launcher_path=custom_launcher_path
            )
            success_count += 1
            bot._send_webhook_embed(
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
            bot._send_webhook_embed(
                "Launch Failure",
                f"Profile **{account_name}** failed to launch.",
                0xE74C3C,
                fields=[
                    {"name": "👤 Account", "value": f"**{account_name}**", "inline": True},
                    {"name": "❌ Error Detail", "value": f"```{e}```", "inline": False}
                ]
            )
        await asyncio.sleep(0.01)
    bot._send_webhook_embed(
        "Launch Sequence Completed",
        "Finished staggered launch process.",
        0x2ECC71,
        fields=[
            {"name": "🟢 Launched Successfully", "value": f"**{success_count}** accounts", "inline": True},
            {"name": "🔴 Failed to Launch", "value": f"**{fail_count}** accounts", "inline": True}
        ]
    )
    bot._send_followup(resolved_app_id, interaction_token, {
        "embeds": [{
            "title": "🚀 Staggered Join Sequence Completed",
            "description": f"Finished staggered launch process for all **{len(all_accounts)}** accounts into {target_display}.",
            "color": 0x2ECC71,
            "fields": [
                {"name": "🟢 Launched Successfully", "value": f"**{success_count}**", "inline": True},
                {"name": "🔴 Failed to Launch", "value": f"**{fail_count}**", "inline": True}
            ],
            "footer": {"text": "Roblox Account Manager | Batch Launcher"},
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }]
    })

async def handle_interaction(bot, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token):
    if command_name == "accounts":
        options = {o["name"]: o["value"] for o in d["data"].get("options", [])}
        place_id = options.get("place_id", "").strip()
        private_server = options.get("private_server", "").strip()
        await send_paginated_accounts(bot, interaction_id, interaction_token, place_id, private_server, 0, headers)
        return True

    if command_name == "list_join":
        await send_paginated_list_join(bot, interaction_id, interaction_token, 0, headers)
        return True

    if command_name == "join_all":
        options = {o["name"]: o["value"] for o in d["data"].get("options", [])}
        place_id = options.get("place_id", "").strip()
        private_server = options.get("private_server", "").strip()
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        if not place_id and not private_server:
            bot._send_callback(url, headers, {
                "type": 4,
                "data": {"content": "[ERROR] You must specify either a Roblox Place ID or a Private Server Link/Code.", "flags": 64}
            })
            return True
        target_display = f"Place ID `{place_id}`" if place_id else f"Private Server `{private_server}`"
        bot._send_webhook_embed(
            "Launch Sequence Initiated",
            "Programmatic batch launch sequence initiated.",
            0x95A5A6,
            fields=[
                {"name": "👥 Accounts", "value": "**ALL** registered profiles", "inline": True},
                {"name": "📍 Destination", "value": f"`{place_id or private_server}`", "inline": True}
            ]
        )
        bot._send_callback(url, headers, {
            "type": 4,
            "data": {
                "embeds": [{
                    "title": "🚀 Staggered Join Sequence Initiated",
                    "description": f"Programmatic batch launch sequence started to launch **ALL** registered profiles into {target_display}.",
                    "color": 0xF1C40F,
                    "footer": {"text": "Roblox Account Manager | Launcher"}
                }]
            }
        })
        asyncio.create_task(_run_batch_join_task(
            bot, resolved_app_id, interaction_token,
            list(bot.ui.manager.accounts.keys()), place_id, private_server, target_display
        ))
        return True

    if command_name in ("join", "launch"):
        options = {o["name"]: o["value"] for o in d["data"].get("options", [])}
        target = options.get("target", "").strip()
        place_id = options.get("place_id", "").strip()
        private_server = options.get("private_server", "").strip()
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"

        if not place_id and not private_server:
            preselected = [target] if (target and target.lower() != "all" and target in bot.ui.manager.accounts) else None
            await bot.send_interactive_join(interaction_id, interaction_token, preselected)
            return True

        if target.lower() == "all":
            target_display = f"Place ID `{place_id}`" if place_id else f"Private Server `{private_server}`"
            bot._send_callback(url, headers, {
                "type": 4,
                "data": {
                    "embeds": [{
                        "title": "🚀 Staggered Join Sequence Initiated",
                        "description": "Programmatic batch launch sequence started to launch **ALL** profiles.",
                        "color": 0xF1C40F,
                        "footer": {"text": "Roblox Account Manager | Launcher"}
                    }]
                }
            })
            bot._send_webhook_embed(
                "Launch Sequence Initiated",
                "Batch launch sequence started.",
                0x95A5A6,
                fields=[
                    {"name": "👥 Accounts", "value": "**ALL** registered profiles", "inline": True},
                    {"name": "📍 Destination", "value": f"`{place_id or private_server}`", "inline": True}
                ]
            )
            asyncio.create_task(_run_batch_join_task(
                bot, resolved_app_id, interaction_token,
                list(bot.ui.manager.accounts.keys()), place_id, private_server, target_display
            ))
        elif target in bot.ui.manager.accounts:
            bot._send_callback(url, headers, {
                "type": 4,
                "data": {
                    "embeds": [{
                        "title": "🚀 Spawning Game Session",
                        "description": f"Launching Roblox player client for account **{target}**...",
                        "color": 0xF1C40F,
                        "footer": {"text": "Roblox Account Manager | Launcher"}
                    }]
                }
            })
            launcher_pref, custom_launcher_path = bot.ui._get_roblox_launcher_config()
            def run_single():
                try:
                    bot.ui.manager.launch_roblox(
                        username=target,
                        game_id=place_id,
                        private_server_id=private_server,
                        launcher_preference=launcher_pref,
                        custom_launcher_path=custom_launcher_path
                    )
                    bot._send_webhook_embed(
                        "Launch Successful",
                        "Account launched successfully.",
                        0x2ECC71,
                        fields=[
                            {"name": "👤 Account", "value": f"**{target}**", "inline": True},
                            {"name": "📍 Destination", "value": f"`{place_id or private_server}`", "inline": True}
                        ]
                    )
                    bot._send_followup(resolved_app_id, interaction_token, {
                        "embeds": [{
                            "title": "🚀 Launch Sequence Completed",
                            "description": f"Roblox account **{target}** successfully deployed.",
                            "color": 0x2ECC71,
                            "fields": [
                                {"name": "👤 Account", "value": f"**{target}**", "inline": True},
                                {"name": "📍 Target", "value": f"`{place_id or private_server}`", "inline": True}
                            ],
                            "footer": {"text": "Roblox Account Manager | Launcher"},
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        }]
                    })
                except Exception as e:
                    bot._send_webhook_embed(
                        "Launch Failure",
                        "Launch sequence failed.",
                        0xE74C3C,
                        fields=[
                            {"name": "👤 Account", "value": f"**{target}**", "inline": True},
                            {"name": "❌ Error Detail", "value": f"```{e}```", "inline": False}
                        ]
                    )
                    bot._send_followup(resolved_app_id, interaction_token, {
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
            bot._send_callback(url, headers, {
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
        return True

    return False

async def send_paginated_accounts(bot, interaction_id, interaction_token, place_id, private_server, page_index, headers):
    all_accounts = list(bot.ui.manager.accounts.keys())
    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
    if not all_accounts:
        bot._send_callback(url, headers, {
            "type": 4,
            "data": {"content": "No Roblox accounts found in the application.", "flags": 64}
        })
        return
    select_options = [{"label": acc[:100], "value": acc[:100]} for acc in all_accounts[page_index*25:(page_index+1)*25]]
    components = [{
        "type": 1,
        "components": [{
            "type": 3,
            "custom_id": f"launch_select:{place_id}:{private_server}",
            "placeholder": "Select accounts...",
            "min_values": 1,
            "max_values": min(25, len(select_options)),
            "options": select_options
        }]
    }]
    if len(all_accounts) > 25:
        components.append({
            "type": 1,
            "components": [
                {"type": 2, "style": 2, "label": "◀ Prev", "custom_id": f"bot_page:prev:{place_id}:{private_server}:{page_index}", "disabled": page_index == 0},
                {"type": 2, "style": 2, "label": "Next ▶", "custom_id": f"bot_page:next:{place_id}:{private_server}:{page_index}", "disabled": (page_index+1)*25 >= len(all_accounts)}
            ]
        })
    target_display = f"Place ID `{place_id}`" if place_id else f"Private Server `{private_server}`"
    bot._send_callback(url, headers, {
        "type": 4,
        "data": {
            "content": f"Select the Roblox accounts you want to launch into {target_display} (Page {page_index + 1}):",
            "components": components,
            "flags": 64
        }
    })

async def send_paginated_list_join(bot, interaction_id, interaction_token, page_index, headers):
    all_accounts = list(bot.ui.manager.accounts.keys())
    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
    if not all_accounts:
        bot._send_callback(url, headers, {
            "type": 4,
            "data": {"content": "No Roblox accounts found registered in the application.", "flags": 64}
        })
        return
    select_options = [{"label": acc[:100], "value": acc[:100]} for acc in all_accounts[page_index*25:(page_index+1)*25]]
    components = [{
        "type": 1,
        "components": [{
            "type": 3,
            "custom_id": "list_join_select:",
            "placeholder": "Select accounts to join...",
            "min_values": 1,
            "max_values": min(25, len(select_options)),
            "options": select_options
        }]
    }]
    if len(all_accounts) > 25:
        components.append({
            "type": 1,
            "components": [
                {"type": 2, "style": 2, "label": "◀ Prev", "custom_id": f"list_join_page:prev:{page_index}", "disabled": page_index == 0},
                {"type": 2, "style": 2, "label": "Next ▶", "custom_id": f"list_join_page:next:{page_index}", "disabled": (page_index+1)*25 >= len(all_accounts)}
            ]
        })
    bot._send_callback(url, headers, {
        "type": 4,
        "data": {
            "content": f"Select the Roblox accounts you want to launch (Page {page_index + 1}):",
            "components": components,
            "flags": 64
        }
    })
