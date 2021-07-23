import logging

from bot import PG13Bot

# Set up logging
logger = logging.getLogger("discord")
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
handler.setFormatter(logging.Formatter("{asctime} [{levelname}]: {message}", style="{"))
logger.addHandler(handler)

# For scheduling:
# https://stackoverflow.com/a/61180222

pg13_bot = PG13Bot("config.toml", logger)
pg13_bot.run()
