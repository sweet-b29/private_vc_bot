from __future__ import annotations
import logging
import discord
from discord.ext import commands
from . import config
from .db import DB
from .services.private_rooms import rescan_and_repair

INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.members = True
INTENTS.voice_states = True

class Bot(commands.Bot):
    def __init__(self, db: DB):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.db = db

    async def setup_hook(self):
        # Слэш-команды для одной гильдии, если указан
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

        # загружаем коги
        await self.load_extension("private_vc_bot.cogs.voice_events")
        await self.load_extension("private_vc_bot.cogs.admin")

        # восстановление состояния
        await rescan_and_repair(self, self.db)

    async def on_ready(self):
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")
        try:
            await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="за вашими приватками"))
        except Exception:
            pass

def main():
    config.require_token()
    db = DB(config.DB_PATH)
    bot = Bot(db)
    bot.run(config.DISCORD_TOKEN)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
