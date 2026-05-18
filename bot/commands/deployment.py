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
        }
    ]

async def handle_interaction(bot, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token):
    if command_name == "accounts":
        place_id = d["data"]["options"][0]["value"]
        await send_paginated_accounts(bot, interaction_id, interaction_token, place_id, 0, headers)
        return True

    elif command_name == "list_join":
        await send_paginated_list_join(bot, interaction_id, interaction_token, 0, headers)
        return True

    elif command_name == "join_all":
        place_id = d["data"]["options"][0]["value"].strip()
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        bot._send_webhook_embed(
            "Launch Sequence Initiated",
            f"Programmatic batch launch sequence initiated for **ALL** accounts into Place ID `{place_id}`.",
            0x95A5A6
        )
        bot._send_callback(url, headers, {
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
        launcher_pref, custom_launcher_path = bot.ui._get_roblox_launcher_config()
        all_accounts = list(bot.ui.manager.accounts.keys())
        async def run_batch_join():
            for account_name in all_accounts:
                try:
                    bot.ui.manager.launch_roblox(
                        username=account_name,
                        game_id=place_id,
                        launcher_preference=launcher_pref,
                        custom_launcher_path=custom_launcher_path
                    )
                    bot._send_webhook_embed(
                        "Launch Successful",
                        f"Staggered launch sequence successful for account **{account_name}**.",
                        0x2ECC71
                    )
                except Exception as e:
                    bot._send_webhook_embed(
                        "Launch Failure",
                        f"Staggered launch sequence failed for account **{account_name}**: {e}",
                        0xE74C3C
                    )
                await asyncio.sleep(0.01)
            bot._send_webhook_embed(
                "Launch Sequence Completed",
                f"Finished staggered launch process for all **{len(all_accounts)}** accounts into Place ID `{place_id}`.",
                0x2ECC71
            )
            bot._send_followup(resolved_app_id, interaction_token, {
                "embeds": [{
                    "title": "🚀 Staggered Join Sequence Completed",
                    "description": f"Finished staggered launch process for all **{len(all_accounts)}** accounts into Place ID `{place_id}`.",
                    "color": 0x2ECC71,
                    "footer": {"text": "Roblox Account Manager | Batch Launcher"},
                    "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                }]
            })
        asyncio.create_task(run_batch_join())
        return True

    elif command_name == "join":
        target = d["data"]["options"][0]["value"].strip()
        place_id = d["data"]["options"][1]["value"].strip()
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        if target.lower() == "all":
            bot._send_callback(url, headers, {
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
            bot._send_webhook_embed(
                "Launch Sequence Initiated",
                f"Programmatic batch launch sequence initiated for **ALL** accounts into Place ID `{place_id}`.",
                0x95A5A6
            )
            launcher_pref, custom_launcher_path = bot.ui._get_roblox_launcher_config()
            all_accounts = list(bot.ui.manager.accounts.keys())
            async def run_batch_join():
                for account_name in all_accounts:
                    try:
                        bot.ui.manager.launch_roblox(
                            username=account_name,
                            game_id=place_id,
                            launcher_preference=launcher_pref,
                            custom_launcher_path=custom_launcher_path
                        )
                        bot._send_webhook_embed(
                            "Launch Successful",
                            f"Staggered launch sequence successful for account **{account_name}**.",
                            0x2ECC71
                        )
                    except Exception as e:
                        bot._send_webhook_embed(
                            "Launch Failure",
                            f"Staggered launch sequence failed for account **{account_name}**: {e}",
                            0xE74C3C
                        )
                    await asyncio.sleep(0.01)
                bot._send_webhook_embed(
                    "Launch Sequence Completed",
                    f"Finished staggered launch process for all **{len(all_accounts)}** accounts into Place ID `{place_id}`.",
                    0x2ECC71
                )
                bot._send_followup(resolved_app_id, interaction_token, {
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
            if target in bot.ui.manager.accounts:
                bot._send_callback(url, headers, {
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
                launcher_pref, custom_launcher_path = bot.ui._get_roblox_launcher_config()
                def run_single():
                    try:
                        bot.ui.manager.launch_roblox(
                            username=target,
                            game_id=place_id,
                            launcher_preference=launcher_pref,
                            custom_launcher_path=custom_launcher_path
                        )
                        bot._send_webhook_embed(
                            "Launch Successful",
                            f"Roblox account **{target}** launched successfully into Place ID `{place_id}`.",
                            0x2ECC71
                        )
                        bot._send_followup(resolved_app_id, interaction_token, {
                            "embeds": [{
                                "title": "🚀 Launch Sequence Completed",
                                "description": f"Roblox account **{target}** successfully deployed into Experience ID `{place_id}`.",
                                "color": 0x2ECC71,
                                "footer": {"text": "Roblox Account Manager | Launcher"},
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                            }]
                        })
                    except Exception as e:
                        bot._send_webhook_embed(
                            "Launch Failure",
                            f"Launch sequence failed for account **{target}**: {e}",
                            0xE74C3C
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

async def send_paginated_accounts(bot, interaction_id, interaction_token, place_id, page_index, headers):
    all_accounts = list(bot.ui.manager.accounts.keys())
    if not all_accounts:
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        bot._send_callback(url, headers, {
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
    bot._send_callback(url, headers, {
        "type": 4,
        "data": {
            "content": f"Select the Roblox accounts you want to launch into Place ID `{place_id}` (Page {page_index + 1}):",
            "components": components,
            "flags": 64
        }
    })

async def send_paginated_list_join(bot, interaction_id, interaction_token, page_index, headers):
    all_accounts = list(bot.ui.manager.accounts.keys())
    if not all_accounts:
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        bot._send_callback(url, headers, {
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
    bot._send_callback(url, headers, {
        "type": 4,
        "data": {
            "content": f"Select the Roblox accounts you want to launch (Page {page_index + 1}):",
            "components": components,
            "flags": 64
        }
    })
