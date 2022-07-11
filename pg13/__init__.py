import logging
import logging.handlers as handlers
import os
import pathlib

from systemd import journal

from . import bot


def run_bot():
    systemd_handler = journal.JournalHandler(SYSLOG_IDENTIFIER="pg-13")
    systemd_handler.setLevel("INFO")

    log_format = logging.Formatter(
        fmt="[{levelname}] ({name}:{lineno}) {asctime}: {message}",
        style="{",
    )
    systemd_handler.setFormatter(log_format)

    # Add handler to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(systemd_handler)

    # Make sure root logger is also set to INFO logging level
    root_logger.setLevel("INFO")

    config_path = os.environ.get("CONFIG_PATH") or "config.toml"
    pg13_bot = bot.PG13Bot(config_path)
    pg13_bot.run()
