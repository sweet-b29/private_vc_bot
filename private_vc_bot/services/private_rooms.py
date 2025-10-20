from __future__ import annotations
from typing import Optional

import discord
from .. import config
from ..db import DB
from ..utils.naming import sanitize_name
from ..services.logging import send_mod_log
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..ui.views import ControlView

PANEL_DESC = (
    "Создатель управляет доступом и лимитом.\n"
    "• 🔒 Открыть/закрыть\n"
    "• 👥 Лимит мест\n"
    "• 👢 Кик участника\n"
    "• 👑 Передать права\n"
    "• 🗑 Удалить канал"
)

def _build_view(db: DB, voice: discord.VoiceChannel, owner: discord.Member):
    # ленивый импорт, чтобы не было циклического
    from ..ui.views import ControlView
    member_options = [(m.id, m.display_name) for m in voice.members]
    return ControlView(db=db, voice_channel_id=voice.id, owner_id=owner.id, member_options=member_options)


async def upsert_panel(db: DB, guild: discord.Guild, voice: discord.VoiceChannel, owner: discord.Member) -> tuple[int | None, int | None]:
    """Редактируем существующую панель, если она есть; иначе создаём новую.
    Возвращаем (panel_channel_id, panel_message_id)."""
    import logging
    from .. import config

    view = _build_view(db, voice, owner)
    embed = discord.Embed(title=config.PANEL_TITLE, description=PANEL_DESC, color=config.BRAND_COLOR)
    embed.set_footer(text="Private VC • yourserver.gg")
    embed.add_field(name="Создатель", value=owner.mention, inline=False)

    room = db.get_room(voice.id)

    # 1) Пробуем отредактировать старое сообщение
    if room and getattr(room, "panel_message_id", None):
        try:
            ch = voice if room.panel_channel_id == voice.id else guild.get_channel(room.panel_channel_id)
            if isinstance(ch, (discord.VoiceChannel, discord.TextChannel, discord.Thread)):
                msg = await ch.fetch_message(room.panel_message_id)
                await msg.edit(embed=embed, view=view)
                return (ch.id, msg.id)
        except Exception as e:
            logging.info("upsert_panel: old message not found/editable -> recreate (%s)", e)

    # 2) Публикуем заново в чат voice
    try:
        msg = await voice.send(embed=embed, view=view)
        db.set_panel_channel(voice.id, voice.id)
        db.set_panel_message(voice.id, msg.id)
        return (voice.id, msg.id)
    except Exception as e:
        logging.exception("upsert_panel: voice.send failed in %s (%s)", voice.name, voice.id)
        if not config.ALLOW_FALLBACK_TEXT_PANEL:
            return (None, None)
        # Фоллбэк: отдельный текст-канал (если разрешён)
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
                owner: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True),
            }
            text = await guild.create_text_channel(
                name=f"🔧-{sanitize_name(owner.display_name)}",
                category=voice.category,
                overwrites=overwrites,
                reason="Панель управления приваткой (fallback)"
            )
            msg = await text.send(embed=embed, view=view)
            db.set_panel_channel(voice.id, text.id)
            db.set_panel_message(voice.id, msg.id)
            return (text.id, msg.id)
        except Exception:
            return (None, None)

async def apply_lock_state(voice: discord.VoiceChannel, locked: bool, owner: discord.Member):
    overwrites = voice.overwrites
    g = voice.guild
    overwrites[g.default_role] = discord.PermissionOverwrite(
        view_channel=True, connect=not locked, send_messages=True
    )
    overwrites[owner] = discord.PermissionOverwrite(
        view_channel=True, connect=True, manage_channels=True, move_members=True,
        send_messages=True, manage_messages=True
    )
    overwrites[g.me] = discord.PermissionOverwrite(
        view_channel=True, connect=True, manage_channels=True, move_members=True,
        send_messages=True, manage_messages=True
    )
    await voice.edit(overwrites=overwrites, reason="Toggle lock")

async def ensure_category(guild: discord.Guild) -> discord.CategoryChannel:
    cat = guild.get_channel(config.PRIVATE_CATEGORY_ID) if config.PRIVATE_CATEGORY_ID else None
    if not isinstance(cat, discord.CategoryChannel):
        cat = await guild.create_category("🔑 Приватки")
    return cat

async def create_private_channel(member: discord.Member) -> discord.VoiceChannel:
    guild = member.guild
    category = await ensure_category(guild)
    name = f"🎧 {sanitize_name(member.display_name)}"
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True, connect=True, send_messages=True
        ),
        member: discord.PermissionOverwrite(
            view_channel=True, connect=True, manage_channels=True, move_members=True,
            send_messages=True, manage_messages=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, connect=True, manage_channels=True, move_members=True,
            send_messages=True, manage_messages=True
        ),
    }
    voice = await guild.create_voice_channel(
        name=name,
        category=category,
        user_limit=config.DEFAULT_LIMIT,
        overwrites=overwrites,
        reason="Создание приватки"
    )
    return voice

async def move_safe(member: discord.Member, target: Optional[discord.VoiceChannel]):
    try:
        await member.move_to(target, reason="Private room management")
    except (discord.Forbidden, discord.HTTPException):
        pass

async def delete_private_channel(db: DB, voice: discord.VoiceChannel):
    db.del_room(voice.id)
    try:
        await voice.delete(reason="Удаление пустой приватки")
    except Exception:
        pass
    await send_mod_log(voice.guild._state._get_client(), title="🗑 Удалена приватка",
                       description=f"{voice.name} ({voice.id})")

async def post_panel(guild: discord.Guild, voice: discord.VoiceChannel, owner: discord.Member, view) -> Optional[int]:
    import logging
    from .. import config
    embed = discord.Embed(title=config.PANEL_TITLE, description=PANEL_DESC, color=config.BRAND_COLOR)
    embed.set_footer(text="Private VC • yourserver.gg")
    embed.add_field(name="Создатель", value=owner.mention, inline=False)
    try:
        await voice.send(embed=embed, view=view)  # отправка в чат голосового
        logging.info("post_panel: sent in voice %s (%s)", voice.name, voice.id)
        return voice.id
    except Exception as e:
        logging.exception("post_panel: failed to send in voice %s (%s)", voice.name, voice.id)
        if not config.ALLOW_FALLBACK_TEXT_PANEL:
            # уведомим владельца, чтобы было видно причину
            try:
                await owner.send(f"Не удалось отправить панель в {voice.name}: {type(e).__name__}: {e}")
            except Exception:
                pass
            return None

async def schedule_delete_if_empty(db: DB, voice: discord.VoiceChannel):
    import logging, asyncio
    logging.info("cleanup: schedule check for %s (%s) in %ss", voice.name, voice.id, config.DELETE_AFTER_EMPTY_SEC)
    await asyncio.sleep(config.DELETE_AFTER_EMPTY_SEC)
    ch = voice.guild.get_channel(voice.id)
    if ch and isinstance(ch, discord.VoiceChannel) and len(ch.members) == 0:
        logging.info("cleanup: deleting %s (%s)", ch.name, ch.id)
        await delete_private_channel(db, ch)

async def rescan_and_repair(bot, db: DB):
    """Восстановление состояния после рестарта:
    - Удаляем записи из БД, если канал исчез.
    - Если есть голосовые каналы '🎧 ' без записи — берём под управление.
    - Репостим панели управления для всех активных приваток.
    """
    guild = bot.get_guild(config.GUILD_ID) if config.GUILD_ID else None
    if not guild:
        return

    # 1) чистка отсутствующих
    for room in db.list_rooms():
        ch = guild.get_channel(room.voice_channel_id)
        if not isinstance(ch, discord.VoiceChannel):
            continue
        owner = guild.get_member(room.owner_id)
        if not owner:
            continue
        await upsert_panel(db, guild, ch, owner)

    # 2) усыновление каналов по сигнатуре
    category = guild.get_channel(config.PRIVATE_CATEGORY_ID) if config.PRIVATE_CATEGORY_ID else None
    voice_candidates = []
    if isinstance(category, discord.CategoryChannel):
        voice_candidates = [ch for ch in category.voice_channels if ch.name.startswith("🎧 ")]
    else:
        voice_candidates = [ch for ch in guild.voice_channels if ch.name.startswith("🎧 ")]

    known_ids = {r.voice_channel_id for r in db.list_rooms()}
    adopt = [ch for ch in voice_candidates if ch.id not in known_ids]
    for ch in adopt:
        # пытаемся определить владельца (первый участник, если есть; иначе — пропускаем)
        owner = ch.members[0] if ch.members else None
        if owner:
            db.add_room(ch.id, owner.id, None, is_locked=0, user_limit=ch.user_limit or config.DEFAULT_LIMIT)
            await send_mod_log(bot, title="🍼 Усыновлена приватка", description=f"{ch.name} ({ch.id}) -> {owner.mention}")

    # 3) репост панелей
    for room in db.list_rooms():
        ch = guild.get_channel(room.voice_channel_id)
        if not isinstance(ch, discord.VoiceChannel):
            continue
        owner = guild.get_member(room.owner_id)
        if not owner:
            continue
        await upsert_panel(db, guild, ch, owner)