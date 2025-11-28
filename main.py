import os
import discord
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Guild ID for testing (slash commands)
GUILD_ID = os.getenv("GUILD_ID")
guild = discord.Object(id=GUILD_ID)

# Load cogs asynchronously
async def load_cogs():
    for cog in ["cogs.context_archive","cogs.avatar", "cogs.purge"]:
        await bot.load_extension(cog)

# Ready event
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        await bot.tree.sync(guild=guild)  # guild-specific sync
        print("Slash commands synced")
    except discord.Forbidden:
        print("Missing access to sync commands in this guild. Try updating your Guild ID?")


# Async main function
async def main():
    await load_cogs()
    await bot.start(TOKEN)

# Run bot
asyncio.run(main())
