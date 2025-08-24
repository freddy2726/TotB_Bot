# cogs/self_roles.py
import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import pathlib
from typing import Dict, Any, Optional, Tuple

DATA_DIR = pathlib.Path("data")
DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = DATA_DIR / "selfroles.json"

# ------------------------------
# Persistenz
# ------------------------------
def load_data() -> Dict[str, Any]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_data(data: Dict[str, Any]) -> None:
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

# ------------------------------
# Emoji Normalisierung / Utils
# ------------------------------
def normalize_emoji_from_str(emoji_str: str) -> Tuple[str, str]:
    """
    Nimmt Slash-Command-Eingabe (z.B. "😄" oder "<:name:123456789012345678>") und
    gibt (key, display) zurück:
      - key:   "u:😄"  (Unicode) oder "c:123456789012345678" (Custom)
      - display: String für UI/Embed (Unicode oder <:name:id>)
    """
    emoji_str = emoji_str.strip()

    # Custom: <a:name:id> oder <:name:id>
    if emoji_str.startswith("<") and emoji_str.endswith(">"):
        parts = emoji_str.strip("<>").split(":")
        if len(parts) == 3:
            _prefix, _name, _id = parts
            if _id.isdigit():
                return (f"c:{_id}", emoji_str)
    # Unicode
    return (f"u:{emoji_str}", emoji_str)

def normalize_emoji_from_payload(payload_emoji: discord.PartialEmoji) -> str:
    """
    Nimmt payload.emoji und liefert den key wie oben beschrieben.
    """
    if payload_emoji.is_custom_emoji():
        if payload_emoji.id:
            return f"c:{payload_emoji.id}"
    return f"u:{payload_emoji.name or ''}"

async def resolve_member(guild: discord.Guild, user_id: int) -> Optional[discord.Member]:
    """
    Holt Member zuverlässig: erst Cache, dann API.
    """
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except discord.NotFound:
            return None
        except discord.HTTPException:
            return None
    return member

def can_assign_role(guild: discord.Guild, role: discord.Role) -> bool:
    """
    Prüft, ob die Bot-Toprolle über der Zielrolle liegt.
    """
    me = guild.me
    if not me:
        return False
    return me.top_role > role

async def add_panel_reaction(message: discord.Message, display_emoji: str) -> None:
    """
    Fügt der Panel-Message die passende Reaction hinzu (Unicode oder Custom).
    """
    try:
        await message.add_reaction(display_emoji)
    except discord.HTTPException:
        pass

# ------------------------------
# Cog
# ------------------------------
class SelfRoles(commands.Cog):
    """
    Datenstruktur (pro Guild):
    data[guild_id] = {
        "selectors": {
            "<name>": {
                "panel_id": int,
                "channel_id": int,
                "title": str,
                "description": str,
                "entries": { "<role_id>": {"key": "u:😄"/"c:123", "display": "..."} }
            },
            ...
        }
    }
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild = discord.Object(id=int(os.getenv("GUILD_ID")))
        self.data = load_data()

    # --------------------------
    # Helpers für Selector-Zugriff
    # --------------------------
    def _g(self, guild: discord.Guild) -> Dict[str, Any]:
        gid = str(guild.id)
        if gid not in self.data:
            self.data[gid] = {"selectors": {}}
        return self.data[gid]

    def _get_selector(self, guild: discord.Guild, name: str) -> Optional[Dict[str, Any]]:
        return self._g(guild)["selectors"].get(name)

    def _find_selector_by_message(self, guild: discord.Guild, message_id: int) -> Optional[Tuple[str, Dict[str, Any]]]:
        for name, sel in self._g(guild)["selectors"].items():
            if sel.get("panel_id") == message_id:
                return name, sel
        return None

    async def _refresh_panel_embed(self, guild: discord.Guild, name: Optional[str] = None) -> None:
        """
        Aktualisiert 1 Selector (wenn name gesetzt) oder alle Selector-Embeds.
        """
        store = self._g(guild)["selectors"]
        items = [(name, store.get(name))] if name else list(store.items())

        for sel_name, conf in items:
            if not conf:
                continue
            channel = guild.get_channel(conf.get("channel_id"))
            if channel is None:
                continue
            try:
                message = await channel.fetch_message(conf.get("panel_id"))
            except discord.NotFound:
                continue
            except discord.HTTPException:
                continue

            desc = conf.get("description") or ""
            entries = conf.get("entries", {})
            if entries:
                lines = []
                for rid, info in entries.items():
                    lines.append(f'{info.get("display", "❓")} → <@&{rid}>')
                desc = (desc + "\n\n" if desc else "") + "\n".join(lines)

            embed = discord.Embed(
                title=conf.get("title") or f"Self-Roles: {sel_name}",
                description=desc,
                color=0x5865F2
            )
            try:
                await message.edit(embed=embed)
            except discord.HTTPException:
                pass

    # --------------------------
    # Slash Commands (Admin only)
    # --------------------------
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_create", description="Erstellt/aktualisiert einen Selector (Panel).")
    @app_commands.describe(
        name="Eindeutiger Name des Selectors (z.B. games, pings)",
        channel="Channel, in dem das Panel stehen soll",
        title="Titel des Panels",
        description="Beschreibung (z.B. Hinweise/Regeln im Panel)"
    )
    async def selfroles_create(
        self,
        interaction: discord.Interaction,
        name: str,
        channel: discord.TextChannel,
        title: str,
        description: str
    ):
        gstore = self._g(interaction.guild)
        selectors = gstore["selectors"]

        # Neu posten (immer neu, damit panel_id aktuell ist)
        embed = discord.Embed(title=title, description=description, color=0x5865F2)
        message = await channel.send(embed=embed)

        selectors[name] = {
            "panel_id": message.id,
            "channel_id": channel.id,
            "title": title,
            "description": description,
            "entries": selectors.get(name, {}).get("entries", {})  # Falls es schon Einträge gab, beibehalten
        }
        save_data(self.data)
        await interaction.response.send_message(f"✅ Selector **{name}** erstellt/aktualisiert.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_bind", description="Bindet Emoji↔Rolle an einen Selector.")
    @app_commands.describe(
        name="Name des Selectors",
        emoji="Unicode (😄) oder Custom (<:name:id>)",
        role="Rolle, die vergeben/entfernt werden soll"
    )
    async def selfroles_bind(self, interaction: discord.Interaction, name: str, emoji: str, role: discord.Role):
        conf = self._get_selector(interaction.guild, name)
        if not conf:
            await interaction.response.send_message("❌ Selector nicht gefunden. Nutze zuerst `/selfroles_create`.", ephemeral=True)
            return

        if not can_assign_role(interaction.guild, role):
            await interaction.response.send_message("❌ Ich kann diese Rolle nicht verwalten (Hierarchie).", ephemeral=True)
            return

        key, display = normalize_emoji_from_str(emoji)
        conf["entries"][str(role.id)] = {"key": key, "display": display}
        save_data(self.data)

        channel = interaction.guild.get_channel(conf["channel_id"])
        try:
            message = await channel.fetch_message(conf["panel_id"])
        except discord.NotFound:
            await interaction.response.send_message("⚠️ Panel-Nachricht wurde nicht gefunden. Bitte Selector neu erstellen.", ephemeral=True)
            return

        await add_panel_reaction(message, display)
        await self._refresh_panel_embed(interaction.guild, name=name)

        await interaction.response.send_message(f"✅ {display} ↔ {role.mention} in **{name}** hinzugefügt.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_unbind", description="Entfernt Emoji/Rolle aus einem Selector.")
    @app_commands.describe(
        name="Name des Selectors",
        emoji="(optional) Unicode (😄) oder Custom (<:name:id>)",
        role="(optional) Rolle, die entfernt werden soll"
    )
    async def selfroles_unbind(self, interaction: discord.Interaction, name: str, emoji: Optional[str] = None, role: Optional[discord.Role] = None):
        conf = self._get_selector(interaction.guild, name)
        if not conf:
            await interaction.response.send_message("❌ Selector nicht gefunden.", ephemeral=True)
            return

        entries = conf.get("entries", {})
        removed = False

        if role and str(role.id) in entries:
            entries.pop(str(role.id), None)
            removed = True

        if emoji:
            key_to_remove, _disp = normalize_emoji_from_str(emoji)
            for rid, info in list(entries.items()):
                if info.get("key") == key_to_remove:
                    entries.pop(rid, None)
                    removed = True

        conf["entries"] = entries
        save_data(self.data)
        await self._refresh_panel_embed(interaction.guild, name=name)

        await interaction.response.send_message(
            f"{'✅' if removed else '❌'} {'Zuordnung(en) entfernt' if removed else 'Nichts entfernt'} in **{name}**.",
            ephemeral=True
        )

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_list", description="Listet alle Selector oder deren Zuordnungen.")
    @app_commands.describe(
        name="(optional) Name des Selectors – zeigt dessen Einträge, sonst alle Selector"
    )
    async def selfroles_list(self, interaction: discord.Interaction, name: Optional[str] = None):
        gstore = self._g(interaction.guild)
        selectors = gstore["selectors"]

        if not selectors:
            await interaction.response.send_message("Keine Selector vorhanden.", ephemeral=True)
            return

        if name:
            conf = selectors.get(name)
            if not conf:
                await interaction.response.send_message("Selector nicht gefunden.", ephemeral=True)
                return
            entries = conf.get("entries", {})
            if not entries:
                await interaction.response.send_message(f"**{name}**: (keine Zuordnungen)", ephemeral=True)
                return
            lines = [f'{info.get("display","❓")} → <@&{rid}>' for rid, info in entries.items()]
            await interaction.response.send_message(f"**{name}**\n" + "\n".join(lines), ephemeral=True)
        else:
            lines = []
            for sel_name, conf in selectors.items():
                entries = conf.get("entries", {})
                lines.append(f"• **{sel_name}** — {len(entries)} Einträge, Channel <#{conf.get('channel_id')}>")
            await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_refresh", description="Aktualisiert 1 Selector oder alle Panels.")
    @app_commands.describe(
        name="(optional) Name des Selectors – nur diesen aktualisieren"
    )
    async def selfroles_refresh(self, interaction: discord.Interaction, name: Optional[str] = None):
        await self._refresh_panel_embed(interaction.guild, name=name)
        await interaction.response.send_message("🔄 Panel(s) aktualisiert.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_delete", description="Löscht einen Selector (Panel bleibt unberührt).")
    @app_commands.describe(
        name="Name des Selectors"
    )
    async def selfroles_delete(self, interaction: discord.Interaction, name: str):
        gstore = self._g(interaction.guild)
        if name in gstore["selectors"]:
            gstore["selectors"].pop(name, None)
            save_data(self.data)
            await interaction.response.send_message(f"🗑️ Selector **{name}** gelöscht.", ephemeral=True)
        else:
            await interaction.response.send_message("Selector nicht gefunden.", ephemeral=True)

    # --------------------------
    # Reaction Handling
    # --------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        # Welcher Selector?
        found = self._find_selector_by_message(guild, payload.message_id)
        if not found:
            return
        sel_name, conf = found

        member = await resolve_member(guild, payload.user_id)
        if member is None or member.bot:
            return

        target_key = normalize_emoji_from_payload(payload.emoji)

        for rid, info in conf.get("entries", {}).items():
            if info.get("key") == target_key:
                role = guild.get_role(int(rid))
                if role is None:
                    continue
                if not can_assign_role(guild, role):
                    continue
                try:
                    await member.add_roles(role, reason=f"SelfRole add ({sel_name})")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                break

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        found = self._find_selector_by_message(guild, payload.message_id)
        if not found:
            return
        sel_name, conf = found

        member = await resolve_member(guild, payload.user_id)
        if member is None:
            return

        target_key = normalize_emoji_from_payload(payload.emoji)

        for rid, info in conf.get("entries", {}).items():
            if info.get("key") == target_key:
                role = guild.get_role(int(rid))
                if role is None:
                    continue
                if not can_assign_role(guild, role):
                    continue
                try:
                    await member.remove_roles(role, reason=f"SelfRole remove ({sel_name})")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                break

    async def cog_load(self):
        self.bot.tree.add_command(self.selfroles_create, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_bind, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_unbind, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_list, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_refresh, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_delete, guild=self.guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(SelfRoles(bot))
