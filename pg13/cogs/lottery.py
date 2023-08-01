import asyncio
from datetime import datetime, timedelta
import logging
import random
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..config import lottery_channels
from ..common import CogMissing

logger = logging.getLogger(__name__)

MIN_POINTS = 75
MEAN_INCREMENT = 25
EXP_LAMBDA = 1 / MEAN_INCREMENT


def prize_rng():
    """Generates a random lottery prize value.
    The minimum number of points is defined as MIN_POINTS, with the mean prize
    amount being 100 (I think).
    """
    return int(MIN_POINTS + random.expovariate(EXP_LAMBDA))


class Lottery(commands.Cog):
    TICKET_COST = 20

    def __init__(self, bot, scores):
        self.bot = bot
        self.scores = scores
        self.db_pool = bot.db_pool

    async def cog_load(self):
        # table initialization
        async with self.db_pool.acquire() as con:
            # TODO: remove stake column since tickets cost the same for everyone now
            await con.execute(
                "CREATE TABLE IF NOT EXISTS lottery"
                "(guild BIGINT, userid BIGINT, stake INT, PRIMARY KEY(guild, userid))"
            )

        self.lottery_draw.start()

    @property
    def next_draw_time(self):
        """Fetches the next lottery draw time as a datetime.datetime object"""
        # 1-second addition is a hack to make next draw time work properly
        # this breaks if the bot starts up right at a draw time but that's extremely unlikely so ;)
        nowish = datetime.now(
            ZoneInfo("America/Los_Angeles")) + timedelta(seconds=1)
        today_weekday = nowish.weekday()

        # 6 -> Sunday, as represented by datetime.weekday()
        days_until_draw = 6 - today_weekday

        # lottery drawings happen at noon on Sundays
        draw_datetime = (nowish + timedelta(days=days_until_draw)).replace(
            hour=12, minute=0, second=0)

        # used to check if the draw time already passed today
        passed = False

        # draw should have happened earlier the same day; do it now to not miss a week
        if draw_datetime < nowish:
            draw_datetime += timedelta(days=7)
            passed = True

        return draw_datetime, passed

    @app_commands.command(
        description="Buy a lottery ticket for 20 points. Drawings happen every Sunday for 75-250 points."
    )
    async def buyticket(self, interaction: discord.Interaction):
        # store ids for easy access
        guildid = interaction.guild_id
        userid = interaction.user.id

        # we need a configured announcement channel
        if lottery_channels.get(guildid) is None:
            return await interaction.response.send_message(
                "Tell an admin to configure lottery announcements properly :)",
                ephemeral=True,
            )

        async with self.db_pool.acquire() as con:
            already_claimed = await con.fetchval(
                "SELECT TRUE FROM lottery WHERE userid = $1 AND guild = $2",
                userid, guildid)

            if not already_claimed:
                buy_res = await con.execute(
                    """
                    WITH member_info AS (UPDATE scores SET score = score - 20
                        WHERE userid = $1 AND guild = $2 AND scores.score >= 20
                        RETURNING guild, userid)
                    INSERT INTO lottery (guild, userid) (SELECT * FROM member_info)
                    """, userid, guildid)

        next_draw_unix = int(self.next_draw_time[0].timestamp())
        next_draw_timestamp = f"<t:{next_draw_unix}:F>"

        if already_claimed:
            next_draw_unix = int(self.next_draw_time[0].timestamp())
            await interaction.response.send_message(
                "You already entered this week's lottery drawing! "
                f"Check back at {next_draw_timestamp} to see if you win :)",
                ephemeral=True,
            )
        else:
            # INSERT query result has form `INSERT oid count`, where count is the number of updated rows
            updated_rows = int(buy_res.split()[-1])

            if updated_rows == 1:
                await interaction.response.send_message(
                    "You've been entered into this week's lottery drawing! "
                    f"Check back at {next_draw_timestamp} to see if you won :)",
                    ephemeral=True)
            else:
                await interaction.response.send_message(
                    "You need at least 20 points to enter into the lottery :)",
                    ephemeral=True)

    # do a lottery drawing every week at the same time
    @tasks.loop(hours=24 * 7)
    async def lottery_draw(self):
        logger.debug("Doing lottery drawing...")

        # select random winners from each guild
        winners = await self.db_pool.fetch("""
            SELECT DISTINCT ON (guild) guild, userid
                FROM lottery ORDER BY guild, random()
            """)

        next_draw_unix = int(self.next_draw_time[0].timestamp())
        next_draw_timestamp = f"<t:{next_draw_unix}>"
        winner_increments = []

        for winner_record in winners:
            # I don't think you can destructure records directly in a for loop (?)
            guildid, userid = tuple(winner_record)

            # NOTE: this assumes the bot is in the configured guild, as
            # otherwise this throws an AttributeError (guild would be None)
            guild = self.bot.get_guild(guildid)
            win_member = guild.get_member(userid)

            # TODO: refactor to avoid having to do repeated None checks :(
            if win_member is not None:
                # generate prize
                prize = prize_rng()

                # send out winner announcement
                announcement_chan = guild.get_channel(
                    lottery_channels[guildid])
                if announcement_chan is not None:
                    logger.debug(
                        f"{win_member.name} just won lottery in guild {guild.name}")
                    await announcement_chan.send(
                        f"{win_member.mention} just won **{prize}** points in the lottery! "
                        f"The next drawing will be at {next_draw_timestamp}, make sure to get your tickets by then!"
                    )
                    winner_increments.append((win_member, prize))
                else:
                    logger.warn(
                        f"Guild {guildid} didn't have announcement channel with id {lottery_channels[guildid]}"
                    )
            else:
                logger.warn(
                    f"User {userid} not found in guild {guildid} to give points"
                )

        # do bulk increment with all winners
        await self.scores.bulk_increment_scores(winner_increments,
                                                reason="Lottery prizes")

        lottery_guilds = set(lottery_channels.keys())
        winner_guilds = {rec["guild"] for rec in winners}

        # send an announcement in guilds where no one entered this week
        for guildid in lottery_guilds - winner_guilds:
            guild = self.bot.get_guild(guildid)
            announcement_chan = guild.get_channel(lottery_channels[guildid])
            if announcement_chan is not None:
                await announcement_chan.send(
                    "No one entered the lottery this week :(\n"
                    "Reminder that you can win up to 250 points and it only "
                    "costs 20 points to buy a ticket! The next drawing is at "
                    f"{next_draw_timestamp} so make sure to enter by then! :)")

        # clean up purchased tickets in database
        async with self.db_pool.acquire() as con:
            await con.execute("TRUNCATE TABLE lottery")

        logger.debug("Cleared lottery db table")

    @lottery_draw.before_loop
    async def wait_until_draw(self):
        await self.bot.wait_until_ready()
        draw_datetime, passed = self.next_draw_time

        # draw should have happened earlier the same day; do it now to not miss a week
        # TODO: this breaks if the bot goes down multiple times on a draw day;
        # maybe record draws in database/persistent storage somehow?
        if passed:
            logger.warn("Missed a draw; doing it now")
            await self.lottery_draw()

        # datetime.now() has to be called again in case lottery_draw took a while
        logger.debug("Waiting until proper draw time")
        seconds_until_draw = (
            draw_datetime - datetime.now(ZoneInfo("America/Los_Angeles"))).total_seconds()
        await asyncio.sleep(seconds_until_draw)


async def setup(bot):
    if (scores := bot.get_cog("Scores")) is None:
        raise CogMissing("Lottery", "Scores")
    else:
        await bot.add_cog(Lottery(bot, scores))
