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

for guild_id, config in _config["guilds"].items():
    guild_id = int(guild_id)

    thresholds[guild_id] = config["thresholds"]
    bonus_roles[guild_id] = config["bonus_role"]
    admins[guild_id] = config["admins"]
