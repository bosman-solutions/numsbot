"""
cogs/setup.py — /setup command
version: 0.3.2
Creates #vote-cards and #places, configures permissions, posts living cards.
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands
from cogs.places_card import redraw_places, build_page_embed

log = logging.getLogger("numsbot.setup")

VOTE_CHANNEL_NAME   = "vote-cards"
PLACES_CHANNEL_NAME = "places"


class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def nb(self):
        return self.bot.nb

    @app_commands.command(name="setup", description="(Admin) Create and configure NumsBot channels.")
    async def setup(self, interaction: discord.Interaction):
        if interaction.user.id != self.bot.admin_id:
            await interaction.response.send_message("🚫 Admin only.", ephemeral=True)
            return

        await interaction.response.send_message("🔧 Setting up NumsBot...", ephemeral=True)

        guild    = interaction.guild
        bot_role = guild.me.top_role

        everyone_deny_send = discord.PermissionOverwrite(
            send_messages=False,
            send_messages_in_threads=True,
            add_reactions=True,
            read_messages=True,
            read_message_history=True,
        )
        bot_allow = discord.PermissionOverwrite(
            send_messages=True,
            create_public_threads=True,
            manage_messages=True,
            manage_threads=True,
            pin_messages=True,
            embed_links=True,
            add_reactions=True,
            read_messages=True,
            read_message_history=True,
        )

        # ── #vote-cards ──────────────────────────────────────────────────
        vote_channel = discord.utils.get(guild.text_channels, name=VOTE_CHANNEL_NAME)
        if not vote_channel:
            vote_channel = await guild.create_text_channel(
                name=VOTE_CHANNEL_NAME,
                overwrites={guild.default_role: everyone_deny_send, bot_role: bot_allow},
                topic="NumsBot vote sessions. Use /nuuums to start.",
            )
            vote_status = "created"
        else:
            await vote_channel.set_permissions(guild.default_role, **{k: v for k, v in everyone_deny_send._values.items()})
            await vote_channel.set_permissions(bot_role, **{k: v for k, v in bot_allow._values.items()})
            vote_status = "updated"

        self.nb.config.vote_channel_id = vote_channel.id

        # ── #places ──────────────────────────────────────────────────────
        places_channel = discord.utils.get(guild.text_channels, name=PLACES_CHANNEL_NAME)
        if not places_channel:
            places_channel = await guild.create_text_channel(
                name=PLACES_CHANNEL_NAME,
                overwrites={guild.default_role: everyone_deny_send, bot_role: bot_allow},
                topic="NumsBot place registry. Always up to date.",
            )
            places_status = "created"
        else:
            await places_channel.set_permissions(guild.default_role, **{k: v for k, v in everyone_deny_send._values.items()})
            await places_channel.set_permissions(bot_role, **{k: v for k, v in bot_allow._values.items()})
            places_status = "updated"

        self.nb.config.places_channel_id = places_channel.id

        # clear old messages and repost living card
        for old_id in self.nb.config.places_message_ids:
            try:
                old_msg = await places_channel.fetch_message(old_id)
                await old_msg.delete()
            except Exception:
                pass
        self.nb.config.places_message_ids = []

        places     = self.nb.active_places()
        first_page = places[:20] if places else []
        embed      = build_page_embed(first_page, 1, max(1, -(-len(places) // 20)))
        card_msg   = await places_channel.send(embed=embed)
        self.nb.config.places_message_ids = [card_msg.id]

        if not self.nb.config.places_thread_id:
            try:
                thread = await card_msg.create_thread(
                    name="Places — edit history",
                    auto_archive_duration=10080,
                )
                self.nb.config.places_thread_id = thread.id
                await thread.send("> 📋 Place registry audit log. Every addition, edit, and removal is recorded here.")
            except Exception as e:
                log.warning(f"Places thread creation failed: {e}")

        self.nb.config.save()
        await redraw_places(self.bot)

        # ── Welcome message in #vote-cards ───────────────────────────────
        welcome = discord.Embed(
            title="🍽️ NumsBot is ready",
            description=(
                "This channel is for lunch votes.\n\n"
                "`/nuuums` — start a session\n"
                f"`/placeadd` — add a place (browse them in {places_channel.mention})"
            ),
            color=discord.Color.blurple(),
        )
        await vote_channel.send(embed=welcome)

        self.nb.config.save()
        log.info(f"Setup complete by {interaction.user}")

        result = discord.Embed(title="✅ Setup complete", color=discord.Color.green())
        result.add_field(name="#vote-cards", value=f"{vote_channel.mention} — {vote_status}", inline=True)
        result.add_field(name="#places",     value=f"{places_channel.mention} — {places_status}", inline=True)
        await interaction.followup.send(embed=result, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SetupCog(bot))
