"""
cogs/places_card.py — living places card utility
version: 0.3.2
"""

import logging
import math
import discord
from numsbot import PLACES_PER_PAGE

log = logging.getLogger("numsbot.places_card")


def build_page_embed(places: list, page: int, total_pages: int) -> discord.Embed:
    embed = discord.Embed(
        title="🍽️ Places" if total_pages == 1 else f"🍽️ Places — page {page}/{total_pages}",
        description="Use `/nominate` during a session to add a place to the vote.",
        color=discord.Color.blurple(),
    )

    if not places:
        embed.description = "No places yet. Use `/placeadd` to add some."
        return embed

    lines = []
    for p in places:
        line = f"`{p.lexi}` — **{p.name}**"
        if p.pricing:
            line += f" {p.pricing}"
        if p.lexi_aliases:
            line += f" _(also: {', '.join(f'`{a}`' for a in p.lexi_aliases)})_"
        if p.win_count > 0:
            line += f" · {p.win_count}W"
        lines.append(line)

    embed.add_field(name="Places", value="\n".join(lines), inline=False)
    embed.set_footer(text=f"{len(places)} places on this page · /placeview <lexi> for details")
    return embed


async def redraw_places(bot) -> None:
    """
    Rebuild the living places card in #places.
    Always does a full redraw: deletes all bot messages in the channel,
    then reposts fresh pages.
    """
    cfg = bot.nb.config

    if not cfg.places_channel_id:
        return

    channel = bot.get_channel(cfg.places_channel_id)
    if not channel:
        return

    places      = bot.nb.active_places()
    total_pages = max(1, math.ceil(len(places) / PLACES_PER_PAGE))
    pages       = [
        places[i * PLACES_PER_PAGE:(i + 1) * PLACES_PER_PAGE]
        for i in range(total_pages)
    ]

    # delete all existing bot messages in the channel
    ids_to_delete = set(cfg.places_message_ids)
    try:
        async for msg in channel.history(limit=50):
            if msg.author.id == bot.user.id:
                ids_to_delete.add(msg.id)
    except Exception as e:
        log.warning(f"Could not scan channel history: {e}")

    for msg_id in ids_to_delete:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.delete()
        except Exception:
            pass

    cfg.places_message_ids = []

    # post fresh pages
    new_ids   = []
    first_msg = None

    for i, page_places in enumerate(pages):
        embed = build_page_embed(page_places, i + 1, total_pages)
        try:
            msg = await channel.send(embed=embed)
            new_ids.append(msg.id)
            if i == 0:
                first_msg = msg
        except Exception as e:
            log.error(f"Places card post failed (page {i+1}): {e}")

    # ensure audit thread exists on first message
    if first_msg and not cfg.places_thread_id:
        try:
            thread = await first_msg.create_thread(
                name="Places — edit history",
                auto_archive_duration=10080,
            )
            cfg.places_thread_id = thread.id
            await thread.send("> 📋 Place registry audit log.")
            log.info(f"Places audit thread created: {thread.id}")
        except Exception as e:
            log.warning(f"Places thread creation failed: {e}")

    cfg.places_message_ids = new_ids
    cfg.save()
    log.info(f"Places card redrawn: {total_pages} page(s), {len(places)} places")


async def log_to_places_thread(bot, message: str) -> None:
    """Append an audit line to the permanent places thread."""
    cfg = bot.nb.config
    if not cfg.places_thread_id:
        return
    try:
        thread = bot.get_channel(cfg.places_thread_id)
        if thread:
            await thread.send(message)
    except Exception as e:
        log.warning(f"Places thread log failed: {e}")
