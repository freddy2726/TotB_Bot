import discord
from discord import app_commands
from discord.ext import commands
import os, json, pathlib

DATA_DIR = pathlib.Path("data")
DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = DATA_DIR / "selfroles.json"

def load_data():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

class SelfRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild = discord.Object(id=int(os.getenv("GUILD_ID")))
        self.data = load_data()

    # --- Slash commands (admin-only) ---

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_create", description="Erstellt oder aktualisiert ein Self-Role Panel.")
    async def selfroles_create(self, interaction: discord.Interaction,
                               channel: discord.TextChannel,
                               title: str,
                               description: str):
        embed = discord.Embed(title=title, description=description, color=0x5865F2)
        message = await channel.send(embed=embed)

        guild_id = str(interaction.guild.id)
        self.data[guild_id] = {
            "panel_id": message.id,
            "channel_id": channel.id,
            "title": title,
            "description": description,
            "entries": {}  # role_id -> emoji str
        }
        save_data(self.data)
        await interaction.response.send_message("✅ Self-role Panel erstellt.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_bind", description="Bindet ein Emoji an eine Rolle im Panel.")
    async def selfroles_bind(self, interaction: discord.Interaction,
                             emoji: str,
                             role: discord.Role):
        guild_id = str(interaction.guild.id)
        conf = self.data.get(guild_id)
        if not conf:
            await interaction.response.send_message("❌ Kein Panel vorhanden.", ephemeral=True)
            return

        conf["entries"][str(role.id)] = emoji
        save_data(self.data)

        channel = interaction.guild.get_channel(conf["channel_id"])
        message = await channel.fetch_message(conf["panel_id"])
        await message.add_reaction(emoji)

        await interaction.response.send_message(f"✅ {emoji} ↔ {role.name} hinzugefügt.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_unbind", description="Entfernt Emoji/Rolle aus dem Panel.")
    async def selfroles_unbind(self, interaction: discord.Interaction,
                               emoji: str = None,
                               role: discord.Role = None):
        guild_id = str(interaction.guild.id)
        conf = self.data.get(guild_id)
        if not conf:
            await interaction.response.send_message("❌ Kein Panel vorhanden.", ephemeral=True)
            return

        removed = False
        if role:
            conf["entries"].pop(str(role.id), None)
            removed = True
        if emoji:
            for rid, em in list(conf["entries"].items()):
                if em == emoji:
                    conf["entries"].pop(rid, None)
                    removed = True

        save_data(self.data)
        await interaction.response.send_message("✅ Zuordnung entfernt." if removed else "❌ Nichts entfernt.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="selfroles_list", description="Zeigt aktuelle Self-Role-Zuordnungen.")
    async def selfroles_list(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        conf = self.data.get(guild_id)
        if not conf or not conf["entries"]:
            await interaction.response.send_message("Keine Zuordnungen vorhanden.", ephemeral=True)
            return

        lines = [f"{em} → <@&{rid}>" for rid, em in conf["entries"].items()]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # --- Reaction handling ---

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        guild_id = str(payload.guild_id)
        conf = self.data.get(guild_id)
        if not conf or payload.message_id != conf.get("panel_id"):
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        if member.bot:
            return

        for rid, em in conf["entries"].items():
            if str(payload.emoji) == em:
                role = guild.get_role(int(rid))
                if role:
                    await member.add_roles(role, reason="SelfRole add")
                break

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        guild_id = str(payload.guild_id)
        conf = self.data.get(guild_id)
        if not conf or payload.message_id != conf.get("panel_id"):
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        if not member:
            return

        for rid, em in conf["entries"].items():
            if str(payload.emoji) == em:
                role = guild.get_role(int(rid))
                if role:
                    await member.remove_roles(role, reason="SelfRole remove")
                break

    async def cog_load(self):
        self.bot.tree.add_command(self.selfroles_create, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_bind, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_unbind, guild=self.guild)
        self.bot.tree.add_command(self.selfroles_list, guild=self.guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(SelfRoles(bot))