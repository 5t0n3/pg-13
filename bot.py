from discord.ext import commands
import toml


class PG13Bot(commands.Bot):
    def __init__(self, config_path, logger):
        self.config = toml.load(config_path)

        super().__init__(command_prefix=self.config["prefix"])
        self.logger = logger

        # Load cogs

    def run(self):
        super().run(self.config["token"])

    async def on_ready(self):
        self.logger.info("Now running!")
