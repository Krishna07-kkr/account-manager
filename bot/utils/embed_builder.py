import discord
from datetime import datetime

class EmbedBuilder:
    @staticmethod
    def build_success(title, description, thumbnail_url=None):
        embed = discord.Embed(
            title=f"🟢 {title}",
            description=description,
            color=0x2ECC71,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Roblox Account Manager", icon_url="https://raw.githubusercontent.com/evanovar/RobloxAccountManager/main/icon.ico")
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        return embed

    @staticmethod
    def build_error(title, description):
        embed = discord.Embed(
            title=f"🔴 {title}",
            description=description,
            color=0xE74C3C,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Roblox Account Manager", icon_url="https://raw.githubusercontent.com/evanovar/RobloxAccountManager/main/icon.ico")
        return embed

    @staticmethod
    def build_info(title, description, fields=None, thumbnail_url=None):
        embed = discord.Embed(
            title=f"ℹ️ {title}",
            description=description,
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Roblox Account Manager", icon_url="https://raw.githubusercontent.com/evanovar/RobloxAccountManager/main/icon.ico")
        if fields:
            for name, val, inline in fields:
                embed.add_field(name=name, value=val, inline=inline)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        return embed
