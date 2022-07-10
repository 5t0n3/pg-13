import logging
import pathlib

import discord
from discord import app_commands
from discord.ext import commands
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
        self.tree.on_error = self.handle_command_error

        # Ensure database folder exists
        db_path = pathlib.Path("databases/")
        if not db_path.exists():
            db_path.mkdir()

    def run(self):
        super().run(self._token, log_handler=None)

    async def handle_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "Hey, you don't have permission to do that :)", ephemeral=True
            )

    async def update_presence(self):
        bot_presence = discord.Activity(
            name="your every mov(i)e :)", type=discord.ActivityType.watching
        )
        await self.change_presence(activity=bot_presence, status=discord.Status.idle)

    async def setup_hook(self):
        cog_list = [
            "cogs.scores",
            "cogs.dailies",
            # "cogs.game_nights",
            # "cogs.bonus_roles",
            # "cogs.door_to_darkness",
        ]

        for cog in cog_list:
            await self.load_extension(cog)

    async def on_ready(self):
        await self.update_presence()

        # Sync slash commands (for development purposes)
        await self.tree.sync(guild=discord.Object(745332731184939039))

        self.logger.info("Now running!")
