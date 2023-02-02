import asyncio
from datetime import datetime, timedelta
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..config import lottery_channels

logger = logging.getLogger(__name__)


class Lottery(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = bot.db_pool

    async def cog_load(self):
        # table initialization
        async with self.db_pool.acquire() as con:
            await con.execute(
                "CREATE TABLE IF NOT EXISTS lottery"
                "(guild BIGINT, userid BIGINT, stake INT, PRIMARY KEY(guild, userid))"
            )

        self.lottery_draw.start()

    @property
    def next_draw_time(self):
        """Fetches the next lottery draw time as a datetime.datetime object"""
        now = datetime.now()
        today_weekday = now.weekday()

        # 6 -> Sunday, as represented by datetime.weekday()
        days_until_draw = 6 - today_weekday

        # lottery drawings happen at noon on Sundays
        draw_datetime = (now + timedelta(days=days_until_draw)).replace(
            hour=12, minute=0, second=0
        )

        # used to check if the draw time already passed today
        passed = False

        # draw should have happened earlier the same day; do it now to not miss a week
        if draw_datetime < now:
            draw_datetime += timedelta(days=7)
            passed = True

        return draw_datetime, passed

    @app_commands.command(
        description="Gamble 5% of your points for a chance to win big :)"
    )
    async def gamble(self, interaction: discord.Interaction):
        # Scores cog is required for gambling to work
        # TODO: move cog requirements to loading process
        if (scores := self.bot.get_cog("Scores")) is None:
            return await interaction.response.send_message(
                "I'm not configured to keep track of points in this server silly :)",
                ephemeral=True,
            )

        # we need a configured announcement channel
        if lottery_channels.get(interaction.guild_id) is None:
            return await interaction.response.send_message(
                "Tell an admin to configure lottery announcements properly :)",
                ephemeral=True,
            )

        # these could probably be golfed into a single request but this is easier to understand anyways
        async with self.db_pool.acquire() as con:
            # used to check if user has enough points to gamble
            score = await con.fetchval(
                "SELECT score FROM scores WHERE userid = $1 AND guild = $2",
                interaction.user.id,
                interaction.guild_id,
            )

            # lottery stake is 5% of a user's score with a 5 point minimum (for now)
            stake = await con.fetchval(
                "INSERT INTO lottery "
                "SELECT guild, userid, floor(score * 0.05) AS stake FROM scores "
                "WHERE userid = $1 AND guild = $2 AND score >= 100"
                "ON CONFLICT (guild, userid) DO NOTHING "
                "RETURNING stake",
                interaction.user.id,
                interaction.guild_id,
            )

        # not enough points (or none at all)
        if score is None or score < 100:
            await interaction.response.send_message(
                "You need at least 100 points to participate in the lottery :)",
                ephemeral=True,
            )

        # user already gambled this week
        elif stake is None:
            next_draw_unix = int(self.next_draw_time[0].timestamp())
            await interaction.response.send_message(
                f"You already gambled this week! Wait until the next drawing (<t:{next_draw_unix}:F>) to see if you win :)",
                ephemeral=True,
            )

        # all good to place a bet
        else:
            # subtract the staked points from the user's score
            await scores.increment_score(
                interaction.user, -stake, reason="Lottery stake"
            )
            await interaction.response.send_message(
                f"You bet {stake} points on the lottery :)", ephemeral=True
            )

    # do a lottery drawing every week at the same time
    @tasks.loop(hours=24 * 7)
    async def lottery_draw(self):
        logger.debug("Doing lottery drawing...")

        async with self.db_pool.acquire() as con:
            winners = await con.fetch(
                "WITH prizes AS (SELECT guild, sum(stake) / 2 AS prize, count(*) AS entrants "
                "FROM lottery GROUP BY guild) "
                "SELECT DISTINCT ON (guild) lottery.guild, userid, prize, entrants "
                "FROM lottery JOIN prizes ON lottery.guild = prizes.guild "
                "ORDER BY guild, random()"
            )

        # yes this is annoying but I need the number of entrants per guild so
        winner_info = [
            (
                self.bot.get_guild(row["guild"]).get_member(row["userid"]),
                row["prize"],
                row["entrants"],
            )
            for row in winners
        ]
        winner_increments = [winner[:2] for winner in winner_info]

        logger.debug(f"winners: {winner_increments}")

        # theoretically the scores cog should always be loaded?
        if (scores := self.bot.get_cog("Scores")) is not None:
            await scores.bulk_increment_scores(
                winner_increments, reason="Lottery winnings"
            )

        next_draw_unix = int(self.next_draw_time[0].timestamp())

        for member, points, entrants in winner_info:
            guild = member.guild

            # configured announcement channel is guaranteed to exist at this point
            win_channel = guild.get_channel(lottery_channels[guild.id])

            # yay weird plurals
            entrants_phrase = "person" if entrants == 1 else "people"

            # ooo timestamps
            await win_channel.send(
                f"{member.mention} just won **{points}** points in the lottery! "
                f"({entrants} {entrants_phrase} entered this round)\n"
                f"The next drawing will be at <t:{next_draw_unix}>, make sure to get your bets in by then!"
            )
        logger.debug("Finished sending out winner announcements")

        # draws can be cleaned up since points have been given out & winners announced
        async with self.db_pool.acquire() as con:
            await con.execute("TRUNCATE TABLE lottery")

        logger.debug("Cleared lottery db table")

    @lottery_draw.before_loop
    async def wait_until_draw(self):
        await self.bot.wait_until_ready()
        now = datetime.now()
        draw_datetime, passed = self.next_draw_time

        # draw should have happened earlier the same day; do it now to not miss a week
        if passed:
            logger.warn("Missed a draw; doing it now")
            await self.lottery_draw()

        # datetime.now() has to be called again in case lottery_draw took a while
        logger.debug("Waiting until proper draw time")
        seconds_until_draw = (draw_datetime - datetime.now()).total_seconds()
        await asyncio.sleep(seconds_until_draw)


async def setup(bot):
    await bot.add_cog(Lottery(bot))
