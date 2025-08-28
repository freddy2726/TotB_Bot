import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import aiomysql

# ENV
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TEST_GUILD_ID = int(os.getenv("GUILD_ID"))
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")

# Bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True
intents.voice_states = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Events
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        guild = discord.Object(id=TEST_GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        print(f"🔁 Synced {len(synced)} command(s) to guild {TEST_GUILD_ID}")
    except Exception as e:
        print(f"Slash command sync failed: {e}")

# DB
async def setup_db_pool():
    bot.db_pool = await aiomysql.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        autocommit=True,
        charset="utf8mb4"
    )
    print("🗄️  MySQL pool ready")

# Main
async def main():
    async with bot:
        await setup_db_pool()
        await bot.load_extension("cogs.basic")
        await bot.load_extension("cogs.embed_creator")
        await bot.load_extension("cogs.self_roles")
        await bot.load_extension("cogs.welcome")
        await bot.load_extension("cogs.leveling")
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
