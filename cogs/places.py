"""
cogs/places.py — place management slash commands
version: 0.3.2
/placeadd, /placeview, /placeremove, /placeretire, /placeunretire
All ephemeral. All trigger living card redraw + audit log.
"""

import logging
import re
import discord
from discord import app_commands
from discord.ext import commands
from numsbot import normalize_lexi
from cogs.places_card import redraw_places, log_to_places_thread, build_page_embed

log = logging.getLogger("numsbot.places")

GOOGLE_PLACES_KEY = __import__("os").getenv("GOOGLE_PLACES_API_KEY", "")


# ── Edit modal ───────────────────────────────────────────────────────────────

class EditPlaceModal(discord.ui.Modal, title="Edit Place"):
    name_field = discord.ui.TextInput(
        label="Name", placeholder="e.g. In-N-Out Burger",
        required=True, max_length=100,
    )
    lexi_field = discord.ui.TextInput(
        label="Primary lexi", placeholder="e.g. innout",
        required=True, max_length=40,
    )
    alias_field = discord.ui.TextInput(
        label="Add alias (optional)", placeholder="e.g. animalsfriez",
        required=False, max_length=40,
    )
    phone_field = discord.ui.TextInput(
        label="Phone", placeholder="e.g. (909) 555-0100",
        required=False, max_length=30,
    )
    pricing_field = discord.ui.TextInput(
        label="Price range ($, $$, $$$)", placeholder="$$",
        required=False, max_length=5,
    )

    def __init__(self, place, nb, bot):
        super().__init__()
        self.place = place
        self.nb    = nb
        self.bot   = bot
        self.name_field.default    = place.name
        self.lexi_field.default    = place.lexi
        if place.phone:   self.phone_field.default   = place.phone
        if place.pricing: self.pricing_field.default = place.pricing

    async def on_submit(self, interaction: discord.Interaction):
        p = self.place
        changes = []

        new_name = self.name_field.value.strip()
        if new_name and new_name != p.name:
            p.name = new_name
            changes.append(f"name → {new_name}")

        new_lexi = normalize_lexi(self.lexi_field.value.strip())
        if new_lexi and new_lexi != normalize_lexi(p.lexi):
            existing = self.nb.find_by_lexi(new_lexi)
            if existing and existing.id != p.id:
                await interaction.response.send_message(
                    f"`{new_lexi}` is already taken by **{existing.name}**.", ephemeral=True
                )
                return
            p.lexi = new_lexi
            changes.append(f"lexi → {new_lexi}")

        alias_raw = self.alias_field.value.strip()
        if alias_raw:
            existing = self.nb.find_by_lexi(alias_raw)
            if existing and existing.id != p.id:
                await interaction.response.send_message(
                    f"`{normalize_lexi(alias_raw)}` is used by **{existing.name}**.", ephemeral=True
                )
                return
            if p.add_alias(alias_raw):
                changes.append(f"alias + {normalize_lexi(alias_raw)}")

        if self.phone_field.value.strip():
            p.phone = self.phone_field.value.strip()
            changes.append("phone updated")

        raw_pricing = self.pricing_field.value.strip()
        if raw_pricing in {"$", "$$", "$$$"}:
            p.pricing = raw_pricing
            changes.append(f"pricing → {raw_pricing}")

        self.nb.save_places()
        await redraw_places(self.bot)
        change_str = ", ".join(changes) if changes else "no changes"
        await log_to_places_thread(
            self.bot,
            f"✏️ `{p.lexi}` edited by {interaction.user.display_name} ({change_str})"
        )
        await interaction.response.send_message(
            f"✅ **{p.name}** updated: {change_str}", ephemeral=True
        )


class UpdateMapsModal(discord.ui.Modal, title="Update Maps Link"):
    maps_url = discord.ui.TextInput(
        label="Google Maps link",
        placeholder="https://maps.app.goo.gl/...",
        required=True,
        max_length=500,
    )

    def __init__(self, place, nb, bot):
        super().__init__()
        self.place = place
        self.nb    = nb
        self.bot   = bot

    async def on_submit(self, interaction: discord.Interaction):
        from cogs.session import fetch_place_from_maps, is_maps_url
        url = self.maps_url.value.strip()
        if not is_maps_url(url):
            await interaction.response.send_message("That doesn't look like a Maps link.", ephemeral=True)
            return

        await interaction.response.send_message("📍 Fetching Maps data...", ephemeral=True)
        data = await fetch_place_from_maps(url)
        if not data or not data.get("name"):
            await interaction.followup.send("Couldn't pull that link.", ephemeral=True)
            return

        p = self.place
        if data.get("business_status") == "CLOSED_PERMANENTLY":
            await interaction.followup.send(
                f"⚠️ Google says **{data['name']}** is permanently closed. Updating anyway.",
                ephemeral=True,
            )

        p.google_maps     = data.get("google_maps", "")
        p.address         = data.get("address", "") or p.address
        p.primary_type    = data.get("primary_type", "") or p.primary_type
        p.business_status = data.get("business_status", "") or p.business_status
        if data.get("lat"): p.lat = data["lat"]
        if data.get("lng"): p.lng = data["lng"]

        self.nb.save_places()
        await redraw_places(self.bot)
        await log_to_places_thread(
            self.bot,
            f"🗺️ `{p.lexi}` Maps link updated by {interaction.user.display_name}"
        )
        await interaction.followup.send(
            f"✅ **{p.name}** updated with fresh Maps data.", ephemeral=True
        )


def build_place_embed(place) -> discord.Embed:
    closed = place.business_status == "CLOSED_PERMANENTLY"
    color  = discord.Color.red() if closed else discord.Color.blurple()
    embed  = discord.Embed(
        title=f"{'⚠️ CLOSED — ' if closed else ''}🍽️ {place.name}",
        color=color,
    )
    embed.add_field(name="Lexi / aliases", value=place.all_aliases_display(), inline=False)
    if place.pricing:      embed.add_field(name="💰 Price",   value=place.pricing,              inline=True)
    if place.primary_type: embed.add_field(name="🏷️ Type",   value=place.primary_type.title(), inline=True)
    if place.phone:        embed.add_field(name="📞 Phone",   value=place.phone,                inline=True)
    if place.address:      embed.add_field(name="📍 Address", value=place.address,              inline=False)
    if place.site:         embed.add_field(name="🌐 Site",    value=place.site,                 inline=False)
    if place.google_maps:  embed.add_field(name="🗺️ Maps",   value=place.google_maps,          inline=False)
    embed.set_footer(
        text=f"Won {place.win_count}x | Last: {place.last_won} | Added by: {place.added_by}"
    )
    return embed


class PlaceCardView(discord.ui.View):
    def __init__(self, place, nb, bot):
        super().__init__(timeout=600)
        self.place = place
        self.nb    = nb
        self.bot   = bot

    @discord.ui.button(label="Edit details ✏️", style=discord.ButtonStyle.primary)
    async def edit_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditPlaceModal(self.place, self.nb, self.bot))

    @discord.ui.button(label="Update Maps 🗺️", style=discord.ButtonStyle.secondary)
    async def update_maps(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(UpdateMapsModal(self.place, self.nb, self.bot))


class PlacesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def nb(self):
        return self.bot.nb

    # ── /placeadd ────────────────────────────────────────────────────────

    @app_commands.command(name="placeadd", description="Add a place to the registry.")
    @app_commands.describe(
        lexi="Short lookup name (required, e.g. innout)",
        maps_link="Google Maps link for auto-enrichment",
        name="Full place name (if no Maps link)",
    )
    async def placeadd(
        self,
        interaction: discord.Interaction,
        lexi: str,
        maps_link: str = "",
        name: str = "",
    ):
        from cogs.session import fetch_place_from_maps, is_maps_url

        norm_lexi = normalize_lexi(lexi)
        if not norm_lexi:
            await interaction.response.send_message("Lexi can't be empty.", ephemeral=True)
            return

        if self.nb.lexi_taken(norm_lexi):
            existing = self.nb.find_by_lexi(norm_lexi)
            label    = f"**{existing.name}**" if existing else "a retired place"
            await interaction.response.send_message(
                f"`{norm_lexi}` is already taken by {label}. Use `/placeview` to edit it.",
                ephemeral=True,
            )
            return

        if maps_link and is_maps_url(maps_link):
            await interaction.response.send_message("📍 Fetching Maps data...", ephemeral=True)
            data = await fetch_place_from_maps(maps_link)
            if not data or not data.get("name"):
                await interaction.followup.send(
                    "Couldn't pull that link. Try again with a name instead.", ephemeral=True
                )
                return
            if data.get("business_status") == "CLOSED_PERMANENTLY":
                await interaction.followup.send(
                    f"⚠️ Google says **{data['name']}** is permanently closed. Adding anyway.",
                    ephemeral=True,
                )
            place = self.nb.add_place(
                name=data["name"], lexi=norm_lexi,
                address=data.get("address", ""),
                google_maps=data.get("google_maps", ""),
                primary_type=data.get("primary_type", ""),
                business_status=data.get("business_status", ""),
                lat=data.get("lat"), lng=data.get("lng"),
                added_by=interaction.user.display_name,
            )
            await interaction.followup.send(
                f"✅ **{place.name}** added as `{place.lexi}`.", ephemeral=True
            )
        else:
            place_name = name.strip() or norm_lexi
            place = self.nb.add_place(
                name=place_name, lexi=norm_lexi,
                added_by=interaction.user.display_name,
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"✅ **{place.name}** added as `{place.lexi}`.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"✅ **{place.name}** added as `{place.lexi}`.", ephemeral=True
                )

        await redraw_places(self.bot)
        await log_to_places_thread(
            self.bot,
            f"✅ `{place.lexi}` — **{place.name}** added by {interaction.user.display_name}"
        )
        log.info(f"placeadd {place.name} ({place.lexi}) by {interaction.user}")

    # ── /placeview ───────────────────────────────────────────────────────

    @app_commands.command(name="placeview", description="View and edit a place.")
    @app_commands.describe(lexi="The place lexi to look up")
    async def placeview(self, interaction: discord.Interaction, lexi: str):
        place = self.nb.find_by_lexi(lexi)
        if not place:
            await interaction.response.send_message(
                f"Don't know `{lexi}`. Check `#places`.", ephemeral=True
            )
            return
        embed = build_place_embed(place)
        view  = PlaceCardView(place, self.nb, self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @placeview.autocomplete("lexi")
    async def placeview_autocomplete(self, interaction: discord.Interaction, current: str):
        places = self.nb.active_places()
        cl     = current.lower()
        return [
            app_commands.Choice(name=f"{p.lexi} — {p.name}", value=p.lexi)
            for p in places
            if not cl or cl in p.lexi or cl in p.name.lower()
        ][:25]

    # ── /placeremove ─────────────────────────────────────────────────────

    @app_commands.command(name="placeremove", description="Permanently remove a place from the registry.")
    @app_commands.describe(lexi="The place lexi to remove")
    async def placeremove(self, interaction: discord.Interaction, lexi: str):
        place = self.nb.find_by_lexi_any(lexi)
        if not place:
            await interaction.response.send_message(f"Don't know `{lexi}`.", ephemeral=True)
            return

        view = ConfirmRemoveView(place, self.nb, self.bot, interaction.user)
        await interaction.response.send_message(
            f"⚠️ Permanently remove **{place.name}**? History gone.\n"
            f"Consider `/placeretire {place.lexi}` to keep history.",
            view=view,
            ephemeral=True,
        )

    @placeremove.autocomplete("lexi")
    async def placeremove_autocomplete(self, interaction: discord.Interaction, current: str):
        places = list(self.nb.places.values())
        cl     = current.lower()
        return [
            app_commands.Choice(
                name=f"{p.lexi} — {p.name}{' (retired)' if not p.active else ''}",
                value=p.lexi
            )
            for p in places
            if not cl or cl in p.lexi or cl in p.name.lower()
        ][:25]

    # ── /placeretire / /placeunretire (admin) ────────────────────────────

    @app_commands.command(name="placeretire", description="(Admin) Soft-retire a place, keeping its history.")
    @app_commands.describe(lexi="The place lexi to retire")
    async def placeretire(self, interaction: discord.Interaction, lexi: str):
        if interaction.user.id != self.bot.admin_id:
            await interaction.response.send_message("🚫 Admin only.", ephemeral=True)
            return
        place = self.nb.find_by_lexi_any(lexi)
        if not place:
            await interaction.response.send_message(f"Don't know `{lexi}`.", ephemeral=True)
            return
        place.active = False
        self.nb.save_places()
        await redraw_places(self.bot)
        await log_to_places_thread(
            self.bot,
            f"🪦 `{place.lexi}` — **{place.name}** retired by {interaction.user.display_name}"
        )
        await interaction.response.send_message(
            f"🪦 **{place.name}** retired. History preserved.", ephemeral=True
        )

    @app_commands.command(name="placeunretire", description="(Admin) Restore a retired place.")
    @app_commands.describe(lexi="The place lexi to restore")
    async def placeunretire(self, interaction: discord.Interaction, lexi: str):
        if interaction.user.id != self.bot.admin_id:
            await interaction.response.send_message("🚫 Admin only.", ephemeral=True)
            return
        place = self.nb.find_by_lexi_any(lexi)
        if not place:
            await interaction.response.send_message(f"Don't know `{lexi}`.", ephemeral=True)
            return
        place.active = True
        self.nb.save_places()
        await redraw_places(self.bot)
        await log_to_places_thread(
            self.bot,
            f"✅ `{place.lexi}` — **{place.name}** restored by {interaction.user.display_name}"
        )
        await interaction.response.send_message(
            f"✅ **{place.name}** restored.", ephemeral=True
        )


class ConfirmRemoveView(discord.ui.View):
    def __init__(self, place, nb, bot, invoker):
        super().__init__(timeout=30)
        self.place   = place
        self.nb      = nb
        self.bot     = bot
        self.invoker = invoker

    @discord.ui.button(label="Yes, remove permanently", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invoker.id:
            await interaction.response.send_message("Not yours to confirm.", ephemeral=True)
            return
        name = self.place.name
        lexi = self.place.lexi
        self.nb.remove_place(self.place.id)
        await redraw_places(self.bot)
        await log_to_places_thread(
            self.bot,
            f"🗑️ `{lexi}` — **{name}** removed by {interaction.user.display_name}"
        )
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"🗑️ **{name}** removed.", view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Cancelled.", view=self)


async def setup(bot):
    await bot.add_cog(PlacesCog(bot))
