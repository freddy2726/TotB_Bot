import discord
from discord import app_commands
from discord.ext import commands
import os

class EmbedCreator(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild = discord.Object(id=int(os.getenv("GUILD_ID")))

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="create_embed", description="Erstellt ein Embed in einem Channel.")
    @app_commands.describe(
        channel="Der Channel, in den das Embed gesendet werden soll",
        title="Titel des Embeds",
        description="Beschreibung des Embeds",
        color="Farbe (Hex-Code, z.B. #ff0000)",
        image_url="Bild-URL (optional)",
        thumbnail_url="Thumbnail-URL (optional)"
    )
    async def create_embed(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str,
        color: str = "#2f3136",
        image_url: str = None,
        thumbnail_url: str = None
    ):

        # Admin-only guard

        user = getattr(interaction, 'user', None) or getattr(interaction, 'author', None)

        if not getattr(getattr(user, 'guild_permissions', None), 'administrator', False):

            await interaction.response.send_message('❌ Nur Administratoren dürfen diesen Befehl verwenden.', ephemeral=True)

            return

        try:
            color_value = int(color.replace("#", ""), 16)
        except ValueError:
            await interaction.response.send_message("❌ Ungültiger Farbcode. Nutze z.B. `#ff0000`.", ephemeral=True)
            return

        embed = discord.Embed(title=title, description=description, color=color_value)
        if image_url:
            embed.set_image(url=image_url)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        await channel.send(embed=embed)
        await interaction.response.send_message("✅ Embed wurde gesendet!", ephemeral=True)

    async def cog_load(self):
        self.bot.tree.add_command(self.create_embed, guild=self.guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedCreator(bot))
