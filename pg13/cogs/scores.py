import logging
import sqlite3

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from .cog_config import configured_guilds, admin_check


class Scores(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.scores")
        self.init_db_table()

    def init_db_table(self):
        db = sqlite3.connect("pg-13.db")
        db.execute(
            "CREATE TABLE IF NOT EXISTS scores"
            "(guild INT, user INT, score INT, UNIQUE(guild, user))"
        )
        db.close()

    score_group = app_commands.Group(
        name="score",
        description="Score manipulation commands",
        guild_ids=configured_guilds,
    )

    @app_commands.command(
        name="leaderboard",
        description="Display the score leaderboard for the current server.",
    )
    @app_commands.guilds(*configured_guilds)
    async def leaderboard(self, interaction: discord.Interaction):
        leaderboard = discord.Embed(
            title=f"{interaction.guild.name} Leaderboard", description=""
        )
        place = 1
        previous_score = None

        async with aiosqlite.connect("pg-13.db") as db:
            db.row_factory = aiosqlite.Row

            async with db.execute("SELECT * FROM scores ORDER BY score DESC") as scores:
                async for row in scores:
                    if (
                        member := interaction.guild.get_member(row["user"])
                    ) is not None:
                        leaderboard.description += (
                            f"{place}: {member.mention} - {row['score']} points\n"
                        )

                        if place > 15:
                            break

                        place += 1
                        previous_score = row["user"]

        # TODO: Record the leaderboard message id for pagination purposes

        await interaction.response.send_message(embed=leaderboard)

    @app_commands.command(
        name="total",
        description="Check the total amount of points of members of this server.",
    )
    @app_commands.guilds(*configured_guilds)
    async def total(self, interaction: discord.Interaction):
        guild_total = 0

        async with aiosqlite.connect("pg-13.db") as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                f"SELECT score FROM scores WHERE guild = {interaction.guild_id}"
            ) as guild_scores:
                async for row in guild_scores:
                    guild_total += row["score"]

        await interaction.response.send_message(
            f"Total points for this server: **{guild_total}**"
        )

    # TODO: Remove after leaderboard pagination is implemented?
    @app_commands.command(
        name="rank",
        description="Display a user's rank & score in this server.",
    )
    @app_commands.describe(user="The user to display the rank of (default you).")
    @app_commands.guilds(*configured_guilds)
    async def rank(self, interaction: discord.Interaction, user: discord.Member = None):
        if user is None:
            user = interaction.user

        if user.bot:
            return await interaction.response.send_message(
                "Bots can't get points silly :)", ephemeral=True
            )

        place = 1

        async with aiosqlite.connect("pg-13.db") as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                "SELECT score FROM scores WHERE guild = ? AND user = ?",
                (interaction.guild_id, user.id),
            ) as user_request:
                user_row = await user_request.fetchone()

            if user_row is None:
                return await interaction.response.send_message(
                    "That user doesn't have any points yet!", ephemeral=True
                )

            user_score = user_row["score"]

            # TODO: Should this be distinct?
            async with db.execute(
                "SELECT score FROM scores "
                f"WHERE guild = {interaction.guild_id} ORDER BY score DESC"
            ) as scores:
                async for row in scores:
                    if row["score"] == user_score:
                        break

                    place += 1

        await interaction.response.send_message(
            f"{user.name} is in **{self.make_ordinal(place)} place** with **{user_score}** points."
        )

    @score_group.command(
        name="set",
        description="Set a user's score to a specific value.",
    )
    async def score_set(
        self, interaction: discord.Interaction, user: discord.Member, points: int
    ):
        # Bots are ignored for score purposes
        if user.bot:
            return await interaction.response.send(
                f"{user.name} is a bot and cannot get points.", ephemeral=True
            )

        # Update user's score in guild database table
        async with aiosqlite.connect("pg-13.db") as db:
            await db.execute(
                f"INSERT INTO scores VALUES(?, ?, ?) "
                f"ON CONFLICT(guild, user) DO UPDATE SET score = ?",
                (interaction.guild_id, user.id, points, points),
            )

            await db.commit()

        self.logger.debug(f"Updated {user.name}'s score to {points}")

        # Update bonus roles, if applicable
        if (bonus_cog := self.bot.get_cog("BonusRoles")) is not None:
            await bonus_cog.update_bonus_roles(user.guild)

        await interaction.response.send_message(
            f"Successfully updated {user.name}'s score to **{points}**!"
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
        # TODO: Move to a group-wide check?
        if user.bot:
            return await interaction.response.send_message(
                f"{user.name} is a bot and cannot get points."
            )

        # Update scores in database
        await self.increment_score(user, points)

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

    # TODO: add a reason parameter for logging purposes
    async def increment_score(self, member, points, update_roles=True):
        """Changes a user's score by some amount"""
        async with aiosqlite.connect("pg-13.db") as db:
            await db.execute(
                "INSERT INTO scores VALUES(?, ?, ?) ON CONFLICT(guild, user) "
                "DO UPDATE SET score = score + ?",
                (member.guild.id, member.id, points, points),
            )
            await db.commit()

        if update_roles and (bonus_cog := self.bot.get_cog("BonusRoles")) is not None:
            await bonus_cog.update_bonus_roles(member.guild)

        self.logger.debug(f"Changed {member.name}'s score by {points} points.")

    def make_ordinal(self, n):
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


async def setup(bot):
    await bot.add_cog(Scores(bot))
