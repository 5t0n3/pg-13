import logging

import discord
from discord.ext import commands
from discord_slash import SlashCommand
import toml


class PG13Bot(commands.Bot):
    def __init__(self, config_path):
        self.config = toml.load(config_path)

        # Choose only necessary intents
        bot_intents = discord.Intents(
            guild_messages=True, voice_states=True, guilds=True, members=True
        )

        super().__init__(
            command_prefix=self.config["commands"]["prefix"], intents=bot_intents
        )
        self.logger = logging.getLogger("pg13")

        # Initialize slash commands
        self.slash = SlashCommand(self, sync_commands=True)

        # Load cogs
        cogs = ["cogs.scores", "cogs.dailies", "cogs.game_nights"]
        for cog in cogs:
            self.load_extension(cog)

    def run(self):
        super().run(self.config["token"])

    async def on_ready(self):
        self.logger.info("Now running!")
