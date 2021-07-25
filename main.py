import logging

from bot import PG13Bot

# Set up logging
logging.basicConfig(
    filename="discord.log",
    encoding="utf-8",
    filemode="w",
    format="[{levelname}] ({name}:{lineno}) {asctime}: {message}",
    style="{",
    level="INFO",
)

pg13_bot = PG13Bot("config.toml")
pg13_bot.run()
