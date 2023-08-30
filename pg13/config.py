import os
from pathlib import Path

import toml

thresholds = {}
bonus_roles = {}
admins = {}
door_members = {}
daily_points = {}
daily_max = {}
picture_channels = {}
lottery_channels = {}


def load_config():
    global prefix, token

    config_path = Path(os.environ["CREDENTIALS_DIRECTORY"]) / "config.toml"
    config = toml.load(config_path)

    # General bot config
    prefix = config["prefix"]
    token = config["token"]

    # guild-specific stuff
    for guild_id, config in config["guilds"].items():
        guild_id = int(guild_id)

        thresholds[guild_id] = config["thresholds"]
        bonus_roles[guild_id] = config.get("bonus_role")
        admins[guild_id] = config["admins"]
        daily_points[guild_id] = config.get("daily_points", 3)
        daily_max[guild_id] = config.get("daily_max", 10)
        door_members[guild_id] = config.get("door_member")

        if "picture_channel" in config:
            picture_channels[guild_id] = config["picture_channel"]

        if "lottery_channel" in config:
            lottery_channels[guild_id] = config["lottery_channel"]


load_config()
