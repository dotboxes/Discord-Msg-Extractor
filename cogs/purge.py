import os
import discord
from discord import app_commands
from discord.ext import commands

GUILD_ID = os.getenv("GUILD_ID")
ALLOWED_ROLE_ID = int(os.getenv("PURGE_ROLE_ID", 0))
guild = discord.Object(id=GUILD_ID)


class PurgeConfirmView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, messages: list[discord.Message], label: str):
        super().__init__(timeout=30)
        self.channel = channel
        self.messages = messages  # Pre-resolved list of messages to delete
        self.label = label
        self.message = None

    async def on_timeout(self):
        if self.message:
            await self.message.edit(content="⌛ Purge cancelled (no response).", view=None)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="⏳ Purging messages...", view=None)
        try:
            deleted = await self.channel.delete_messages(self.messages)
            await interaction.edit_original_response(
                content=f"✅ Successfully deleted {len(self.messages)} message(s).", view=None
            )
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Failed to purge messages: {e}", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Purge cancelled.", view=None)
        self.stop()


class Purge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="purge", description="Delete messages from this channel")
    @app_commands.describe(
        amount="Number of messages to delete (1-25). Ignored if depth is set.",
        depth="Delete the single message N positions above this command (1 = message just above)."
    )
    async def purge(self, interaction: discord.Interaction, amount: int = None, depth: int = None):
        # --- Permission checks ---
        if not interaction.user.guild_permissions.administrator:
            if ALLOWED_ROLE_ID not in [role.id for role in interaction.user.roles]:
                await interaction.response.send_message(
                    "❌ You do not have permission to use this command.", ephemeral=True
                )
                return

        if not interaction.channel.permissions_for(interaction.guild.me).manage_messages:
            await interaction.response.send_message(
                "❌ I do not have permission to manage messages in this channel.", ephemeral=True
            )
            return

        # --- Depth mode ---
        if depth is not None:
            if depth < 1 or depth > 100:
                await interaction.response.send_message(
                    "❌ Depth must be between 1 and 100.", ephemeral=True
                )
                return

            fetch_limit = max(depth, amount) if amount else depth
            history = [msg async for msg in interaction.channel.history(limit=fetch_limit)]

            if len(history) < depth:
                await interaction.response.send_message(
                    f"❌ Not enough messages in this channel to reach depth {depth}.", ephemeral=True
                )
                return

            if amount:
                messages_to_delete = history[depth - 1: depth - 1 + amount]
                confirm_text = f"⚠️ Delete **{len(messages_to_delete)}** message(s) starting at depth **{depth}**?"
            else:
                messages_to_delete = [history[depth - 1]]
                target = messages_to_delete[0]
                preview = target.content[:60] + ("..." if len(target.content) > 60 else "")
                preview = preview or "[no text content]"
                confirm_text = f"⚠️ Delete message at depth **{depth}** by **{target.author.display_name}**?\n> {preview}"

            view = PurgeConfirmView(interaction.channel, messages_to_delete, label="depth")
            await interaction.response.send_message(confirm_text, view=view, ephemeral=True)
            view.message = await interaction.original_response()
            return

        # --- Amount mode ---
        if amount < 1 or amount > 25:
            await interaction.response.send_message("❌ Amount must be between 1 and 25.", ephemeral=True)
            return

        history = [msg async for msg in interaction.channel.history(limit=amount)]
        view = PurgeConfirmView(interaction.channel, history, label="amount")
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to delete the **{amount}** most recent message(s)?",
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()


async def setup(bot):
    cog = Purge(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.purge, guild=guild)