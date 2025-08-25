import discord
from discord.ext import commands

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.welcome_channel_id = 1399119245782290474  # dein Willkommens-Channel

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = member.guild.get_channel(self.welcome_channel_id)
        if channel:
            await channel.send(
                f"👋 Willkommen auf dem Server, {member.mention}! "
                "Schön, dass du da bist 🎉"
            )

async def setup(bot):
    await bot.add_cog(Welcome(bot))
