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
        self.last_places = {}

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_bonus_roles()

    async def init_bonus_roles(self):
        for guild_id, config in self.bot.guild_configs.items():
            # Fetch guild and bonus role, or skip if either is invalid
            guild = self.bot.get_guild(int(guild_id))
            if (guild := self.bot.get_guild(int(guild_id))) is None:
                self.logger.warn(f"Unable to fetch guild {guild_id}")
                continue

            bonus_id = config["bonus_role"]
            if (bonus_role := guild.get_role(bonus_id)) is None:
                self.logger.warn(f"Guild {guild.name} has no role with ID {bonus_id}")
                continue

            # Fetch user scores for guild
            async with aiosqlite.connect("databases/scores.db") as scores:
                top_users = await scores.execute_fetchall(
                    f"SELECT user FROM guild_{guild.id} "
                    "ORDER BY cumulative DESC LIMIT 12"
                )

            # Keep track of last place user
            self.last_places[int(guild_id)] = top_users[-1][0]

            role_members = set(bonus_role.members)

            # Users that should have the bonus role but don't
            for member_id in top_users:
                member = guild.get_member(member_id)

                if member is not None and member.id not in role_members:
                    await member.add_roles(bonus_role)

            self.logger.info(f"Initialized bonus roles for guild {guild.name}")

    async def update_bonus_roles(self, member, current_score):
        # TODO: take member as parameter instead and only look at if their place changed

        guild = member.guild

        # Fetch guild's bonus role from config
        bonus_id = int(self.bot.guild_configs[str(guild.id)].get("bonus_role", None))
        if bonus_id is None:
            self.logger.info(f"Guild {guild.name} doesn't have a bonus role")

        # TODO: There's a lot of repeated code between this method & init_bonus_roles

        # Fetch role object to ensure it exists
        if (bonus_role := guild.get_role(bonus_id)) is None:
            self.logger.warn(
                f"Guild {guild.name} doesn't have a role with the ID of {bonus_id}"
            )
            return

        # Fetch top users from guild
        async with aiosqlite.connect("databases/scores.db") as scores:
            top_users = await scores.execute_fetchall(
                f"SELECT user FROM guild_{guild.id} "
                "ORDER BY cumulative DESC LIMIT 12"
            )

        if (last_id := self.last_places[guild.id]) not in top_users:
            # Remove user's regular role
            thirteenth_place = guild.get_member(last_id)
            await thirteenth_place.remove_roles(bonus_role, reason="Lost bonus role")
            self.logger.info(f"User {thirteenth_place.name} lost bonus role")

            # Add new user's regular role
            await member.add_roles(bonus_role, reason="Gained bonus role")
            self.logger.info(f"User {member.name} gained bonus role")

            # Scores cog is a prerequisite; if this errors you have bigger
            # problems than a cog being None
            await scores_cog.update_scores(member, 5, update_roles=False)

            # Update last place member ID for guild
            self.last_places[guild.id] = member.id


def setup(bot):
    bot.add_cog(BonusRoles(bot))
