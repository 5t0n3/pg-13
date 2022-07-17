import logging
import os

from systemd import journal

from .bot import PG13Bot


def run_bot():
    systemd_handler = journal.JournalHandler(SYSLOG_IDENTIFIER="pg-13")
    systemd_handler.setLevel("INFO")

    log_format = logging.Formatter(
        fmt="[{levelname}] ({name}:{lineno}): {message}",
        style="{",
    )
    systemd_handler.setFormatter(log_format)

    root_logger = logging.getLogger()
    root_logger.addHandler(systemd_handler)
    root_logger.setLevel("INFO")

    # Only log discord.py error/warning messages
    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel("WARNING")

    config_path = os.environ.get("CONFIG_PATH") or "config.toml"
    pg13_bot = bot.PG13Bot(config_path)
    pg13_bot.run()
