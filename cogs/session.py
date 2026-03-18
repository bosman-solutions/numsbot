"""
cogs/session.py — session slash commands
version: 0.3.3
/nuuums, /nominate (autocomplete), /votestop, /voteextend, /roll
All session activity goes into the session thread.
/roll is ephemeral with nomination buttons per suggestion.
"""

import asyncio
import logging
import os
import random
import re
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from numsbot import ROLL_SASS, ROLL_SASS_NAMED, normalize_lexi

log = logging.getLogger("numsbot.session")

NOMINATION_DURATION = 600
STOPVOTE_DURATION   = 60
GOOGLE_PLACES_KEY   = os.getenv("GOOGLE_PLACES_API_KEY", "")

ROLL_EMOJIS = ["1️⃣", "2️⃣", "3️⃣"]

SESSION_COMMANDS = (
    "🗳️ **Session open**\n"
    "`/nominate` — nominate a place (autocomplete on lexi or name)\n"
    "`/votestop` — lock nominations and start 60s close\n"
    "`/voteextend [minutes]` — reopen and extend (default 5m)\n"
    "`/roll` — let fate decide (3 rounds, then sass)\n"
    "Browse the full place list in `#places`."
)


def is_maps_url(text: str) -> bool:
    return "maps.google" in text or "goo.gl/maps" in text or "maps.app.goo" in text


def build_vote_embed(nominations: list[dict], locked: bool, seconds_left: int) -> discord.Embed:
    minutes = seconds_left // 60
    seconds = seconds_left % 60

    if locked:
        status = f"🔒 Locked — closing in {minutes}m {seconds}s"
        color  = discord.Color.orange()
    else:
        status = f"⏱️ {minutes}m {seconds}s remaining"
        color  = discord.Color.green()

    embed = discord.Embed(
        title="🍽️ Where are we eating?",
        description=status,
        color=color,
    )

    if not nominations:
        embed.add_field(
            name="No nominations yet",
            value="Use `/nominate` in the thread below",
            inline=False,
        )
    else:
        lines = []
        for n in nominations:
            line = f"{n['emoji']} **{n['name']}**"
            if n.get("pricing"):
                line += f" {n['pricing']}"
            lines.append(line)
        embed.add_field(name="Nominees", value="\n".join(lines), inline=False)
        embed.set_footer(text="React with the emoji to vote. One emoji = one vote.")

    return embed


async def fetch_place_from_maps(url: str) -> dict:
    """Resolve Maps URL → Place ID → Place Details (New). Falls back to Text Search."""
    if not GOOGLE_PLACES_KEY:
        return {}
    try:
        import aiohttp

        async with aiohttp.ClientSession() as s:
            async with s.get(url, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as r:
                resolved_url = str(r.url)

        log.debug(f"Maps resolved: {url} → {resolved_url}")

        place_id = None
        m = re.search(r"!1s([^!&]+)", resolved_url)
        if m and m.group(1).startswith("ChIJ"):
            place_id = m.group(1)
            log.info(f"Extracted Place ID: {place_id}")
        if not place_id:
            m = re.search(r"place_id=([^&]+)", resolved_url)
            if m:
                place_id = m.group(1)

        field_mask   = "id,displayName,formattedAddress,googleMapsUri,primaryType,businessStatus,location"
        base_headers = {"Content-Type": "application/json", "X-Goog-Api-Key": GOOGLE_PLACES_KEY, "X-Goog-FieldMask": field_mask}

        if place_id:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://places.googleapis.com/v1/places/{place_id}", headers=base_headers) as r:
                    if r.status == 200:
                        p = await r.json()
                        loc = p.get("location", {})
                        raw = p.get("primaryType", "")
                        return {
                            "name": p.get("displayName", {}).get("text", ""),
                            "address": p.get("formattedAddress", ""),
                            "google_maps": p.get("googleMapsUri", url),
                            "primary_type": raw.replace("_", " ") if raw else "",
                            "business_status": p.get("businessStatus", ""),
                            "lat": loc.get("latitude"), "lng": loc.get("longitude"),
                            "phone": "", "site": "", "pricing": "",
                        }
                    log.warning(f"Place Details {r.status}, falling back")

        query = resolved_url
        m = re.search(r"/maps/place/([^/@?]+)", resolved_url)
        if m:
            query = m.group(1).replace("+", " ").replace("%20", " ")
        log.info(f"Text Search fallback: {query}")

        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://places.googleapis.com/v1/places:searchText",
                json={"textQuery": query, "pageSize": 1},
                headers={**base_headers, "X-Goog-FieldMask": "places." + field_mask.replace(",", ",places.")},
            ) as r:
                if r.status != 200:
                    log.error(f"Text Search {r.status}")
                    return {}
                data = await r.json()

        places = data.get("places", [])
        if not places:
            return {}
        p = places[0]
        loc = p.get("location", {})
        raw = p.get("primaryType", "")
        return {
            "name": p.get("displayName", {}).get("text", ""),
            "address": p.get("formattedAddress", ""),
            "google_maps": p.get("googleMapsUri", url),
            "primary_type": raw.replace("_", " ") if raw else "",
            "business_status": p.get("businessStatus", ""),
            "lat": loc.get("latitude"), "lng": loc.get("longitude"),
            "phone": "", "site": "", "pricing": "",
        }

    except Exception as e:
        log.error(f"Maps lookup error: {e}", exc_info=True)
        return {}


# ── Roll suggestion view ──────────────────────────────────────────────────────

class RollView(discord.ui.View):
    """
    Ephemeral view shown only to the person who ran /roll.
    One button per suggestion. Pressing one nominates it into the session.
    Buttons disable after any pick, or on timeout.
    """

    def __init__(self, picks: list, cog):
        super().__init__(timeout=60)
        self.picks = picks
        self.cog   = cog

        for i, place in enumerate(picks):
            button = discord.ui.Button(
                label=f"{ROLL_EMOJIS[i]} {place.name}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"roll_{place.id}",
            )
            button.callback = self._make_callback(place)
            self.add_item(button)

    def _make_callback(self, place):
        """
        Factory — returns a callback bound to a specific place.
        Each button needs its own closure so it knows which place it nominates.
        """
        async def callback(interaction: discord.Interaction):
            session = self.cog.nb.session

            if not session.active:
                await interaction.response.edit_message(
                    content="Session ended.", embed=None, view=None
                )
                return
            if session.locked:
                await interaction.response.edit_message(
                    content="Nominations are locked.", embed=None, view=None
                )
                return
            if len(session.nominations) >= 10:
                await interaction.response.edit_message(
                    content="Already at 10 nominations.", embed=None, view=None
                )
                return
            if session.find_nomination(place.lexi):
                await interaction.response.edit_message(
                    content=f"**{place.name}** is already nominated.",
                    embed=None, view=None
                )
                return

            emoji = session.next_emoji()
            if not emoji:
                return

            session.nominations.append({
                "lexi":         place.lexi,
                "place_id":     place.id,
                "name":         place.name,
                "emoji":        emoji,
                "pricing":      place.pricing,
                "nominator_id": interaction.user.id,
            })

            await self.cog.add_reaction_to_embed(emoji)
            elapsed   = asyncio.get_event_loop().time() - (session.started_at or 0)
            remaining = max(0, int(session.duration - elapsed))
            await self.cog.update_vote_embed(remaining)

            await self.cog.thread_send(embed=discord.Embed(
                description=f"{emoji} **{place.name}** nominated by {interaction.user.display_name}",
                color=discord.Color.green(),
            ))

            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(
                content=f"✅ **{place.name}** nominated.",
                embed=None,
                view=self,
            )

        return callback

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── SessionCog ────────────────────────────────────────────────────────────────

class SessionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def nb(self):
        return self.bot.nb

    def _vote_channel(self) -> Optional[discord.TextChannel]:
        cid = self.nb.config.vote_channel_id
        return self.bot.get_channel(cid) if cid else None

    def _session_thread(self) -> Optional[discord.Thread]:
        tid = self.nb.session.thread_id
        return self.bot.get_channel(tid) if tid else None

    async def update_vote_embed(self, seconds_left: int):
        session = self.nb.session
        if not session.embed_message_id or not session.channel_id:
            return
        try:
            channel = self.bot.get_channel(session.channel_id)
            msg     = await channel.fetch_message(session.embed_message_id)
            await msg.edit(embed=build_vote_embed(
                session.nominations, session.locked, seconds_left
            ))
        except Exception as e:
            log.warning(f"Vote embed update failed: {e}")

    async def add_reaction_to_embed(self, emoji: str):
        session = self.nb.session
        if not session.embed_message_id or not session.channel_id:
            return
        try:
            channel = self.bot.get_channel(session.channel_id)
            msg     = await channel.fetch_message(session.embed_message_id)
            await msg.add_reaction(emoji)
        except Exception as e:
            log.warning(f"Reaction seed failed: {e}")

    async def thread_send(self, content=None, embed=None):
        thread = self._session_thread()
        if not thread:
            return None
        try:
            return await thread.send(content=content, embed=embed)
        except Exception as e:
            log.warning(f"Thread send failed: {e}")
            return None

    async def run_timer(self, duration: int):
        try:
            elapsed = 0
            while elapsed < duration:
                await asyncio.sleep(10)
                elapsed += 10
                await self.update_vote_embed(max(0, duration - elapsed))
        except asyncio.CancelledError:
            return
        voting_cog = self.bot.get_cog("VotingCog")
        if voting_cog:
            channel = self.bot.get_channel(self.nb.session.channel_id)
            if channel:
                await voting_cog.tally(channel)

    # ── /nuuums ──────────────────────────────────────────────────────────

    @app_commands.command(name="nuuums", description="Start a lunch vote session.")
    async def nuuums(self, interaction: discord.Interaction):
        vote_channel = self._vote_channel()

        if vote_channel and interaction.channel_id != vote_channel.id:
            await interaction.response.send_message(
                f"Start sessions in {vote_channel.mention}",
                ephemeral=True,
            )
            return

        if self.nb.session.active:
            thread = self._session_thread()
            ref    = thread.mention if thread else "the active thread"
            await interaction.response.send_message(
                f"Already rolling. Head to {ref}.",
                ephemeral=True,
            )
            return

        self.nb.session.active     = True
        self.nb.session.channel_id = interaction.channel_id
        self.nb.session.locked     = False
        self.nb.session.duration   = NOMINATION_DURATION
        self.nb.session.started_at = asyncio.get_event_loop().time()

        embed = build_vote_embed([], False, NOMINATION_DURATION)
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        self.nb.session.embed_message_id = msg.id

        try:
            thread = await msg.create_thread(
                name=f"Lunch — {discord.utils.utcnow().strftime('%b %d')}",
                auto_archive_duration=60,
            )
            self.nb.session.thread_id = thread.id
            log.info(f"Session thread created: {thread.id}")
        except Exception as e:
            log.error(f"Thread creation failed: {e}")
            self.nb.session.thread_id = None

        await self.thread_send(content=SESSION_COMMANDS)

        places = self.nb.active_places()[:10]
        if places:
            lines = [
                f"`{p.lexi}` — **{p.name}**{f' {p.pricing}' if p.pricing else ''}{f' · {p.win_count}W' if p.win_count else ''}"
                for p in places
            ]
            await self.thread_send(embed=discord.Embed(
                title="🍽️ Top places — `/nominate` to add to the vote",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            ))

        self.nb.session.timer_task = asyncio.create_task(
            self.run_timer(NOMINATION_DURATION)
        )

    # ── /nominate ────────────────────────────────────────────────────────

    @app_commands.command(name="nominate", description="Nominate a place into the active session.")
    @app_commands.describe(lexi="Start typing a lexi or place name to search")
    async def nominate(self, interaction: discord.Interaction, lexi: str):
        session = self.nb.session
        if not session.active:
            await interaction.response.send_message(
                "No active session. Start one with `/nuuums`.",
                ephemeral=True,
            )
            return

        if session.thread_id and interaction.channel_id != session.thread_id:
            thread = self._session_thread()
            ref    = thread.mention if thread else "the session thread"
            await interaction.response.send_message(
                f"Nominate inside {ref}.",
                ephemeral=True,
            )
            return

        if session.locked:
            await interaction.response.send_message(
                "Nominations are locked. Use `/voteextend` to reopen.",
                ephemeral=True,
            )
            return

        if len(session.nominations) >= 10:
            await interaction.response.send_message(
                "We're at 10 places — vote for what's there.",
                ephemeral=True,
            )
            return

        place = self.nb.find_by_lexi(lexi)
        if not place:
            await interaction.response.send_message(
                f"Don't know `{lexi}`. Add it with `/placeadd` first.",
                ephemeral=True,
            )
            return

        emoji = session.next_emoji()
        if not emoji:
            return

        if session.find_nomination(place.lexi):
            await interaction.response.send_message(
                f"**{place.name}** is already nominated.",
                ephemeral=True,
            )
            return

        session.nominations.append({
            "lexi":         place.lexi,
            "place_id":     place.id,
            "name":         place.name,
            "emoji":        emoji,
            "pricing":      place.pricing,
            "nominator_id": interaction.user.id,
        })

        await self.add_reaction_to_embed(emoji)
        elapsed   = asyncio.get_event_loop().time() - (session.started_at or 0)
        remaining = max(0, int(session.duration - elapsed))
        await self.update_vote_embed(remaining)

        await interaction.response.send_message(
            f"✅ **{place.name}** nominated.",
            ephemeral=True,
        )
        await self.thread_send(embed=discord.Embed(
            description=f"{emoji} **{place.name}** nominated by {interaction.user.display_name}",
            color=discord.Color.green(),
        ))

    @nominate.autocomplete("lexi")
    async def nominate_autocomplete(self, interaction: discord.Interaction, current: str):
        places = self.nb.active_places()
        cl     = current.lower()
        matches = [
            p for p in places
            if not cl
            or cl in p.lexi
            or cl in p.name.lower()
            or any(cl in a for a in p.lexi_aliases)
        ]
        return [
            app_commands.Choice(
                name=f"{p.lexi} — {p.name}{f' · {p.win_count}W' if p.win_count else ''}",
                value=p.lexi,
            )
            for p in matches[:25]
        ]

    # ── /votestop ────────────────────────────────────────────────────────

    @app_commands.command(name="votestop", description="Lock nominations and start 60s final vote.")
    async def votestop(self, interaction: discord.Interaction):
        session = self.nb.session

        if not session.active:
            await interaction.response.send_message("Nothing's running.", ephemeral=True)
            return
        if session.locked:
            await interaction.response.send_message("Already locked. Use `/voteextend` to reopen.", ephemeral=True)
            return
        if not session.nominations:
            await interaction.response.send_message("No nominations yet — add some places first.", ephemeral=True)
            return

        if session.timer_task and not session.timer_task.done():
            session.timer_task.cancel()

        session.locked     = True
        session.duration   = STOPVOTE_DURATION
        session.started_at = asyncio.get_event_loop().time()
        await self.update_vote_embed(STOPVOTE_DURATION)

        await interaction.response.send_message("✅ Locked.", ephemeral=True)
        await self.thread_send(embed=discord.Embed(
            description="🔒 Nominations locked. **60 seconds to vote.** Choose wisely.",
            color=discord.Color.orange(),
        ))

        session.timer_task = asyncio.create_task(self.run_timer(STOPVOTE_DURATION))

    # ── /voteextend ──────────────────────────────────────────────────────

    @app_commands.command(name="voteextend", description="Reopen nominations and extend the timer.")
    @app_commands.describe(minutes="Minutes to extend (default 5, max 30)")
    async def voteextend(self, interaction: discord.Interaction, minutes: int = 5):
        session = self.nb.session

        if not session.active:
            await interaction.response.send_message("Nothing's running.", ephemeral=True)
            return
        if not 1 <= minutes <= 30:
            await interaction.response.send_message("Extension must be 1–30 minutes.", ephemeral=True)
            return

        if session.timer_task and not session.timer_task.done():
            session.timer_task.cancel()

        duration = minutes * 60
        session.locked     = False
        session.duration   = duration
        session.started_at = asyncio.get_event_loop().time()
        await self.update_vote_embed(duration)

        await interaction.response.send_message("✅ Extended.", ephemeral=True)
        await self.thread_send(embed=discord.Embed(
            description=f"⏰ Extended by **{minutes} minute(s)**. Nominations open again.",
            color=discord.Color.green(),
        ))

        session.timer_task = asyncio.create_task(self.run_timer(duration))

    # ── /roll ────────────────────────────────────────────────────────────

    @app_commands.command(name="roll", description="Can't decide? Let fate choose. 3 rounds then sass.")
    async def roll(self, interaction: discord.Interaction):
        session = self.nb.session

        # round 3+ — named sass fires publicly into the thread
        if session.roll_round >= 3:
            name = interaction.user.display_name
            sass = random.choice(ROLL_SASS_NAMED).format(name=name)
            await interaction.response.send_message("🎲", ephemeral=True)
            await self.thread_send(embed=discord.Embed(
                description=sass,
                color=discord.Color.red(),
            ))
            return

        nominated_ids = session.nominated_place_ids() if session.active else set()
        pool = [
            p for p in self.nb.active_places()
            if p.id not in nominated_ids and p.id not in session.roll_used
        ]

        if not pool:
            await interaction.response.send_message(
                "beep boop. the place pool is empty.",
                ephemeral=True,
            )
            return

        picks = random.sample(pool, min(3, len(pool)))
        for p in picks:
            session.roll_used.add(p.id)
        session.roll_round += 1

        is_final = session.roll_round >= 3

        embed = discord.Embed(
            title="🎲 How about...",
            description="\n".join(
                f"{ROLL_EMOJIS[i]} **{p.name}**{f' {p.pricing}' if p.pricing else ''}"
                for i, p in enumerate(picks)
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(
            text="That's your lot. One more /roll for consequences."
            if is_final else "Tap to nominate. /roll again if none feel right."
        )

        view = RollView(picks, self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SessionCog(bot))
