import itertools
import logging

from discord.ext import commands

logger = logging.getLogger(__name__)


class BonusRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_places = {}

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_bonus_roles()

    async def init_bonus_roles(self):
        for guild in self.bot.guilds:
            await self.update_bonus_roles(guild)

        logger.info(f"Initialized all guild bonus roles")

    async def update_bonus_roles(self, guild):
        # Fetch guild's bonus role from config
        bonus_id = self.bot.guild_configs[str(guild.id)].get("bonus_role")
        if bonus_id is None:
            logger.warn(f"Guild {guild.name} doesn't have a bonus role configured")
            return

        bonus_id = int(bonus_id)

        # Fetch role object to ensure it exists
        if (bonus_role := guild.get_role(bonus_id)) is None:
            logger.warn(
                f"Guild {guild.name} doesn't have a role with the ID of {bonus_id}"
            )
            return

        # Fetch top users from guild
        async with self.bot.db_pool.acquire() as con:
            # TODO: Handle cases where someone in the top 12 left a server
            top_12 = await con.fetch(
                "SELECT userid FROM scores ORDER BY score DESC LIMIT 12"
            )

        top_users = set(map(lambda row: row["userid"], top_12))
        current_bonus_users = set(map(lambda member: member.id, bonus_role.members))

        gained_role = top_users - current_bonus_users
        lost_role = current_bonus_users - top_users

        for id in gained_role:
            if (member := guild.get_member(user_id)) is not None:
                await member.add_roles(bonus_role, reason="Gained bonus role")

        for id in lost_role:
            if (member := guild.get_member(user_id)) is not None:
                await member.remove_roles(bonus_role, reason="Lost bonus role")

        if (scores_cog := self.bot.get_cog("Scores")) is not None:
            increments = zip(gained_role, itertools.repeat(5))
            await scores_cog.bulk_increment_scores(
                guild, increments, update_roles=False
            )


async def setup(bot):
    await bot.add_cog(BonusRoles(bot))
