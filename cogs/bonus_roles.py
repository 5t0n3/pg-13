import logging

import aiosqlite
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.context import SlashContext
from discord_slash.model import SlashCommandOptionType as OptionType
from discord_slash.utils.manage_commands import create_option, create_choice

from .guild_ids import GUILD_IDS


class BonusRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.bonusroles")

    async def update_bonus_roles(self, guild):
        # TODO: take member as parameter instead and only look at if their place changed

        # Fetch guild's bonus role from config
        bonus_id = int(self.bot.guild_configs[str(guild.id)].get("bonus_role", None))
        if bonus_id is None:
            self.logger.info(f"Guild {guild.name} doesn't have a bonus role")

        # Fetch role object to ensure it exists
        bonus_role = guild.get_role(bonus_id)
        if bonus_role is None:
            self.logger.warn(
                f"Guild {guild.name} doesn't have a role with the ID of {bonus_id}"
            )

        async with aiosqlite.connect("databases/scores.db") as scores:
            top_users = await scores.execute_fetchall(
                f"SELECT user FROM guild_{guild.id} "
                "ORDER BY cumulative DESC LIMIT 12"
            )

        # TODO: Handle removal of bonus role
        for (user_id,) in top_users:
            member = guild.get_member(user_id)
            if bonus_id not in member.roles:
                await member.add_roles(bonus_role, reason="Gained bonus role")
                if (scores_cog := self.bot.get_cog("Scores")) is not None:
                    await scores_cog.update_scores(member, 5, update_roles=False)


def setup(bot):
    bot.add_cog(BonusRoles(bot))
