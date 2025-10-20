
from __future__ import annotations
import discord
from typing import Iterable, Tuple, Optional
from .. import config

async def send_mod_log(bot, *, title: str, description: str = "", fields: Optional[Iterable[Tuple[str, str, bool]]] = None):
    if not config.LOG_CHANNEL_ID:
        return
    ch = bot.get_channel(config.LOG_CHANNEL_ID)
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        return
    emb = discord.Embed(title=title, description=description, color=config.BRAND_COLOR)
    if fields:
        for name, value, inline in fields:
            emb.add_field(name=name, value=value, inline=inline)
    await ch.send(embed=emb)
