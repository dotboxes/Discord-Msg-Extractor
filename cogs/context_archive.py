import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from bot.processors import process_archive

load_dotenv()

GUILD_ID = int(os.getenv("GUILD_ID", "0"))
guild = discord.Object(id=GUILD_ID)


@app_commands.context_menu(name="Archive Message")
async def archive_message(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(ephemeral=True)
    await process_archive(interaction, message)


async def setup(bot: commands.Bot):
    bot.tree.add_command(archive_message, guild=guild)