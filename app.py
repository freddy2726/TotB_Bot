import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio

# ENV laden
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TEST_GUILD_ID = int(os.getenv("GUILD_ID"))

# Bot Setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        guild = discord.Object(id=TEST_GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} command(s) to guild {TEST_GUILD_ID}")
    except Exception as e:
        print(f"Slash command sync failed: {e}")

async def main():
    await bot.load_extension("cogs.basic")
    await bot.load_extension("cogs.embed_creator")
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
