import itertools
import logging

import discord
from discord import app_commands
from discord.ext import commands

from .cog_config import admin_check
from .views import Leaderboard

logger = logging.getLogger(__name__)


def make_ordinal(n):
    """
    Convert an integer into its ordinal representation::

        make_ordinal(0)   => '0th'
        make_ordinal(3)   => '3rd'
        make_ordinal(122) => '122nd'
        make_ordinal(213) => '213th'

    (taken from https://stackoverflow.com/a/50992575)
    """
    n = int(n)
    suffix = ["th", "st", "nd", "rd", "th"][min(n % 10, 4)]
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    return str(n) + suffix


class Scores(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = bot.db_pool

    async def cog_load(self):
        async with self.db_pool.acquire() as con:
            await con.execute(
                "CREATE TABLE IF NOT EXISTS scores"
                "(guild BIGINT, userid BIGINT, score INT, UNIQUE(guild, userid))"
            )

    score_group = app_commands.Group(
        name="score",
        description="Score manipulation commands",
    )

    @app_commands.command(
        name="leaderboard",
        description="Display the score leaderboard for the current server.",
    )
    async def leaderboard(self, interaction: discord.Interaction):
        leaderboard_view = Leaderboard(interaction.guild, self.db_pool)
        await leaderboard_view.init_leaderboard(interaction)

    @app_commands.command(
        name="total",
        description="Check the total amount of points of members of this server.",
    )
    async def total(self, interaction: discord.Interaction):
        async with self.db_pool.acquire() as con:
            guild_total = await con.fetchval(
                "SELECT sum(score) FROM scores WHERE guild = $1", interaction.guild_id
            )

        if guild_total is None:
            await interaction.response.send_message(
                "No users have points in this server."
            )
        else:
            await interaction.response.send_message(
                f"Total points for this server: **{guild_total}**"
            )

    @app_commands.command(
        name="rank",
        description="Display a user's rank & score in this server.",
    )
    @app_commands.describe(user="The user to display the rank of (default you)")
    async def rank(self, interaction: discord.Interaction, user: discord.Member = None):
        if user is None:
            user = interaction.user

        if user.bot:
            return await interaction.response.send_message(
                "Bots can't get points silly :)", ephemeral=True
            )

        async with self.db_pool.acquire() as con:
            at_least_equal = await con.fetch(
                "WITH guild_scores AS (SELECT score, userid FROM scores WHERE guild = $1), "
                "user_score as (SELECT score FROM guild_scores WHERE userid = $2) "
                "SELECT score, userid FROM guild_scores WHERE score >= (SELECT score FROM user_score) "
                "ORDER BY score DESC",
                interaction.guild_id,
                user.id,
            )

        if not at_least_equal:
            return await interaction.response.send_message(
                "That user doesn't have any points yet.", ephemeral=True
            )

        user_score = at_least_equal[-1]["score"]

        in_guild = [
            member.id
            for row in at_least_equal
            if (member := interaction.guild.get_member(row["userid"])) is not None
        ]
        members_ahead = list(
            itertools.takewhile(lambda member_id: member_id != user.id, in_guild)
        )
        place = len(members_ahead) + 1

        await interaction.response.send_message(
            f"{user.name} is in **{make_ordinal(place)} place** with **{user_score}** points."
        )

    @score_group.command(
        name="set",
        description="Set a user's score to a specific value.",
    )
    @app_commands.describe(
        user="Whose score to set", score="The specified user's new score"
    )
    async def score_set(
        self, interaction: discord.Interaction, user: discord.Member, score: int
    ):
        # Bots are ignored for score purposes
        if user.bot:
            return await interaction.response.send(
                f"{user.name} is a bot and cannot get points.", ephemeral=True
            )

        # Update user's score in guild database table
        async with self.db_pool.acquire() as con:
            await con.execute(
                f"INSERT INTO scores VALUES($1, $2, $3) "
                f"ON CONFLICT(guild, userid) DO UPDATE SET score = EXCLUDED.score",
                interaction.guild_id,
                user.id,
                score,
            )

        logger.debug(f"Updated {user.name}'s score to {score}")

        # Update bonus roles, if applicable
        if (bonus_cog := self.bot.get_cog("BonusRoles")) is not None:
            await bonus_cog.update_bonus_roles(user.guild)

        await interaction.response.send_message(
            f"Successfully updated {user.name}'s score to **{score}**!"
        )

    @score_group.command(
        name="adjust", description="Give points to or take points away from a user."
    )
    @app_commands.describe(
        user="Member to give/take points from",
        points="Amount of points to give/take",
    )
    @app_commands.check(admin_check)
    async def score_adjust(
        self, interaction: discord.Interaction, user: discord.Member, points: int
    ):
        # Bots are ignored for score purposes
        if user.bot:
            return await interaction.response.send_message(
                f"{user.name} is a bot and cannot get points."
            )

        # Update scores in database
        await self.increment_score(user, points, reason="User score adjusted")

        # Incrementing user score
        if points >= 0:
            await interaction.response.send_message(
                f"Gave {user.name} {points} points!"
            )

        # Decrementing user score
        else:
            await interaction.response.send_message(
                f"Took {-points} points from {user.name}!"
            )

    async def increment_score(self, member, points, reason=None):
        await self.bulk_increment_scores(member.guild, [(member.id, points)], reason)

    # TODO: add a reason parameter for logging purposes
    async def bulk_increment_scores(self, guild, increments, reason=None):
        """Changes a user's score by some amount"""
        async with self.db_pool.acquire() as con:
            await con.executemany(
                "INSERT INTO scores VALUES($1, $2, $3) ON CONFLICT(guild, userid) "
                "DO UPDATE SET score = scores.score + $3",
                [(guild.id, *increment) for increment in increments],
            )

        affected_users = ", ".join(
            map(lambda inc: f"{inc[0]} -> {inc[1]} points", increments)
        )
        logger.debug(
            f"User score increments: {affected_users}" + f" (reason: {reason})"
            if reason is not None
            else ""
        )

        if (bonus_cog := self.bot.get_cog("BonusRoles")) is not None:
            await bonus_cog.update_bonus_roles(guild)


async def setup(bot):
    await bot.add_cog(Scores(bot))
