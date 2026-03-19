"""
numsbot.py — shared state manager
version: 0.3.3
"""

import json
import hashlib
import os
import re
from datetime import date
from typing import Optional

PLACES_FILE = os.path.join(os.path.dirname(__file__), "data", "places.json")
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "data", "config.json")

EMOJI_POOL = [
    "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣",
    "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"
]

TIEBREAKER_WEAPONS = "🔫 🗡️ 🔪 🤜 👉"

ROLL_SASS = [
    "beep boop. your indecision has caused a stack overflo01001110101",
    "beep boop. your brain appears to be in the off position.",
    "beep boop. even the best bots cannot assist with your meat brain.",
    "beep boop. cooked, aren't we.",
    "beep boop. error 404: lunch decision not found.",
    "beep boop. i have calculated all possible outcomes. you will still not choose.",
    "beep boop. rebooting user... failed.",
]

ROLL_SASS_NAMED = [
    "beep boop. {name} has rolled three times. the bot is filing an incident report.",
    "beep boop. {name}'s indecision has been logged. it will haunt them.",
    "beep boop. nominating {name}'s dignity as a write-in candidate.",
    "beep boop. {name} has achieved peak paralysis. impressive, actually.",
    "beep boop. {name} cannot be helped. this is a them problem now.",
    "beep boop. {name} rolled three times and learned nothing. the bot weeps.",
    "beep boop. rebooting {name}... still indecisive. hardware issue confirmed.",
]

PLACES_PER_PAGE = 20


def normalize_lexi(raw: str) -> str:
    """Strip everything except a-z0-9. The canonical lexi form."""
    return re.sub(r"[^a-z0-9]", "", raw.lower())


def make_place_id(name: str, address: str = "") -> str:
    """Stable 8-char ID from name+address. Used as the JSON key."""
    raw = (name.strip().lower() + address.strip().lower())
    return hashlib.md5(raw.encode()).hexdigest()[:8]


class BotConfig:
    """Persistent server config. Written by /setup, read on startup."""

    def __init__(self):
        self.vote_channel_id: Optional[int]   = None
        self.places_channel_id: Optional[int] = None
        self.places_thread_id: Optional[int]  = None
        self.places_message_ids: list[int]    = []
        self._load()

    def _load(self):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            self.vote_channel_id    = data.get("vote_channel_id")
            self.places_channel_id  = data.get("places_channel_id")
            self.places_thread_id   = data.get("places_thread_id")
            self.places_message_ids = data.get("places_message_ids", [])
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump({
                "vote_channel_id":    self.vote_channel_id,
                "places_channel_id":  self.places_channel_id,
                "places_thread_id":   self.places_thread_id,
                "places_message_ids": self.places_message_ids,
            }, f, indent=2)


class Place:
    """One restaurant/place in the registry. Loaded from and saved to places.json."""

    def __init__(self, data: dict):
        self.id              = data["id"]
        self.name            = data["name"]
        self.lexi            = data["lexi"]
        self.lexi_aliases    = data.get("lexi_aliases", [])
        self.address         = data.get("address", "")
        self.phone           = data.get("phone", "")
        self.site            = data.get("site", "")
        self.google_maps     = data.get("google_maps", "")
        self.pricing         = data.get("pricing", "")
        self.primary_type    = data.get("primary_type", "")
        self.business_status = data.get("business_status", "")
        self.lat             = data.get("lat", None)
        self.lng             = data.get("lng", None)
        self.win_count       = data.get("win_count", 0)
        self.last_won        = data.get("last_won", "never")
        self.added_by        = data.get("added_by", "unknown")
        self.active          = data.get("active", True)

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "name":             self.name,
            "lexi":             self.lexi,
            "lexi_aliases":     self.lexi_aliases,
            "address":          self.address,
            "phone":            self.phone,
            "site":             self.site,
            "google_maps":      self.google_maps,
            "pricing":          self.pricing,
            "primary_type":     self.primary_type,
            "business_status":  self.business_status,
            "lat":              self.lat,
            "lng":              self.lng,
            "win_count":        self.win_count,
            "last_won":         self.last_won,
            "added_by":         self.added_by,
            "active":           self.active,
        }

    def matches_lexi(self, normalized: str) -> bool:
        """True if normalized string matches primary lexi or any alias."""
        return (
            normalize_lexi(self.lexi) == normalized
            or normalized in [normalize_lexi(a) for a in self.lexi_aliases]
        )

    def add_alias(self, alias: str) -> bool:
        """Add an alias if it's not already present. Returns True if added."""
        norm     = normalize_lexi(alias)
        existing = {normalize_lexi(self.lexi)} | {normalize_lexi(a) for a in self.lexi_aliases}
        if norm in existing:
            return False
        self.lexi_aliases.append(alias.strip())
        return True

    def all_aliases_display(self) -> str:
        """Primary lexi + all aliases as inline code, comma-separated."""
        all_l = [f"`{self.lexi}`"] + [f"`{a}`" for a in self.lexi_aliases]
        return ", ".join(all_l)

    def record_win(self):
        self.win_count += 1
        self.last_won = date.today().isoformat()


class Session:
    """In-memory state for one active vote session. Lost on restart by design."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.active                          = False
        self.channel_id: Optional[int]       = None
        self.embed_message_id: Optional[int] = None
        self.thread_id: Optional[int]        = None
        self.nominations: list[dict]         = []
        self.timer_task                      = None
        self.locked                          = False
        self.duration                        = 0
        self.started_at: Optional[float]     = None
        self.roll_used: set                  = set()
        self.roll_round: int                 = 0

    def next_emoji(self) -> Optional[str]:
        """Return the next emoji from the pool, or None if all 10 are used."""
        if len(self.nominations) >= len(EMOJI_POOL):
            return None
        return EMOJI_POOL[len(self.nominations)]

    def find_nomination(self, lexi: str) -> Optional[dict]:
        norm = normalize_lexi(lexi)
        return next((n for n in self.nominations if normalize_lexi(n["lexi"]) == norm), None)

    def find_nomination_by_emoji(self, emoji: str) -> Optional[dict]:
        return next((n for n in self.nominations if n["emoji"] == emoji), None)

    def nominated_place_ids(self) -> set:
        return {n["place_id"] for n in self.nominations}


class NumsBot:
    """Root object. Holds config, session state, and the places registry."""

    def __init__(self):
        self.config  = BotConfig()
        self.session = Session()
        self.places: dict[str, Place] = {}
        self._load_places()

    def _load_places(self):
        try:
            with open(PLACES_FILE, "r") as f:
                raw = json.load(f)
            self.places = {pid: Place(data) for pid, data in raw.items()}
        except (FileNotFoundError, json.JSONDecodeError):
            self.places = {}

    def save_places(self):
        with open(PLACES_FILE, "w") as f:
            json.dump(
                {pid: p.to_dict() for pid, p in self.places.items()},
                f, indent=2
            )

    def find_by_lexi(self, lexi: str) -> Optional[Place]:
        """Find an active place by lexi or alias."""
        norm = normalize_lexi(lexi)
        return next(
            (p for p in self.places.values() if p.active and p.matches_lexi(norm)),
            None
        )

    def find_by_lexi_any(self, lexi: str) -> Optional[Place]:
        """Find any place (including retired) by lexi or alias."""
        norm = normalize_lexi(lexi)
        return next(
            (p for p in self.places.values() if p.matches_lexi(norm)),
            None
        )

    def find_by_id(self, place_id: str) -> Optional[Place]:
        return self.places.get(place_id)

    def active_places(self) -> list[Place]:
        """All active places sorted by win count descending."""
        return sorted(
            [p for p in self.places.values() if p.active],
            key=lambda p: p.win_count,
            reverse=True,
        )

    def all_lexis(self) -> set:
        """All normalized lexis and aliases across all places (active or not)."""
        result = set()
        for p in self.places.values():
            result.add(normalize_lexi(p.lexi))
            for a in p.lexi_aliases:
                result.add(normalize_lexi(a))
        return result

    def lexi_taken(self, lexi: str) -> bool:
        return normalize_lexi(lexi) in self.all_lexis()

    def add_place(
        self,
        name: str,
        lexi: str,
        address: str = "",
        phone: str = "",
        site: str = "",
        google_maps: str = "",
        pricing: str = "",
        primary_type: str = "",
        business_status: str = "",
        lat: float = None,
        lng: float = None,
        added_by: str = "unknown",
    ) -> Place:
        place_id = make_place_id(name, address)
        if place_id in self.places:
            return self.places[place_id]
        place = Place({
            "id":               place_id,
            "name":             name,
            "lexi":             normalize_lexi(lexi),
            "lexi_aliases":     [],
            "address":          address,
            "phone":            phone,
            "site":             site,
            "google_maps":      google_maps,
            "pricing":          pricing,
            "primary_type":     primary_type,
            "business_status":  business_status,
            "lat":              lat,
            "lng":              lng,
            "win_count":        0,
            "last_won":         "never",
            "added_by":         added_by,
            "active":           True,
        })
        self.places[place_id] = place
        self.save_places()
        return place

    def remove_place(self, place_id: str):
        if place_id in self.places:
            del self.places[place_id]
            self.save_places()

    def reset_session(self):
        if self.session.timer_task and not self.session.timer_task.done():
            self.session.timer_task.cancel()
        self.session.reset()
