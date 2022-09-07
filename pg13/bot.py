import logging

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands
        
from .config import token, prefix

logger = logging.getLogger(__name__)


class PG13Tree(discord.app_commands.CommandTree):
    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "Hey, you don't have permission to do that :)", ephemeral=True
            )

        else:
            await interaction.response.send_message(
                "Oops! Something went wrong while executing that command.",
                ephemeral=True,
            )
            logger.error(
                f"Error while executing command `/{interaction.command.qualified_name}`:",
                exc_info=error,
            )


class PG13Bot(commands.Bot):
    def __init__(self):
        bot_intents = discord.Intents(
            guild_messages=True,
            voice_states=True,
            guilds=True,
            members=True,
            message_content=True,
        )
        super().__init__(
            command_prefix=prefix,
            tree_cls=PG13Tree,
            help_command=None,
            intents=bot_intents,
        )

    def run(self):
        super().run(token, log_handler=None)

    async def setup_hook(self):
        self.db_pool = await asyncpg.create_pool(database="pg_13", user="pg-13")

        cog_list = [
            "pg13.cogs.scores",
            "pg13.cogs.dailies",
            "pg13.cogs.gamenights",
            "pg13.cogs.bonus_roles",
            "pg13.cogs.utilities",
        ]

        for cog in cog_list:
            await self.load_extension(cog)

    async def on_ready(self):
        bot_presence = discord.Activity(
            name="your every mov(i)e :)", type=discord.ActivityType.watching
        )
        await self.change_presence(activity=bot_presence, status=discord.Status.idle)

        logger.info(f"Now running as {self.user.name}#{self.user.discriminator}!")
