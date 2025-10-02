from __future__ import annotations
import asyncio
import random
import time
from dataclasses import dataclass
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import os
import aiomysql
import discord
from discord import app_commands
from discord.ext import commands, tasks

# ========================= KONFIGURATION =========================
# Kanal, in dem Nutzer ihren Level anfragen dürfen und wo wir auch Level-Ups & die Rangliste posten
LEVEL_QUERY_CHANNEL_ID = 1410717838855114793
LEVEL_ANNOUNCE_CHANNEL_ID = LEVEL_QUERY_CHANNEL_ID

# ⬇️ NEU: Preise-Kanal + Admin-Rolle (eintragen)
LEVEL_PRIZES_CHANNEL_ID = 1423388175073673246   # z.B. 345678901234567890
ADMIN_ROLE_ID = 1397894964427493417           # z.B. 456789012345678901
SEND_WINNER_DM = False                         # optional

# Voice-Channel, der KEINE Voice-XP vergeben soll
EXCLUDED_VOICE_CHANNEL_ID = 1410703819947638855

# XP-Einstellungen
MESSAGE_XP_MIN = 15
MESSAGE_XP_MAX = 25
MESSAGE_COOLDOWN_SECONDS = 60  # Anti-Spam

VOICE_XP_PER_MINUTE = 5        # XP pro Minute in einem nicht ausgeschlossenen Voice-Channel
VOICE_XP_TICK_SECONDS = 60     # Intervall der Hintergrundaufgabe

# Rangliste täglich um 08:00 Uhr (Europe/Zurich)
LEADERBOARD_POST_HOUR = 8
LEADERBOARD_POST_MINUTE = 0
LEADERBOARD_TIMEZONE = ZoneInfo("Europe/Zurich")
LEADERBOARD_SIZE = 10

# ========================= HILFSKLASSEN =========================
@dataclass
class Profile:
    user_id: int
    xp: int
    level: int
    last_msg_ts: float


def xp_for_next_level(level: int) -> int:
    """XP von Level L zu L+1 (Mee6-ähnliche Kurve)."""
    return 5 * (level ** 2) + 50 * level + 100


def total_xp_at_level(level: int) -> int:
    total = 0
    for l in range(level):
        total += xp_for_next_level(l)
    return total


def combined_score(level: int, xp_in_level: int) -> int:
    return total_xp_at_level(level) + xp_in_level


class Leveling(commands.Cog):
    """Level-/XP-System für Nachrichten + Voice, **MySQL/aiomysql**, deutsche Meldungen und tägliche Rangliste."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_xp_task.start()
        self.daily_leaderboard_task.start()
        # DB-Struktur sicherstellen
        self.bot.loop.create_task(self._ensure_schema())

    # -------------------- DB Utilities --------------------
    @property
    def pool(self) -> aiomysql.Pool:
        return getattr(self.bot, "db_pool")

    async def _ensure_schema(self):
        await self.bot.wait_until_ready()
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Basistabelle
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        xp INT NOT NULL DEFAULT 0,
                        level INT NOT NULL DEFAULT 0,
                        last_msg_ts DOUBLE DEFAULT 0
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                # Level-10-Flag robust nachziehen (erst prüfen, dann alter)
                try:
                    await cur.execute("SELECT level10_rewarded FROM users LIMIT 1;")
                except Exception:
                    try:
                        await cur.execute(
                            "ALTER TABLE users ADD COLUMN level10_rewarded TINYINT(1) NOT NULL DEFAULT 0;"
                        )
                    except Exception:
                        # Falls alter aus irgendeinem Grund nicht geht, fahren wir ohne Hard-Guarantee fort
                        pass

    async def get_profile(self, user_id: int) -> Profile:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id, xp, level, COALESCE(last_msg_ts, 0) FROM users WHERE user_id=%s",
                    (user_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    await cur.execute(
                        "INSERT INTO users (user_id, xp, level, last_msg_ts) VALUES (%s, 0, 0, 0)",
                        (user_id,),
                    )
                    return Profile(user_id=user_id, xp=0, level=0, last_msg_ts=0)
                return Profile(user_id=int(row[0]), xp=int(row[1]), level=int(row[2]), last_msg_ts=float(row[3] or 0))

    async def add_xp(self, user_id: int, amount: int) -> Tuple[int, int, bool]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT xp, level FROM users WHERE user_id=%s", (user_id,))
                row = await cur.fetchone()
                if row is None:
                    xp = 0
                    level = 0
                    await cur.execute("INSERT INTO users (user_id, xp, level) VALUES (%s, %s, %s)", (user_id, 0, 0))
                else:
                    xp = int(row[0] or 0)
                    level = int(row[1] or 0)

                xp += amount
                leveled_up = False
                while xp >= xp_for_next_level(level):
                    xp -= xp_for_next_level(level)
                    level += 1
                    leveled_up = True

                await cur.execute("UPDATE users SET xp=%s, level=%s WHERE user_id=%s", (xp, level, user_id))
                return xp, level, leveled_up

    async def update_last_message_ts(self, user_id: int, ts: float):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE users SET last_msg_ts=%s WHERE user_id=%s", (ts, user_id))

    async def top_users(self, limit: int = LEADERBOARD_SIZE) -> List[Profile]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT user_id, xp, level, COALESCE(last_msg_ts, 0) FROM users")
                rows = await cur.fetchall()
        profiles = [Profile(int(r[0]), int(r[1] or 0), int(r[2] or 0), float(r[3] or 0)) for r in rows]
        profiles.sort(key=lambda p: combined_score(p.level, p.xp), reverse=True)
        return profiles[:limit]

    # ---- Reward-Helpers (Level 10) ----
    async def _already_rewarded_level10(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                try:
                    await cur.execute("SELECT level10_rewarded FROM users WHERE user_id=%s", (user_id,))
                    row = await cur.fetchone()
                    if not row:
                        return False
                    return bool(row[0])
                except Exception:
                    # Spalte fehlt -> als nicht rewarded behandeln
                    return False

    async def _mark_rewarded_level10(self, user_id: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                try:
                    await cur.execute(
                        "UPDATE users SET level10_rewarded=1 WHERE user_id=%s",
                        (user_id,)
                    )
                except Exception:
                    # Spalte fehlt -> still weitermachen
                    pass

    # -------------------- Events --------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        now = time.time()
        profile = await self.get_profile(message.author.id)
        if now - (profile.last_msg_ts or 0) < MESSAGE_COOLDOWN_SECONDS:
            return

        amount = random.randint(MESSAGE_XP_MIN, MESSAGE_XP_MAX)
        old_level = profile.level
        new_xp, new_level, leveled = await self.add_xp(message.author.id, amount)
        await self.update_last_message_ts(message.author.id, now)

        if leveled:
            await self._announce_level_up(message.guild, message.author, new_level)

            # ⬇️ Sonderfall: Crossing Level 10
            if old_level < 10 <= new_level:
                await self._handle_level10_reward(message.guild, message.author, new_level)

    # -------------------- Voice-XP-Task --------------------
    @tasks.loop(seconds=VOICE_XP_TICK_SECONDS)
    async def voice_xp_task(self):
        await self.bot.wait_until_ready()
        for guild in list(self.bot.guilds):
            try:
                for vc in guild.voice_channels:
                    if vc.id == EXCLUDED_VOICE_CHANNEL_ID:
                        continue
                    if not vc.members:
                        continue
                    for member in vc.members:
                        if member.bot:
                            continue
                        # Level vor XP-Änderung holen, damit wir "Crossing" erkennen
                        profile = await self.get_profile(member.id)
                        old_level = profile.level

                        _xp, level, leveled = await self.add_xp(member.id, VOICE_XP_PER_MINUTE)
                        if leveled:
                            await self._announce_level_up(guild, member, level)
                            if old_level < 10 <= level:
                                await self._handle_level10_reward(guild, member, level)
            except Exception as e:
                print(f"[voice_xp_task] Fehler in Guild {guild.id}: {e}")

    @voice_xp_task.before_loop
    async def before_voice_xp_task(self):
        await self.bot.wait_until_ready()

    # -------------------- Rangliste: täglich um 08:00 --------------------
    @tasks.loop(seconds=60)
    async def daily_leaderboard_task(self):
        await self.bot.wait_until_ready()
        now = datetime.now(LEADERBOARD_TIMEZONE)
        target = now.replace(hour=LEADERBOARD_POST_HOUR, minute=LEADERBOARD_POST_MINUTE, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        await self._post_leaderboard_to_all_guilds()

    @daily_leaderboard_task.before_loop
    async def before_daily_leaderboard_task(self):
        await self.bot.wait_until_ready()

    async def _post_leaderboard_to_all_guilds(self):
        for guild in list(self.bot.guilds):
            channel = guild.get_channel(LEVEL_ANNOUNCE_CHANNEL_ID)  # type: ignore
            if isinstance(channel, discord.TextChannel):
                try:
                    embed = await self._build_leaderboard_embed(guild)
                    if embed:
                        await channel.send(embed=embed)
                except Exception as e:
                    print(f"[leaderboard] Fehler in Guild {guild.id}: {e}")

    async def _build_leaderboard_embed(self, guild: discord.Guild) -> Optional[discord.Embed]:
        top = await self.top_users()
        if not top:
            return None
        lines = []
        for i, p in enumerate(top, start=1):
            try:
                member = guild.get_member(p.user_id) or await guild.fetch_member(p.user_id)
                mtxt = member.mention if member else f"<@{p.user_id}>"
            except Exception:
                mtxt = f"<@{p.user_id}>"
            score = combined_score(p.level, p.xp)
            lines.append(f"**#{i}** — {mtxt} • Level {p.level} • {p.xp} XP (Gesamt: {score})")
        embed = discord.Embed(
            title="🏆 Tages-Rangliste",
            description="\n".join(lines),
            color=discord.Color.gold(),
            timestamp=datetime.now(tz=LEADERBOARD_TIMEZONE)
        )
        embed.set_footer(text="Nächste Aktualisierung morgen um 08:00")
        return embed

    # -------------------- Befehle --------------------
    @app_commands.command(name="level", description="Zeige dein aktuelles Level und den XP-Fortschritt.")
    async def level_slash(self, interaction: discord.Interaction, mitglied: Optional[discord.Member] = None):
        if interaction.channel_id != LEVEL_QUERY_CHANNEL_ID:
            return await interaction.response.send_message(
                f"Bitte benutze diesen Befehl in <#{LEVEL_QUERY_CHANNEL_ID}>.", ephemeral=True
            )
        target = mitglied or interaction.user
        profile = await self.get_profile(target.id)
        need = xp_for_next_level(profile.level)
        embed = discord.Embed(title=f"Level von {target.display_name}", color=discord.Color.blurple())
        embed.add_field(name="Level", value=str(profile.level))
        embed.add_field(name="XP", value=f"{profile.xp} / {need}")
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rangliste", description="Zeigt die aktuelle Rangliste.")
    async def leaderboard_slash(self, interaction: discord.Interaction):
        if interaction.channel_id != LEVEL_QUERY_CHANNEL_ID:
            return await interaction.response.send_message(
                f"Bitte benutze diesen Befehl in <#{LEVEL_QUERY_CHANNEL_ID}>.", ephemeral=True
            )
        embed = await self._build_leaderboard_embed(interaction.guild)
        if embed is None:
            return await interaction.response.send_message("Noch keine Daten für die Rangliste vorhanden.")
        await interaction.response.send_message(embed=embed)

    @commands.hybrid_command(name="level", with_app_command=False)
    async def level_prefix(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        if ctx.channel.id != LEVEL_QUERY_CHANNEL_ID:
            return await ctx.reply(f"Bitte benutze diesen Befehl in <#{LEVEL_QUERY_CHANNEL_ID}>.")
        target = member or ctx.author
        profile = await self.get_profile(target.id)
        need = xp_for_next_level(profile.level)
        embed = discord.Embed(title=f"Level von {target.display_name}", color=discord.Color.blurple())
        embed.add_field(name="Level", value=str(profile.level))
        embed.add_field(name="XP", value=f"{profile.xp} / {need}")
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rangliste", with_app_command=False)
    async def leaderboard_prefix(self, ctx: commands.Context):
        if ctx.channel.id != LEVEL_QUERY_CHANNEL_ID:
            return await ctx.reply(f"Bitte benutze diesen Befehl in <#{LEVEL_QUERY_CHANNEL_ID}>.")
        embed = await self._build_leaderboard_embed(ctx.guild)
        if embed is None:
            return await ctx.send("Noch keine Daten für die Rangliste vorhanden.")
        await ctx.send(embed=embed)

    # -------------------- Interna --------------------
    async def _announce_level_up(self, guild: discord.Guild, member: discord.Member, new_level: int):
        channel: Optional[discord.TextChannel] = guild.get_channel(LEVEL_ANNOUNCE_CHANNEL_ID)  # type: ignore
        if channel is None:
            channel = guild.system_channel  # type: ignore
        if channel:
            try:
                await channel.send(f"🎉 {member.mention} hat **Level {new_level}** erreicht! Weiter so!")
            except Exception:
                pass

    async def _handle_level10_reward(self, guild: discord.Guild, member: discord.Member, new_level: int):
        # Doppelvergabe-Schutz
        if await self._already_rewarded_level10(member.id):
            return

        # 1) Öffentliche Gewinn-Meldung im Level-Channel (schöner Embed)
        level_ch = guild.get_channel(LEVEL_ANNOUNCE_CHANNEL_ID)
        if isinstance(level_ch, discord.TextChannel):
            try:
                emb = discord.Embed(
                    title="🎉 Level 10 erreicht – Friendslist Ticket!",
                    description=(
                        f"{member.mention}, du hast **Level 10** erreicht und dir damit "
                        f"ein **Friendslist Ticket** für das **nächste TotB Event** gesichert! 🫶\n\n"
                        f"Ein Admin meldet sich bald bei dir mit den Details."
                    ),
                    color=discord.Color.gold(),
                )
                emb.set_footer(text="Techno on The Block — Level Up Rewards")
                await level_ch.send(embed=emb)
            except Exception:
                pass

        # 2) Admin-Ping im #level-up-preise
        prizes_ch = guild.get_channel(LEVEL_PRIZES_CHANNEL_ID)
        admin_role = guild.get_role(ADMIN_ROLE_ID)
        if isinstance(prizes_ch, discord.TextChannel) and isinstance(admin_role, discord.Role):
            try:
                await prizes_ch.send(
                    content=(
                        f"{admin_role.mention} — **Friendslist Ticket** fällig!\n"
                        f"User: {member.mention}\n"
                        f"Grund: Level 10 erreicht.\n"
                        f"Bitte Ticket für das nächste Event eintragen und Rückmeldung geben. ✅"
                    ),
                    allowed_mentions=discord.AllowedMentions(roles=[admin_role]),
                )
            except Exception:
                pass

        # 3) Optionale DM an den Gewinner
        if SEND_WINNER_DM:
            try:
                await member.send(
                    "🎉 Glückwunsch! Du hast Level 10 erreicht und ein Friendslist Ticket "
                    "für das nächste TotB Event gewonnen! Ein Admin meldet sich bald bei dir. 🫶"
                )
            except discord.Forbidden:
                pass

        # 4) Als rewarded markieren
        await self._mark_rewarded_level10(member.id)

    def cog_unload(self):
        self.voice_xp_task.cancel()
        self.daily_leaderboard_task.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
