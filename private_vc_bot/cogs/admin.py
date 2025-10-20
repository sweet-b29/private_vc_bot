from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from .. import config
from ..db import DB
from ..services.private_rooms import post_panel, rescan_and_repair
from ..ui.views import ControlView

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot, db: DB):
        self.bot = bot
        self.db = db

    @app_commands.command(name="panel", description="Повторно вывести/обновить панель управления приваткой")
    @app_commands.describe(voice_channel="Ваш голосовой канал (если не в нём)")
    async def panel_cmd(self, interaction: discord.Interaction, voice_channel: Optional[discord.VoiceChannel] = None):
        await interaction.response.defer(ephemeral=True)
        target = voice_channel or (interaction.user.voice.channel if interaction.user.voice else None)
        if not target:
            return await interaction.followup.send("Вы не в голосовом канале и канал не указан.", ephemeral=True)

        room = self.db.get_room(target.id)
        if not room:
            return await interaction.followup.send("Этот голосовой канал не управляется ботом.", ephemeral=True)

        if interaction.user.id != room.owner_id and not interaction.user.guild_permissions.manage_channels:
            return await interaction.followup.send("Только создатель может вызвать панель.", ephemeral=True)

        owner = interaction.guild.get_member(room.owner_id) or interaction.user
        from ..services.private_rooms import upsert_panel
        await upsert_panel(self.db, interaction.guild, target, owner)
        return await interaction.followup.send("Панель обновлена.", ephemeral=True)

    @app_commands.command(name="priv-rescan", description="(Админы) Пересканировать приватки и восстановить панели")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def rescan_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await rescan_and_repair(self.bot, self.db)
        await interaction.followup.send("Перескан завершён.", ephemeral=True)

async def setup(bot: commands.Bot):
    db = bot.get_cog("DB_COG").db if bot.get_cog("DB_COG") else getattr(bot, "db", None)
    if not db:
        from ..db import DB as _DB
        from .. import config
        db = _DB(config.DB_PATH)
        bot.db = db
    await bot.add_cog(Admin(bot, db))
