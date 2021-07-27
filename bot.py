import logging
import pathlib

import discord
from discord.ext import commands
from discord_slash import SlashCommand
import toml


class PG13Bot(commands.Bot):
    def __init__(self, config_path):
        config = toml.load(config_path)

        # Choose only necessary intents
        bot_intents = discord.Intents(
            guild_messages=True, voice_states=True, guilds=True, members=True
        )

        super().__init__(
            command_prefix=config["commands"]["prefix"], intents=bot_intents
        )
        self.logger = logging.getLogger("pg13")
        self.guild_ids = config["commands"]["guilds"]
        self._token = config["token"]

        # Initialize slash commands
        self.slash = SlashCommand(self, sync_commands=True)

        # Ensure database folder exists
        db_path = pathlib.Path("databases/")
        if not db_path.exists():
            db_path.mkdir()

        # Load cogs
        cogs = ["cogs.scores", "cogs.dailies", "cogs.game_nights"]
        for cog in cogs:
            self.load_extension(cog)

    def run(self):
        super().run(self._token)

    async def on_ready(self):
        self.logger.info("Now running!")
