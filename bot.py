"""
bot.py — NumsBot entrypoint
version: 0.3.4
Slash commands only. Prefix commands disabled.
Guild sync when GUILD_ID is set — instant propagation.
Falls back to global sync if not set.
"""

import os
import asyncio
import logging
import logging.handlers
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from numsbot import NumsBot

load_dotenv()

TOKEN     = os.getenv("DISCORD_TOKEN")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
GUILD_ID  = int(os.getenv("GUILD_ID", "0"))
VERSION   = "0.3.4"

# ── Logging ──────────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)

log_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

file_handler = logging.handlers.RotatingFileHandler(
    filename="logs/numsbot.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
file_handler.setFormatter(log_formatter)

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), handlers=[])
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

if LOG_LEVEL != "DEBUG":
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

log = logging.getLogger("numsbot")


# ── Bot — slash commands only ────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members          = True
intents.reactions        = True

bot = commands.Bot(
    command_prefix="\x00",   # null byte — will never match anything typed
    intents=intents,
    help_command=None,
)
bot.admin_id = ADMIN_ID
bot.nb       = NumsBot()

COGS = [
    "cogs.setup",
    "cogs.session",
    "cogs.voting",
    "cogs.places",
    "cogs.admin",
]


@bot.event
async def on_ready():
    log.info(f"NumsBot v{VERSION} online — {bot.user} (ID: {bot.user.id})")
    log.info(f"Admin ID: {bot.admin_id}")
    log.info(f"Places loaded: {len(bot.nb.active_places())}")

    if bot.nb.config.vote_channel_id:
        log.info(f"Vote channel: {bot.nb.config.vote_channel_id}")
    else:
        log.warning("Vote channel not configured — run /setup")

    if bot.nb.config.places_channel_id:
        log.info(f"Places channel: {bot.nb.config.places_channel_id}")

    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            # copy all commands to the guild and sync — instant
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            # wipe global commands so there are no duplicates
            bot.tree.clear_commands(guild=None)
            await bot.tree.sync()
            log.info(f"Synced {len(synced)} slash commands to guild {GUILD_ID}, globals cleared")
        else:
            synced = await bot.tree.sync()
            log.info(f"Synced {len(synced)} slash commands globally")
    except Exception as e:
        log.error(f"Slash sync error: {e}")


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # Do NOT call process_commands — slash only


@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    msg = str(error)
    log.error(f"Slash error [{interaction.command}] by {interaction.user}: {msg}")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"> Error: {msg}", ephemeral=True)
        else:
            await interaction.response.send_message(f"> Error: {msg}", ephemeral=True)
    except Exception:
        pass


async def main():
    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            log.info(f"Loaded {cog}")
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
