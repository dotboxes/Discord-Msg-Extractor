import os

import discord
from discord import app_commands
from discord.ext import commands
import aiohttp


GUILD_ID = os.getenv("GUILD_ID")
guild = discord.Object(id=GUILD_ID)


class Avatar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Slash command to change bot avatar
    @app_commands.command(
        name="avatar",
        description="Change the bot's avatar"
    )
    @app_commands.describe(
        url="URL of the new avatar image (optional)",
        file="Upload an image file (optional)"
    )
    async def change_avatar(
        self,
        interaction: discord.Interaction,
        url: str = None,
        file: discord.Attachment = None
    ):
        if not url and not file:
            await interaction.response.send_message(
                "❌ You must provide either a URL or upload a file.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)  # in case it takes time to download

        try:
            if file:
                data = await file.read()
            else:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            await interaction.followup.send(
                                "❌ Failed to fetch the image from URL.", ephemeral=True
                            )
                            return
                        data = await resp.read()

            await self.bot.user.edit(avatar=data)
            await interaction.followup.send("✅ Avatar changed successfully!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to change avatar: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    cog = Avatar(bot)
    await bot.add_cog(cog)
    # Register slash commands in the guild
    guild = discord.Object(id=GUILD_ID)
    bot.tree.add_command(cog.change_avatar, guild=guild)
