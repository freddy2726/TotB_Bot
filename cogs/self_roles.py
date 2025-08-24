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
    gibt einen (key, display)-Tuple zurück:
      - key:   "u:😄"  (Unicode) oder "c:123456789012345678" (Custom)
      - display: String, der im UI/Embed angezeigt wird (Unicode char oder <:name:id>)
    """
    emoji_str = emoji_str.strip()

    # Custom: <a:name:id> oder <:name:id>
    if emoji_str.startswith("<") and emoji_str.endswith(">"):
        # Wir versuchen, die ID herauszulösen
        parts = emoji_str.strip("<>").split(":")
        if len(parts) == 3:
            # parts = ['a' oder '', name, id]
            _a_or_colon, _name, _id = parts
            if _id.isdigit():
                return (f"c:{_id}", emoji_str)
    # Unicode
    return (f"u:{emoji_str}", emoji_str)

def normalize_emoji_from_payload(payload_emoji: discord.PartialEmoji) -> str:
    """
    Nimmt payload.emoji und liefert den key wie oben beschrieben.
    """
    if payload_emoji.is_custom_emoji():
        # Custom mit ID
        if payload_emoji.id:
            return f"c:{payload_emoji.id}"
    # Unicode (name enthält das Zeichen)
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
    Prüft, ob die Top-Rolle des Bots über der Ziel-Rolle liegt.
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
        # discord.py akzeptiert Strings ("😄" oder "<:n:id>") oder PartialEmoji.from_str(...)
        await message.add_reaction(display_emoji)
    except discord.HTTPException:
        # Ignorieren – z.B. wenn der Bot kein Use External Emojis hat oder Emoji ungültig
        pass

# ------------------------------
# Cog
# ------------------------------
class SelfRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild = discord.Object(id=int(os.getenv("GUILD_ID")))
        self.data = load_data()

    # --------------------------
    # Slash Commands (Admin)
    # --------------------------
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_create", description="Erstellt oder aktualisiert ein Self-Role Panel.")
    @app_commands.describe(
        channel="Channel, in dem das Panel stehen soll",
        title="Titel des Panels",
        description="Beschreibung (z.B. Regeln oder Hinweise)"
    )
    async def selfroles_create(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str
    ):
        embed = discord.Embed(title=title, description=description, color=0x5865F2)
        message = await channel.send(embed=embed)

        guild_id = str(interaction.guild.id)
        self.data[guild_id] = {
            "panel_id": message.id,
            "channel_id": channel.id,
            "title": title,
            "description": description,
            # entries: role_id -> {"key": "u:😄" / "c:123", "display": "😄" / "<:name:id>"}
            "entries": {}
        }
        save_data(self.data)
        await interaction.response.send_message("✅ Self-role Panel erstellt.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_bind", description="Bindet ein Emoji an eine Rolle im Panel.")
    @app_commands.describe(
        emoji="Unicode (😄) oder Custom (<:name:id>)",
        role="Rolle, die vergeben/entfernt werden soll"
    )
    async def selfroles_bind(self, interaction: discord.Interaction, emoji: str, role: discord.Role):
        guild_id = str(interaction.guild.id)
        conf = self.data.get(guild_id)
        if not conf:
            await interaction.response.send_message("❌ Kein Panel vorhanden. Erst `/selfroles_create` ausführen.", ephemeral=True)
            return

        # Sicherheitscheck: Bot kann diese Rolle überhaupt verwalten?
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
            await interaction.response.send_message("⚠️ Panel-Nachricht wurde nicht gefunden. Bitte neu erstellen.", ephemeral=True)
            return

        await add_panel_reaction(message, display)
        # Optional: Panel-Embed aktualisieren
        await self._refresh_panel_embed(interaction.guild)

        await interaction.response.send_message(f"✅ {display} ↔ {role.mention} hinzugefügt.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_unbind", description="Entfernt Emoji/Rolle aus dem Panel.")
    @app_commands.describe(
        emoji="(optional) Unicode (😄) oder Custom (<:name:id>)",
        role="(optional) Rolle, die entfernt werden soll"
    )
    async def selfroles_unbind(self, interaction: discord.Interaction, emoji: Optional[str] = None, role: Optional[discord.Role] = None):
        guild_id = str(interaction.guild.id)
        conf = self.data.get(guild_id)
        if not conf:
            await interaction.response.send_message("❌ Kein Panel vorhanden.", ephemeral=True)
            return

        entries = conf.get("entries", {})
        removed = False

        # Entfernen nach Rolle
        if role and str(role.id) in entries:
            entries.pop(str(role.id), None)
            removed = True

        # Entfernen nach Emoji
        if emoji:
            key_to_remove, _display = normalize_emoji_from_str(emoji)
            for rid, info in list(entries.items()):
                if info.get("key") == key_to_remove:
                    entries.pop(rid, None)
                    removed = True

        conf["entries"] = entries
        save_data(self.data)

        # Optional: Panel-Embed aktualisieren
        await self._refresh_panel_embed(interaction.guild)

        await interaction.response.send_message("✅ Zuordnung entfernt." if removed else "❌ Nichts entfernt.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_list", description="Zeigt aktuelle Self-Role-Zuordnungen.")
    async def selfroles_list(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        conf = self.data.get(guild_id)
        entries = (conf or {}).get("entries", {})
        if not entries:
            await interaction.response.send_message("Keine Zuordnungen vorhanden.", ephemeral=True)
            return

        lines = []
        for rid, info in entries.items():
            display = info.get("display", "❓")
            lines.append(f"{display} → <@&{rid}>")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_refresh", description="Aktualisiert das Panel-Embed mit der aktuellen Emoji→Rolle-Liste.")
    async def selfroles_refresh(self, interaction: discord.Interaction):
        await self._refresh_panel_embed(interaction.guild)
        await interaction.response.send_message("🔄 Panel aktualisiert.", ephemeral=True)

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

        guild_id = str(payload.guild_id)
        conf = self.data.get(guild_id)
        if not conf or payload.message_id != conf.get("panel_id"):
            return

        member = await resolve_member(guild, payload.user_id)
        if member is None or member.bot:
            return

        target_key = normalize_emoji_from_payload(payload.emoji)

        # Finde die passende Rolle
        for rid, info in conf.get("entries", {}).items():
            if info.get("key") == target_key:
                role = guild.get_role(int(rid))
                if role is None:
                    continue
                if not can_assign_role(guild, role):
                    continue
                try:
                    await member.add_roles(role, reason="SelfRole add")
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass
                break

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        guild_id = str(payload.guild_id)
        conf = self.data.get(guild_id)
        if not conf or payload.message_id != conf.get("panel_id"):
            return

        member = await resolve_member(guild, payload.user_id)
        if member is None:
            return

        target_key = normalize_emoji_from_payload(payload.emoji)

        # Finde die passende Rolle
        for rid, info in conf.get("entries", {}).items():
            if info.get("key") == target_key:
                role = guild.get_role(int(rid))
                if role is None:
                    continue
                if not can_assign_role(guild, role):
                    continue
                try:
                    await member.remove_roles(role, reason="SelfRole remove")
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass
                break

    # --------------------------
    # Interne Helfer
    # --------------------------
    async def _refresh_panel_embed(self, guild: discord.Guild) -> None:
        """
        Aktualisiert das Panel-Embed, sodass es die aktuelle Emoji→Rolle-Liste zeigt.
        """
        conf = self.data.get(str(guild.id))
        if not conf:
            return
        channel = guild.get_channel(conf.get("channel_id"))
        if channel is None:
            return
        try:
            message = await channel.fetch_message(conf.get("panel_id"))
        except discord.NotFound:
            return
        except discord.HTTPException:
            return

        # Build description
        desc = conf.get("description") or ""
        entries = conf.get("entries", {})
        if entries:
            desc_list = []
            for rid, info in entries.items():
                display = info.get("display", "❓")
                desc_list.append(f"{display} → <@&{rid}>")
            desc += ("\n\n" if desc else "") + "\n".join(desc_list)

        embed = discord.Embed(
            title=conf.get("title") or "Self-Roles",
            description=desc,
            color=0x5865F2
        )
        try:
            await message.edit(embed=embed)
        except discord.HTTPException:
            pass

    async def cog_load(self):
        self.bot.tree.add_command(self.selfroles_create, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_bind, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_unbind, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_list, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_refresh, guild=self.guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(SelfRoles(bot))
