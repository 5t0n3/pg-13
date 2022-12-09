import discord

from ..config import admins


async def admin_check(interaction: discord.Interaction):
    """Returns true if the user attempting to use a command is a bot admin"""
    guild_admins = admins[interaction.guild_id]
    is_bot_owner = await interaction.client.is_owner(interaction.user)

    return is_bot_owner or interaction.user.id in guild_admins["users"] or not set(
        map(lambda role: role.id, interaction.user.roles)
    ).isdisjoint(set(guild_admins["roles"]))
