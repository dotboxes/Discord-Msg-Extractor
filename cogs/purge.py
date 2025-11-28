import os
import discord
from discord import app_commands
from discord.ext import commands

GUILD_ID = os.getenv("GUILD_ID")
ALLOWED_ROLE_ID = int(os.getenv("PURGE_ROLE_ID", 0))  # Role ID from .env
guild = discord.Object(id=GUILD_ID)


class PurgeConfirmView(discord.ui.View):
    def __init__(self, amount: int, channel: discord.TextChannel):
        super().__init__(timeout=30)
        self.amount = amount
        self.channel = channel
        self.message = None  # store the original message

    async def on_timeout(self):
        if self.message:
            await self.message.edit(content="⌛ Purge cancelled (no response).", view=None)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Immediately remove buttons to prevent spam
        await interaction.response.edit_message(content="⏳ Purging messages...", view=None)
        try:
            deleted = await self.channel.purge(limit=self.amount)
            # Edit same message to show success
            await interaction.edit_original_response(content=f"✅ Successfully deleted {len(deleted)} messages.", view=None)
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Failed to purge messages: {e}", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Immediately remove buttons
        await interaction.response.edit_message(content="❌ Purge cancelled.", view=None)
        self.stop()


class Purge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="purge", description="Delete messages from this channel")
    @app_commands.describe(amount="Number of messages to delete (1-25)")
    async def purge(self, interaction: discord.Interaction, amount: int):
        # Admin bypass / role check
        if not interaction.user.guild_permissions.administrator:
            if ALLOWED_ROLE_ID not in [role.id for role in interaction.user.roles]:
                await interaction.response.send_message(
                    "❌ You do not have permission to use this command.", ephemeral=True
                )
                return

        # Bot permission check
        if not interaction.channel.permissions_for(interaction.guild.me).manage_messages:
            await interaction.response.send_message(
                "❌ I do not have permission to manage messages in this channel.", ephemeral=True
            )
            return

        # Amount check
        if amount < 1 or amount > 25:
            await interaction.response.send_message("❌ Amount must be between 1 and 25.", ephemeral=True)
            return

        # Send confirmation buttons
        view = PurgeConfirmView(amount, interaction.channel)
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to delete {amount} messages?", view=view, ephemeral=True
        )


async def setup(bot):
    cog = Purge(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.purge, guild=guild)
