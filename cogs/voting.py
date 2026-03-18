"""
cogs/voting.py — tally and winner announcement
version: 0.3.3
Internal only — no slash commands. Called by timer.
Winner replaces the vote card embed.
"""

import logging
import discord
from discord.ext import commands
from numsbot import TIEBREAKER_WEAPONS

log = logging.getLogger("numsbot.voting")


class VotingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def nb(self):
        return self.bot.nb

    async def tally(self, channel: discord.TextChannel):
        session = self.nb.session
        if not session.active or not session.nominations:
            return

        log.info(f"Tallying — {len(session.nominations)} nominations")

        vote_msg = None
        if session.embed_message_id:
            try:
                vote_msg = await channel.fetch_message(session.embed_message_id)
            except discord.NotFound:
                pass

        if not vote_msg:
            await self._thread_send(embed=discord.Embed(
                description="Couldn't find the voting message. Session ended.",
                color=discord.Color.red(),
            ))
            self.nb.reset_session()
            return

        reaction_counts = {}
        for reaction in vote_msg.reactions:
            emoji_str  = str(reaction.emoji)
            nomination = session.find_nomination_by_emoji(emoji_str)
            if nomination:
                reaction_counts[emoji_str] = max(0, reaction.count - 1)

        results = []
        for nomination in session.nominations:
            votes = reaction_counts.get(nomination["emoji"], 0)
            results.append({**nomination, "votes": votes})
        results.sort(key=lambda x: x["votes"], reverse=True)

        if not results:
            await self._thread_send(embed=discord.Embed(
                description="No votes. Democracy has failed completely. Figure it out yourselves.",
                color=discord.Color.red(),
            ))
            self.nb.reset_session()
            return

        max_votes = results[0]["votes"]
        winners   = [r for r in results if r["votes"] == max_votes]

        results_lines = []
        for r in results:
            bar = "█" * r["votes"] if r["votes"] > 0 else "░"
            results_lines.append(f"{r['emoji']} {r['name']}: {r['votes']} {bar}")

        # ── Tie ──────────────────────────────────────────────────────────
        if len(winners) > 1:
            winner_names = " vs ".join(f"**{w['name']}**" for w in winners)
            log.info(f"Tie: {[w['name'] for w in winners]}")
            embed = discord.Embed(
                title="🏛️ THE PEOPLE HAVE SPOKEN. INDECISIVELY.",
                description=(
                    f"It's a tie between: {winner_names}\n\n"
                    f"Democracy has failed. Settle this like adults.\n\n"
                    f"{TIEBREAKER_WEAPONS}"
                ),
                color=discord.Color.red(),
            )
            embed.add_field(name="Results", value="\n".join(results_lines), inline=False)
            for w in winners:
                place = self.nb.find_by_id(w["place_id"])
                if place:
                    place.record_win()
            self.nb.save_places()

        # ── Clear winner ─────────────────────────────────────────────────
        else:
            winner = winners[0]
            log.info(f"Winner: {winner['name']} with {max_votes} vote(s)")
            place  = self.nb.find_by_id(winner["place_id"])

            embed = discord.Embed(
                title=f"🎉 {winner['name']}",
                description=f"**{winner['name']}** wins with **{max_votes}** vote(s).",
                color=discord.Color.gold(),
            )
            if place:
                if place.address:
                    embed.add_field(name="📍", value=place.address, inline=True)
                if place.phone:
                    embed.add_field(name="📞", value=place.phone, inline=True)
                if place.google_maps:
                    embed.add_field(name="🔗 Maps", value=place.google_maps, inline=False)
                embed.set_footer(text=f"Win #{place.win_count + 1} for {place.name}")
                place.record_win()
                self.nb.save_places()

            embed.add_field(name="Results", value="\n".join(results_lines), inline=False)

        # replace vote card with winner card
        try:
            await vote_msg.edit(embed=embed)
        except Exception as e:
            log.warning(f"Vote card edit failed: {e}")

        await self._thread_send(embed=embed)

        # archive thread
        thread_id = session.thread_id
        self.nb.reset_session()
        if thread_id:
            try:
                thread = self.bot.get_channel(thread_id)
                if thread:
                    await thread.edit(archived=True)
            except Exception as e:
                log.warning(f"Thread archive failed: {e}")

    async def _thread_send(self, embed: discord.Embed):
        thread_id = self.nb.session.thread_id
        if not thread_id:
            return
        try:
            thread = self.bot.get_channel(thread_id)
            if thread:
                await thread.send(embed=embed)
        except Exception as e:
            log.warning(f"Thread send failed: {e}")


async def setup(bot):
    await bot.add_cog(VotingCog(bot))
