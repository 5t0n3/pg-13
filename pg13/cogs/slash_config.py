import discord
import toml

config = toml.load("config.toml")

# Default to registering commands in all guilds with a provided config
loaded_guilds = list(map(int, config["guilds"]))

# Admin roles/users are configured in config.toml as well
async def admin_check(interaction: discord.Interaction):
    """Returns true if the user attempting to use a command is a bot admin"""
    guild_admins = config["guilds"][str(interaction.guild_id)]["admins"]

    return interaction.user.id in guild_admins["users"] or not set(
        map(lambda role: role.id, interaction.user.roles)
    ).isdisjoint(set(guild_admins["roles"]))
