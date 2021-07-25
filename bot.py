import discord
from discord.ext import commands
from discord_slash import SlashCommand
import toml

from channel_daily import ChannelDailyCog
from scores import ScoresCog


class PG13Bot(commands.Bot):
    def __init__(self, config_path, logger):
        self.config = toml.load(config_path)

        # Choose only necessary intents
        bot_intents = discord.Intents(
            guild_messages=True, voice_states=True, guilds=True, members=True
        )

        super().__init__(
            command_prefix=self.config["commands"]["prefix"], intents=bot_intents
        )
        self.logger = logger

        # Initialize slash commands
        self.slash = SlashCommand(self, sync_commands=True)

        # Load cogs
        self.add_cog(ScoresCog(self))
        self.add_cog(ChannelDailyCog(self))

    def run(self):
        super().run(self.config["token"])

    async def on_ready(self):
        self.logger.info("Now running!")
