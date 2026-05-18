from . import admin, deployment, telemetry, settings

def get_commands_definition():
    cmds = []
    cmds.extend(admin.get_definitions())
    cmds.extend(deployment.get_definitions())
    cmds.extend(telemetry.get_definitions())
    cmds.extend(settings.get_definitions())
    return cmds

async def handle_interaction(bot, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token):
    if await admin.handle_interaction(bot, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token):
        return True
    if await deployment.handle_interaction(bot, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token):
        return True
    if await telemetry.handle_interaction(bot, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token):
        return True
    if await settings.handle_interaction(bot, command_name, d, token, headers, resolved_app_id, interaction_id, interaction_token):
        return True
    return False
