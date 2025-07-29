import discord
from discord import app_commands
from discord.ext import commands
import os

class Basic(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild = discord.Object(id=int(os.getenv("GUILD_ID")))  # Für Test-Guild

    @app_commands.command(name="ping", description="Antwortet mit pong.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("pong")

    @app_commands.command(name="hilfe", description="Antwortet mit Hilfetext.")
    async def hilfe(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hilfetext")

    async def cog_load(self):
        self.bot.tree.add_command(self.ping, guild=self.guild)
        self.bot.tree.add_command(self.hilfe, guild=self.guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(Basic(bot))
