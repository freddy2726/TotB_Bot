import discord # type: ignore
from discord import app_commands # type: ignore
from discord.ext import commands # type: ignore
from dotenv import load_dotenv # type: ignore
import os

# --- ENV VARIABLEN LADEN ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TEST_GUILD_ID = int(os.getenv("GUILD_ID"))

# --- BOT SETUP ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

# --- SLASH COMMANDS ---
@bot.tree.command(name="ping", description="Antwortet mit pong.")
async def ping_command(interaction: discord.Interaction):
    await interaction.response.send_message("pong")

@bot.tree.command(name="hilfe", description="Antwortet mit Hilfetext.")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message("Hilfetext")

# --- BEIM STARTEN: COMMANDS NUR IN DER TEST-GUILD SYNCEN ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    try:
        guild = discord.Object(id=TEST_GUILD_ID)
        synced = await bot.tree.sync(guild=guild)  # Nur in Test-Guild
        print(f"Synced {len(synced)} command(s) to guild {TEST_GUILD_ID}")
    except Exception as e:
        print(f"Slash command sync failed: {e}")

# --- BOT STARTEN ---
bot.run(TOKEN)
