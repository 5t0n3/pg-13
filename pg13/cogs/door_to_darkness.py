import asyncio
import datetime
import logging
import re
from zoneinfo import ZoneInfo

from discord.ext import commands, tasks

from ..config import door_members

logger = logging.getLogger(__name__)


class DoorToDarkness(commands.Cog):
    """A really niche cog for asking a specific person if they've heard
    about the door to darkness.

    I doubt anyone will run this bot but if you decide you want to, make
    sure to change the member id in the constructor.
    """

    def __init__(self, bot):
        self.bot = bot
        self.db_pool = bot.db_pool
        self.door_regex = re.compile(r"door to darkness", re.I)

    async def cog_load(self):
        async with self.db_pool.acquire() as con:
            await con.execute(
                "CREATE TABLE IF NOT EXISTS door_claims (userid BIGINT, guild BIGINT, PRIMARY KEY (userid, guild))"
            )

        self.clear_door_claims.start()

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bot messages
        if message.author.bot:
            return

        # Fetch guild's specific member that has to be mentioned
        mention_id = door_members[message.guild.id]
        if mention_id is None:
            logger.debug(f"No door user configured for guild f{message.guild.name}")
            return

        mention_member = message.guild.get_member(int(mention_id))
        if mention_member is None:
            logger.debug(
                f"Member with id {mention_id} not in guild {message.guild.name}"
            )

        # Users have to mention a specific user
        if mention_member not in message.mentions:
            logger.debug(f"User {message.author.id} didn't mention correct user")
            return

        # Make sure that "door to darkness" is also included in the message
        if re.search(self.door_regex, message.content) is None:
            logger.debug(
                f"User {message.author.id} didn't mention the door to darkness"
            )
            return

        # Make sure that a user hasn't already gotten these points today
        async with self.db_pool.acquire() as con:
            claim_result = await con.execute(
                f"INSERT INTO door_claims VALUES($1, $2) ON CONFLICT(userid, guild) DO NOTHING",
                message.author.id,
                message.guild.id,
            )

        rows_updated = int(claim_result.split(" ")[-1])

        if rows_updated != 0 and (scores := self.bot.get_cog("Scores")) is not None:
            await scores.increment_score(
                message.author, 1, reason="Door to darkness claim"
            )

    @tasks.loop(time=datetime.time(11, 57, 0, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def clear_door_claims(self):
        async with self.db_pool.acquire() as con:
            await con.execute(f"DELETE FROM door_claims")


async def setup(bot):
    await bot.add_cog(DoorToDarkness(bot))
