import os

import toml

_config_path = os.environ.get("CONFIG_PATH") or "config.toml"
_config = toml.load(_config_path)

# General bot config
prefix = _config["prefix"]
token = _config["token"]

# Guild-specific things
thresholds = {}
bonus_roles = {}
admins = {}
door_members = {}
daily_points = {}
picture_channels = {}
lottery_channels = {}

for guild_id, config in _config["guilds"].items():
    guild_id = int(guild_id)

    thresholds[guild_id] = config["thresholds"]
    bonus_roles[guild_id] = config.get("bonus_role")
    admins[guild_id] = config["admins"]
    daily_points[guild_id] = config["daily_points"]
    door_members[guild_id] = config.get("door_member")

    if "picture_channel" in config:
        picture_channels[guild_id] = config["picture_channel"]

    if "lottery_channel" in config:
        lottery_channels[guild_id] = config["lottery_channel"\
