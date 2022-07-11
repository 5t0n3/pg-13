import logging

import aiosqlite
from discord.ext import commands


class BonusRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.bonusroles")
        self.last_places = {}

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_bonus_roles()

    async def init_bonus_roles(self):
        for guild in self.bot.guilds:
            await self.update_bonus_roles(guild)
            self.logger.info(f"Initialized bonus roles for guild {guild.name}")

    async def update_bonus_roles(self, guild):
        # Fetch guild's bonus role from config
        bonus_id = int(self.bot.guild_configs[str(guild.id)].get("bonus_role", None))
        if bonus_id is None:
            self.logger.warn(f"Guild {guild.name} doesn't have a bonus role configured")
            return

        # Fetch role object to ensure it exists
        if (bonus_role := guild.get_role(bonus_id)) is None:
            self.logger.warn(
                f"Guild {guild.name} doesn't have a role with the ID of {bonus_id}"
            )
            return

        # Fetch top users from guild
        async with aiosqlite.connect("databases/scores.db") as scores:
            top_rows = await scores.execute_fetchall(
                f"SELECT user FROM guild_{guild.id} "
                "ORDER BY cumulative DESC LIMIT 12"
            )

        # Convert list of rows (tuples) to list of user ids
        top_users = list(map(lambda row: row[0], top_rows))
        top_user_set = set(top_users)

        # Uninitialized; check all users
        if (last_id := self.last_places.get(guild.id, None)) is None:
            current_bonus_members = set(bonus_role.members)
            current_bonus_ids = set(
                map(lambda member: member.id, current_bonus_members)
            )

            # Remove bonus role from people no longer in the first 12 places
            for user_id in current_bonus_ids - top_user_set:
                member = guild.get_member(user_id)
                await member.remove_roles(bonus_role, reason="Lost bonus role")

            # Add role to members if they don't already have it
            for user_id in top_user_set - current_bonus_ids:
                member = guild.get_member(user_id)
                await member.add_roles(bonus_role, reason="Gained bonus role")

                # Give user 5-point bonus if they didn't have the role before
                # See below comment about checking if the cog is None
                scores_cog = self.bot.get_cog("Scores")
                await scores_cog.update_scores(member, 5, update_roles=False)

        # Swap 2 users' bonus roles, if applicable
        elif last_id not in top_user_set:
            # Remove ousted user's regular role
            thirteenth_place = guild.get_member(last_id)
            await thirteenth_place.remove_roles(bonus_role, reason="Lost bonus role")
            self.logger.info(f"User {thirteenth_place.name} lost bonus role")

            # Add new last place user's regular role
            if (new_last := guild.get_member(top_users[-1])) is not None:
                await new_last.add_roles(bonus_role, reason="Gained bonus role")
                self.logger.info(f"User {member.name} gained bonus role")

                # Scores cog is a prerequisite; if this errors you have bigger
                # problems than a cog being None
                scores_cog = self.bot.get_cog("Scores")
                await scores_cog.update_scores(new_last, 5, update_roles=False)

                # Update last place member ID for guild
                self.last_places[guild.id] = new_last.id

            # Theoretically this shouldn't happen but just in case
            # TODO: Investigate why this would happen
            else:
                self.logger.warn(f"User {last_id} not in guild {guild.name}")

        else:
            self.logger.info(
                f"Bonus roles didn't have to be updated in guild {guild.name}"
            )


async def setup(bot):
    await bot.add_cog(BonusRoles(bot))
