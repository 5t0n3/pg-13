import logging
import logging.handlers as handlers

from bot import PG13Bot

# Rotate log files every 24 hours (at midnight)
rotating_handler = handlers.TimedRotatingFileHandler(
    filename="discord.log",
    when="midnight",
)

# Use INFO logging level
rotating_handler.setLevel("INFO")

# Set up custom logging format
log_format = logging.Formatter(
    fmt="[{levelname}] ({name}:{lineno}) {asctime}: {message}",
    style="{",
)
rotating_handler.setFormatter(log_format)

# Add handler to root logger
root_logger = logging.getLogger()
root_logger.addHandler(rotating_handler)

# Make sure root logger is also set to INFO logging level
root_logger.setLevel("INFO")

pg13_bot = PG13Bot("config.toml")
pg13_bot.run()
