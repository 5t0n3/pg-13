from discord_slash.model import SlashCommandPermissionType
from discord_slash.utils.manage_commands import generate_permissions
import toml

config = toml.load("config.toml")

# Default to registering commands in all guilds with a provided config
loaded_guilds = {"guild_ids": list(map(int, config["guilds"]))}

# Admin roles/users are configured in config.toml as well
admin_perms = {
    "base_default_permission": False,
    "base_permissions": {
        int(guild_id): generate_permissions(
            allowed_roles=guild_config["admins"]["roles"],
            allowed_users=guild_config["admins"]["users"],
        )
        for guild_id, guild_config in config["guilds"].items()
    },
}
