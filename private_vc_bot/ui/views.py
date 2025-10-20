from __future__ import annotations
import discord
from typing import List, Tuple
from ..db import DB
from ..services.private_rooms import apply_lock_state, delete_private_channel
from ..services.logging import send_mod_log

class KickMemberSelect(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(custom_id="priv:kick", placeholder="Кого выгнать?",
                         min_values=1, max_values=1, options=options, disabled=(len(options)==0))

    async def callback(self, interaction: discord.Interaction):
        v: ControlView = self.view  # type: ignore
        voice = interaction.guild.get_channel(v.voice_channel_id)
        room = v.db.get_room(v.voice_channel_id) if voice else None
        if not voice or not room:
            return await interaction.response.send_message("Канал не найден.", ephemeral=True)
        if interaction.user.id != room.owner_id and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Только создатель может кикать.", ephemeral=True)

        target_id = int(self.values[0])
        target = interaction.guild.get_member(target_id)
        if not target or target not in voice.members:
            return await interaction.response.send_message("Пользователь уже не в канале.", ephemeral=True)
        if target_id == room.owner_id:
            return await interaction.response.send_message("Создателя выгонять нельзя.", ephemeral=True)

        try:
            await target.move_to(None, reason="Kick from private vc")
        except (discord.Forbidden, discord.HTTPException):
            return await interaction.response.send_message("Не удалось выгнать пользователя.", ephemeral=True)

        await send_mod_log(interaction.client, title="👢 Кик из приватки",
                           description=f"{target.mention} из {voice.name} (инициатор: {interaction.user.mention})")
        await interaction.response.send_message(f"👢 {target.mention} выгнан.", ephemeral=True)


class TransferOwnerSelect(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(custom_id="priv:transfer", placeholder="Кому передать права?",
                         min_values=1, max_values=1, options=options, disabled=(len(options)==0))

    async def callback(self, interaction: discord.Interaction):
        v: ControlView = self.view  # type: ignore
        voice = interaction.guild.get_channel(v.voice_channel_id)
        room = v.db.get_room(v.voice_channel_id) if voice else None
        if not voice or not room:
            return await interaction.response.send_message("Канал не найден.", ephemeral=True)
        if interaction.user.id != room.owner_id and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Только текущий создатель может передавать права.", ephemeral=True)

        new_owner_id = int(self.values[0])
        if new_owner_id == room.owner_id:
            return await interaction.response.send_message("Вы уже владелец.", ephemeral=True)
        new_owner = interaction.guild.get_member(new_owner_id)
        if not new_owner or new_owner not in voice.members:
            return await interaction.response.send_message("Новый владелец должен быть в канале.", ephemeral=True)

        overwrites = voice.overwrites
        old_owner = interaction.guild.get_member(room.owner_id)
        if old_owner in overwrites:
            overwrites[old_owner] = discord.PermissionOverwrite(connect=True, view_channel=True)
        overwrites[new_owner] = discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True)
        await voice.edit(overwrites=overwrites, reason="Передача прав создателя")
        v.db.set_owner(voice.id, new_owner.id)

        await send_mod_log(interaction.client, title="👑 Переданы права создателя",
                           description=f"{voice.name}: {new_owner.mention} теперь владелец (инициатор: {interaction.user.mention})")
        await interaction.response.send_message(f"👑 Права переданы: {new_owner.mention}.", ephemeral=True)


class ControlView(discord.ui.View):
    def __init__(self, db: DB, voice_channel_id: int, owner_id: int, member_options: List[Tuple[int, str]]):
        super().__init__(timeout=None)
        self.db = db
        self.voice_channel_id = voice_channel_id

        others = [(uid, label) for uid, label in member_options if uid != owner_id][:25]
        kick_opts = [discord.SelectOption(label=label, value=str(uid)) for uid, label in others]
        transfer_opts = [discord.SelectOption(label=label, value=str(uid)) for uid, label in others]
        if kick_opts:
            self.add_item(KickMemberSelect(kick_opts))
        if transfer_opts:
            self.add_item(TransferOwnerSelect(transfer_opts))

    def _get_context(self, interaction: discord.Interaction):
        voice = interaction.guild.get_channel(self.voice_channel_id)
        room = self.db.get_room(self.voice_channel_id) if voice else None
        return voice, room

    @discord.ui.button(label="Открыт/Закрыт", style=discord.ButtonStyle.primary, emoji="🔒", custom_id="priv:toggle")
    async def toggle_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice, room = self._get_context(interaction)
        if not voice or not room:
            return await interaction.response.send_message("Канал не найден.", ephemeral=True)
        if interaction.user.id != room.owner_id and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Только создатель может менять доступ.", ephemeral=True)

        locked = not room.is_locked
        await apply_lock_state(voice, locked, interaction.guild.get_member(room.owner_id))
        self.db.set_locked(voice.id, int(locked))
        await send_mod_log(interaction.client, title="🔒 Смена статуса",
                           description=f"{voice.name}: {'закрыт' if locked else 'открыт'} (инициатор: {interaction.user.mention})")
        await interaction.response.send_message(f"Канал теперь **{'закрыт 🔒' if locked else 'открыт 🔓'}**.", ephemeral=True)

    @discord.ui.select(placeholder="Лимит участников",
        options=[discord.SelectOption(label=str(x), value=str(x)) for x in (2,3,4,5,8,10)],
        custom_id="priv:limit")
    async def set_limit(self, interaction: discord.Interaction, select: discord.ui.Select):
        voice, room = self._get_context(interaction)
        if not voice or not room:
            return await interaction.response.send_message("Канал не найден.", ephemeral=True)
        if interaction.user.id != room.owner_id and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Только создатель может менять лимит.", ephemeral=True)

        limit_val = int(select.values[0])
        await voice.edit(user_limit=limit_val, reason="Изменение лимита")
        self.db.set_limit(voice.id, limit_val)
        await send_mod_log(interaction.client, title="👥 Изменён лимит",
                           description=f"{voice.name}: {limit_val} (инициатор: {interaction.user.mention})")
        await interaction.response.send_message(f"Лимит установлен: **{limit_val}**.", ephemeral=True)

    @discord.ui.button(label="Удалить канал", style=discord.ButtonStyle.danger, emoji="🗑", custom_id="priv:delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice, room = self._get_context(interaction)
        if not voice or not room:
            return await interaction.response.send_message("Канал не найден.", ephemeral=True)
        if interaction.user.id != room.owner_id and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Удалить может только создатель.", ephemeral=True)
        await interaction.response.send_message("Канал будет удалён.", ephemeral=True)
        await delete_private_channel(self.db, voice)
