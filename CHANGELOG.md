# NumsBot Changelog

## 0.3.3 — current
- `/roll` is now ephemeral — only the roller sees the suggestions
- Roll suggestions have nomination buttons (1️⃣ 2️⃣ 3️⃣) — tap to nominate directly
- Named sass pool added — round 3+ calls out the indecisive person by display name
- `ROLL_SASS_NAMED` added to `numsbot.py` with `{name}` substitution
- `RollView` class added to `session.py` with button factory pattern

## 0.3.2 — messaging cleanup
- All stale command references updated across `places_card.py`, `setup.py`, `session.py`
- `places_card.py`: description → `/nominate`, footer → `/placeview`, empty state → `/placeadd`
- `setup.py`: welcome message uses `/nuuums` and `/placeadd`
- `SESSION_COMMANDS` string updated with full command names

## 0.3.1 — redraw fix + bang command removal
- `redraw_places()` now scans `#places` channel history and deletes all bot messages before reposting — fixes stale orphaned cards
- `bot.py` prefix set to null byte `\x00` — bang commands (`!pa`, `!va` etc.) completely dead
- `on_message` skips `process_commands` entirely — slash only
- `help_command=None` — built-in `!help` removed

## 0.3.0 — slash commands + living places card
- Full migration to slash commands — no prefix commands
- `/nuuums`, `/nominate` (autocomplete), `/votestop`, `/voteextend`, `/roll`
- `/placeadd`, `/placeview`, `/placeremove`, `/placeretire`, `/placeunretire`
- `/setup`, `/burnitall`, `/botstatus`, `/redrawplaces`
- `/nominate` autocomplete — filters active places by lexi, name, and alias on every keystroke
- All place commands ephemeral — zero channel spam
- `#places` living card — 20 places per page, sorted by win count, auto-redraws after every mutation
- Permanent audit thread in `#places` — every addition, edit, removal logged
- `BotConfig` expanded: `places_channel_id`, `places_thread_id`, `places_message_ids`
- `places_card.py` added — shared utility for `redraw_places()` and `log_to_places_thread()`
- `/pd` → `/placeview` with two buttons: "Edit details ✏️" and "Update Maps 🗺️"
- `UpdateMapsModal` added — fixes Maps link without touching other fields
- `enrichment.py` removed — replaced by inline ephemeral modals
- `help.py` removed — Discord shows slash commands natively

## 0.2.1 — winner card + no pin
- Winner card replaces the vote card embed in place (edit, not new message)
- Pinning removed — thread creation keeps the card visible naturally
- No duplicate winner post in main channel

## 0.2.0 — threading + setup + Place ID extraction
- `!setup` command — creates `#vote-cards`, sets `@everyone` deny send messages, configures bot permissions, writes `config.json`
- Session thread — all nomination noise goes into a thread on the vote card
- `!nuuums` enforces vote channel, creates thread, deletes command message
- All session commands (`!va`, `!vs`, `!ve`, `!roll`) respond in thread, delete command messages
- Maps lookup — extracts Place ID (`ChIJ...`) from resolved URL, uses Place Details (New) API for exact match, falls back to Text Search only if no Place ID found
- `!pa` — lexi mandatory on all forms, posts inline place card with "Edit place ✏️" button
- Unified edit modal covering name, lexi, alias, phone, pricing
- `enrichment.py` DM flow replaced by inline place cards
- `BotConfig` class added to `numsbot.py` — persistent server config in `config.json`
- `Session.thread_id` added
- `cogs/setup.py` added

## 0.1.1 — places registry + enrichment
- Google Places API (New) integration — Maps link enrichment on `!pa`
- Place ID extraction from Maps URLs
- `!pd` / `!placedeets` — place detail view with alias button
- `!placeretire` / `!placeunretire` — soft retire preserving history
- `!recents` and `!stats` commands
- `enrichment.py` — DM place card flow after `!pa`
- Emoji pool extended to 10 (1️⃣–🔟)
- `!roll` — 3 rounds, excludes nominated and previously rolled places, sass pool

## 0.1.0 — initial build
- `!nuuums` — start session, pin vote card
- `!va` / `!voteadd` — nominate a place
- `!vs` / `!votestop` — lock nominations, 60s close
- `!ve` / `!voteextend` — reopen and extend
- `!pa` / `!placeadd` — add place (auto-lexi from name)
- `!prm` / `!placerm` — remove with confirm
- `!pls` / `!placels` — list places (DM)
- Reaction-based voting — bot pre-seeds emojis, tally on close
- Tie detection with `TIEBREAKER_WEAPONS`
- `places.json` in named Docker volume — survives container rebuilds
- `Session` object — in-memory, intentionally lost on restart
- `Place` object — full data model with lexi, aliases, win tracking
- Docker + Makefile deploy workflow
