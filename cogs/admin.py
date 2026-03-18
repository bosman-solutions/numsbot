"""
cogs/admin.py — admin slash commands
version: 0.3.3
/burnitall, /botstatus, /redrawplaces
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands
from cogs.places_card import redraw_places

log = logging.getLogger("numsbot.admin")

VERSION = "0.3.3"


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def nb(self):
        return self.bot.nb

    @app_commands.command(name="burnitall", description="(Admin) Hard reset — kills session. Places untouched.")
    async def burnitall(self, interaction: discord.Interaction):
        if interaction.user.id != self.bot.admin_id:
            await interaction.response.send_message("🚫 Admin only.", ephemeral=True)
            return

        session    = self.nb.session
        was_active = session.active
        nom_names  = [n["name"] for n in session.nominations]
        had_timer  = session.timer_task and not session.timer_task.done()

        if session.embed_message_id and session.channel_id:
            try:
                channel = self.bot.get_channel(session.channel_id)
                if channel:
                    msg = await channel.fetch_message(session.embed_message_id)
                    await msg.delete()
            except Exception:
                pass

        if session.thread_id:
            try:
                thread = self.bot.get_channel(session.thread_id)
                if thread:
                    await thread.edit(archived=True)
            except Exception:
                pass

        self.nb.reset_session()

        log.warning(
            f"burnitall by {interaction.user} — "
            f"active={was_active}, noms={nom_names}, timer={had_timer}"
        )

        embed = discord.Embed(title="🔥 burnitall executed", color=discord.Color.red())
        embed.add_field(name="Was active",  value=str(was_active),                                  inline=True)
        embed.add_field(name="Cleared",     value=", ".join(nom_names) if nom_names else "none",    inline=True)
        embed.add_field(name="Timer",       value="cancelled" if had_timer else "was idle",         inline=True)
        embed.add_field(name="places.json", value="untouched ✅",                                   inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="botstatus", description="(Admin) Show current bot state.")
    async def botstatus(self, interaction: discord.Interaction):
        if interaction.user.id != self.bot.admin_id:
            await interaction.response.send_message("🚫 Admin only.", ephemeral=True)
            return

        session = self.nb.session
        embed   = discord.Embed(title="🤖 NumsBot Status", color=discord.Color.blurple())
        embed.add_field(name="Version",        value=VERSION,                               inline=True)
        embed.add_field(name="Session active", value=str(session.active),                   inline=True)
        embed.add_field(name="Locked",         value=str(session.locked),                   inline=True)
        embed.add_field(name="Nominations",    value=str(len(session.nominations)),         inline=True)
        embed.add_field(name="Roll round",     value=str(session.roll_round),               inline=True)
        embed.add_field(name="Known places",   value=str(len(self.nb.active_places())),     inline=True)
        embed.add_field(
            name="Vote channel",
            value=f"<#{self.nb.config.vote_channel_id}>" if self.nb.config.vote_channel_id else "not set — run /setup",
            inline=True,
        )
        embed.add_field(
            name="Places channel",
            value=f"<#{self.nb.config.places_channel_id}>" if self.nb.config.places_channel_id else "not set",
            inline=True,
        )
        embed.add_field(
            name="Timer",
            value="running" if (session.timer_task and not session.timer_task.done()) else "idle",
            inline=True,
        )
        if session.nominations:
            embed.add_field(
                name="Nominees",
                value="\n".join(f"{n['emoji']} {n['name']}" for n in session.nominations),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="redrawplaces", description="(Admin) Force-redraw the #places living card from JSON.")
    async def redrawplaces(self, interaction: discord.Interaction):
        if interaction.user.id != self.bot.admin_id:
            await interaction.response.send_message("🚫 Admin only.", ephemeral=True)
            return

        if not self.nb.config.places_channel_id:
            await interaction.response.send_message("No places channel configured. Run /setup first.", ephemeral=True)
            return

        await interaction.response.send_message("🔄 Redrawing places card...", ephemeral=True)
        self.nb.config.places_message_ids = []
        self.nb.config.save()
        await redraw_places(self.bot)
        await interaction.followup.send("✅ Places card redrawn.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
