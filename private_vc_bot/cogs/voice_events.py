from __future__ import annotations
import asyncio
import discord
from discord.ext import commands, tasks

from .. import config
from ..db import DB
from ..services import private_rooms as pr
from ..services.anti_spam import check_can_create, after_created
from ..services.logging import send_mod_log
from ..services.private_rooms import upsert_panel

class VoiceEvents(commands.Cog):
    def __init__(self, bot: commands.Bot, db: DB):
        self.bot = bot
        self.db = db
        self.cleanup_empty_channels.start()

    def cog_unload(self):
        self.cleanup_empty_channels.cancel()

    # ---- EVENT ----
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Join hub -> create private
        if after and after.channel and after.channel.id == config.HUB_VOICE_CHANNEL_ID and (not before or before.channel != after.channel):
            allowed, reason = check_can_create(self.db, member.id)
            if not allowed:
                # отправим ЛС и вернём обратно
                try:
                    await member.send(reason)
                except Exception:
                    pass
                # попробуем вернуть в предыдущий канал
                if before and before.channel:
                    try:
                        await member.move_to(before.channel, reason="Антиспам ограничение")
                    except Exception:
                        pass
                else:
                    try:
                        await member.move_to(None, reason="Антиспам ограничение")
                    except Exception:
                        pass
                return

            voice = await pr.create_private_channel(member)
            await pr.move_safe(member, voice)

            # создать/зафиксировать панель
            panel_channel_id, panel_message_id = await upsert_panel(self.db, member.guild, voice, member)

            # запись в БД
            self.db.add_room(
                voice.id, member.id,
                panel_channel_id=panel_channel_id or voice.id,
                is_locked=0,
                user_limit=voice.user_limit or config.DEFAULT_LIMIT,
                preset_id=None,
                panel_message_id=panel_message_id
            )

            # антиспам запись
            after_created(self.db, member.id)

            await send_mod_log(self.bot, title="🎧 Создана приватка",
                               description=f"{voice.name} ({voice.id}) -> {member.mention}")

        # Auto-refresh панели при входе
        if after and after.channel:
            room = self.db.get_room(after.channel.id)
            if room:
                owner = member.guild.get_member(room.owner_id) or member
                asyncio.create_task(upsert_panel(self.db, member.guild, after.channel, owner))

        # Leaving any VC -> refresh panel or schedule delete
        if before and isinstance(before.channel, discord.VoiceChannel):
            room = self.db.get_room(before.channel.id)
            if room:
                if len(before.channel.members) > 0:
                    owner = before.channel.guild.get_member(room.owner_id) or before.channel.members[0]
                    asyncio.create_task(upsert_panel(self.db, before.channel.guild, before.channel, owner))
                asyncio.create_task(pr.schedule_delete_if_empty(self.db, before.channel))

    # ---- CLEANER ----
    @tasks.loop(minutes=2)
    async def cleanup_empty_channels(self):
        guild = self.bot.get_guild(config.GUILD_ID) if config.GUILD_ID else None
        if not guild:
            return
        for ch in guild.voice_channels:
            room = self.db.get_room(ch.id)
            if room and len(ch.members) == 0:
                asyncio.create_task(pr.schedule_delete_if_empty(self.db, ch))

async def setup(bot: commands.Bot):
    db = bot.get_cog("DB_COG").db if bot.get_cog("DB_COG") else getattr(bot, "db", None)
    if not db:
        from ..db import DB as _DB
        from .. import config
        db = _DB(config.DB_PATH)
        bot.db = db
    await bot.add_cog(VoiceEvents(bot, db))
