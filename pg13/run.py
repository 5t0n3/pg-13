import logging
import os

from systemd import journal

from .bot import PG13Bot


def run_bot():
    systemd_handler = journal.JournalHandler(SYSLOG_IDENTIFIER="pg-13")
    systemd_handler.setLevel("DEBUG")

    log_format = logging.Formatter(
        fmt="[{levelname}] ({name}:{lineno}): {message}",
        style="{",
    )
    systemd_handler.setFormatter(log_format)

    root_logger = logging.getLogger()
    root_logger.addHandler(systemd_handler)
    root_logger.setLevel("DEBUG")

    # Only log discord.py error/warning messages
    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel("WARNING")

    pg13_bot = PG13Bot()
    pg13_bot.run()
