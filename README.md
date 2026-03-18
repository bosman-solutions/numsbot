# NumsBot 🍽️

A Discord lunch voting bot for teams who can't decide where to eat.

Built with Python 3.12, discord.py 2.x, and slash commands. Self-hosted via Docker.

---

## What it does

`/nuuums` starts a vote session in `#vote-cards`. A thread opens on the vote card — all nomination activity lives there. The main channel stays clean. When voting closes, the vote card becomes the winner card in place.

`#places` holds a living registry of known places, always up to date, auto-redrawn after every addition or edit. An audit thread logs every change.

---

## Features

- **Slash commands** with autocomplete — `/nominate` filters places by lexi, name, or alias as you type
- **Ephemeral place management** — `/placeadd`, `/placeview`, `/placeremove` only visible to the invoker
- **Google Maps enrichment** — paste a Maps link and the bot pulls name, address, type, and coordinates via Place Details API
- **Living places card** — `#places` channel has one message per 20 places, edits in place after every mutation
- **Reaction voting** — bot pre-seeds emoji reactions, tallies on close
- **Thread-based sessions** — nomination chaos stays in the thread, vote card surface stays clean
- **Named sass** — `/roll` three times and the bot calls you out by name

---

## Commands

### Session
| Command | Description |
|---------|-------------|
| `/nuuums` | Start a vote session |
| `/nominate` | Nominate a place (autocomplete) |
| `/votestop` | Lock nominations, 60s to vote |
| `/voteextend [minutes]` | Reopen and extend (default 5m) |
| `/roll` | Random suggestions, 3 rounds then sass |

### Places
| Command | Description |
|---------|-------------|
| `/placeadd` | Add a place (Maps link or manual name) |
| `/placeview` | View and edit a place |
| `/placeremove` | Permanently remove a place |
| `/placeretire` | Soft-retire, keeps history (admin) |
| `/placeunretire` | Restore a retired place (admin) |

### Admin
| Command | Description |
|---------|-------------|
| `/setup` | Create channels, set permissions, post living card |
| `/burnitall` | Hard reset — kills session, places untouched |
| `/botstatus` | Current bot state |
| `/redrawplaces` | Force-redraw `#places` from JSON |

---

## Setup

### 1. Discord Developer Portal

- Create a bot at [discord.com/developers](https://discord.com/developers/applications)
- Under **Bot**: enable `Message Content Intent`, `Server Members Intent`, `Presence Intent`
- Under **OAuth2 → URL Generator**: select `bot` + `applications.commands`, then select permissions:
  - Send Messages, Embed Links, Add Reactions, Read Message History
  - Manage Messages, Manage Channels, Manage Roles
  - Create Public Threads, Send Messages in Threads, Manage Threads
- Invite the bot to your server with the generated URL

### 2. Environment

```bash
cp .env.example .env
```

Fill in `.env`:

```env
DISCORD_TOKEN=your-bot-token
ADMIN_ID=your-discord-user-id
GOOGLE_PLACES_API_KEY=       # optional — enables Maps link enrichment
LOG_LEVEL=INFO
```

Get your user ID: Settings → Advanced → enable Developer Mode, then right-click your name → Copy User ID.

Google Places API key: [console.cloud.google.com](https://console.cloud.google.com) → enable Places API (New). Free tier is 10k requests/month — plenty for a lunch bot.

### 3. Deploy

```bash
make deploy
make logs
```

### 4. First run

In any channel, run `/setup`. The bot will:
- Create `#vote-cards` with correct permissions (`@everyone` can't post, can react and post in threads)
- Create `#places` with the living place registry
- Post the welcome message

Then `/placeadd` some places and `/nuuums` to start your first session.

---

## Architecture

```
numsbot.py          — data model: Place, Session, NumsBot, BotConfig
bot.py              — entrypoint, logging, cog loading
cogs/
  setup.py          — /setup: channel creation and permission config
  session.py        — /nuuums, /nominate, /votestop, /voteextend, /roll
  voting.py         — tally logic, winner card, thread archive
  places.py         — /placeadd, /placeview, /placeremove, /placeretire
  places_card.py    — living card redraw utility (shared)
  admin.py          — /burnitall, /botstatus, /redrawplaces
data/
  places.json       — place registry (Docker volume, survives rebuilds)
  config.json       — channel IDs written by /setup (Docker volume)
```

**Source of truth is `places.json`.** The `#places` living card is a view — `/redrawplaces` rebuilds it from JSON at any time.

**Sessions are in-memory by design.** A restart kills the active session. For a lunch bot, this is acceptable.

---

## Data persistence

Both `places.json` and `config.json` live in a named Docker volume (`numsbot_data`). Rebuilding the container image does not affect your data.

```bash
make deploy    # rebuilds image, data survives
make nuke      # removes everything including data — DESTRUCTIVE
```

---

## Makefile

```bash
make deploy    # clean rebuild, start
make rebuild   # faster rebuild using cache
make restart   # stop and start without rebuilding
make logs      # tail logs
make clean     # remove containers/images, keep data
make nuke      # remove everything including data
```

---

## License

MIT
