import discord
from discord import app_commands
from discord.ext import commands
import os



class Basic(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Für Test-Guild
        self.guild = discord.Object(id=int(os.getenv("GUILD_ID")))

    @app_commands.command(name="ping", description="Antwortet mit pong.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("pong")

    @app_commands.command(name="hilfe", description="Zeigt eine Übersicht aller verfügbaren Funktionen.")
    async def hilfe(self, interaction: discord.Interaction):
        help_text = (
            "• `/ping` – prüft, ob der Bot online ist.\n"
            "• `/hilfe` – zeigt diese Hilfe an.\n"
            "\n"
            "🔑 **Admin only:**\n"
            "• `/create_embed` – erstellt ein Embed mit Titel, Farbe, Bild, Thumbnail.\n"
            "• `/selfroles_create` – erstellt oder aktualisiert ein Panel.\n"
            "• `/selfroles_bind` – bindet Emoji → Rolle.\n"
            "• `/selfroles_unbind` – entfernt Bindungen.\n"
            "• `/selfroles_list` – zeigt aktuelle Bindungen.\n"
            "• `/selfroles_refresh` – aktualisiert Panel-Embed(s).\n"
            "• `/selfroles_delete` – löscht einen Selector (Panel bleibt bestehen).\n"
            "\n"
            "👋 **Welcome System:**\n"
            "Neue Mitglieder werden automatisch im Willkommens-Channel begrüßt.\n"
            )
        await interaction.response.send_message(help_text)

    async def cog_load(self):
        # Befehle beim Guild-spezifischen Command Tree registrieren
        self.bot.tree.add_command(self.ping, guild=self.guild)
        self.bot.tree.add_command(self.hilfe, guild=self.guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(Basic(bot))
