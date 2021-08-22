import logging
import pathlib

import discord
from discord.ext import commands
from discord_slash import SlashCommand
import toml


class PG13Bot(commands.Bot):
    def __init__(self, config_path):
        # Get bot root logger
        self.logger = logging.getLogger("pg13")

        # Load TOML configuration
        config = toml.load(config_path)
        self.guild_configs = config["guilds"]
        self._token = config["token"]

        # Initialize discord.py side of bot
        bot_intents = discord.Intents(
            guild_messages=True, voice_states=True, guilds=True, members=True
        )
        super().__init__(command_prefix=config["prefix"], intents=bot_intents)

        # Set up slash commands
        self.slash = SlashCommand(self, sync_commands=True)

        # Ensure database folder exists
        db_path = pathlib.Path("databases/")
        if not db_path.exists():
            db_path.mkdir()

        # Load cogs
        cogs = [
            "cogs.scores",
            "cogs.dailies",
            "cogs.game_nights",
            "cogs.bonus_roles",
        ]
        for cog in cogs:
            self.load_extension(cog)

    def run(self):
        super().run(self._token)

    async def update_presence(self):
        bot_presence = discord.Activity(
            name="your every mov(i)e :)", type=discord.ActivityType.watching
        )
        await self.change_presence(activity=bot_presence, status=discord.Status.idle)

    async def on_ready(self):
        await self.update_presence()
        self.logger.info("Now running!")
