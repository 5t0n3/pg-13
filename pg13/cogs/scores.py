import logging

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from .cog_config import configured_guilds, admin_check


class Scores(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.scores")

    score_group = app_commands.Group(
        name="score",
        description="Score manipulation commands",
        guild_ids=configured_guilds,
    )

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_guild_scores()

    async def init_guild_scores(self):
        async with aiosqlite.connect("databases/scores.db") as scores:
            for guild in self.bot.guilds:
                await scores.execute(
                    f"CREATE TABLE IF NOT EXISTS "
                    f"guild_{guild.id}(user INT PRIMARY KEY, cumulative INT)"
                )

            await scores.commit()
        self.logger.info("Successfully initialized all guild score tables.")

    @app_commands.command(
        name="leaderboard",
        description="Display the score leaderboard for the current server.",
    )
    @app_commands.guilds(*configured_guilds)
    async def leaderboard(self, interaction: discord.Interaction):
        # Fetch top 15 guild scores
        async with aiosqlite.connect("databases/scores.db") as scores:
            user_scores = await scores.execute_fetchall(
                f"SELECT user, cumulative FROM guild_{interaction.guild_id} ORDER BY cumulative DESC"
            )

        guild = self.bot.get_guild(interaction.guild_id)

        # Initialize embed
        leaderboard = discord.Embed(title=f"{guild.name} Leaderboard", description="")

        # Used to deal with score ties
        place = 1
        previous_score = None

        # Convert rows to leaderboard
        for user_id, cumulative in user_scores:
            member = guild.get_member(user_id)

            # Skip users that are no longer in the server
            if member is None:
                continue

            if cumulative != previous_score:
                place_str = f"{place}:"
                place += 1
            else:
                place_str = "  "

            leaderboard.description += (
                f"{place_str} {member.mention} - {cumulative} points\n"
            )

            previous_score = cumulative

            # Only take the first 15 users
            # TODO: Implement pagination of the leaderboard
            if place > 15:
                break

        await interaction.response.send_message(embed=leaderboard)

    @app_commands.command(
        name="total",
        description="Check the total amount of points of members in this server.",
    )
    @app_commands.guilds(*configured_guilds)
    async def total(self, interaction: discord.Interaction):
        guild_total = 0

        # Sum up all scores within the server
        async with aiosqlite.connect("databases/scores.db") as scores:
            async with scores.execute(
                f"SELECT cumulative FROM guild_{interaction.guild_id}"
            ) as guild_scores:
                async for (score,) in guild_scores:
                    guild_total += score

        await interaction.response.send_message(
            f"Total points for this server: **{guild_total}**"
        )

    @app_commands.command(
        name="rank",
        description="Display a user's rank & score in this server.",
    )
    @app_commands.describe(user="The user to display the rank of (default you).")
    @app_commands.guilds(*configured_guilds)
    async def rank(self, interaction: discord.Interaction, user: discord.Member = None):
        if user is None:
            user = interaction.user

        # TODO: Implement caching of guild leaderboards
        # Get guild & user's score(s) for standings comparison
        async with aiosqlite.connect("databases/scores.db") as scores:
            guild_standings = await scores.execute_fetchall(
                f"SELECT DISTINCT cumulative FROM guild_{interaction.guild_id} ORDER BY cumulative DESC"
            )

            user_request = await scores.execute(
                f"SELECT cumulative FROM guild_{interaction.guild_id} WHERE user = ?",
                (user.id,),
            )
            user_row = await user_request.fetchone()

        # Row doesn't exist -> user hasn't gotten any points yet
        if user_row is None:
            return await interaction.response.send_message(
                "That user doesn't have any points yet!"
            )

        # Rank by correct score
        user_score = user_row[0]

        # Fetch user's place (treating ties as a single place)
        user_rank = next(
            filter(
                lambda row: row[1][0] == user_score, enumerate(guild_standings, start=1)
            )
        )[0]

        await interaction.response.send_message(
            f"{user.name} is in **{self.make_ordinal(user_rank)} place** with **{user_score}** points."
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
        async with aiosqlite.connect("databases/scores.db") as scores:
            await scores.execute(
                f"INSERT INTO guild_{interaction.guild_id}(user, cumulative) VALUES(?, ?) "
                f"ON CONFLICT(user) DO UPDATE SET cumulative = ?",
                (user.id, points, points),
            )
            await scores.commit()

        # Update bonus roles, if applicable
        if (bonus_cog := self.bot.get_cog("BonusRoles")) is not None:
            await bonus_cog.update_bonus_roles(user.guild)

        await interaction.response.send(
            f"Successfully updated {user.name}'s score to **{points}**!"
        )
        self.logger.debug(f"Successfully updated {user.name}'s score to {points}")

    @score_group.command(
        name="adjust", description="Give points to or take points away from a user."
    )
    @app_commands.describe(
        user="Member to adjust score of", points="Amount of points to give/take away"
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
        await self.update_scores(user, points)

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

        self.logger.debug(f"Changed {user.name}'s score by {points} points.")

    # TODO: add a reason parameter for logging purposes
    async def update_scores(self, member, points, update_roles=True):
        """Updates a user's cumulative score by some amount"""
        async with aiosqlite.connect("databases/scores.db") as scores:
            # Only update the user's cumulative score (current score is no longer used)
            await scores.execute(
                f"INSERT INTO guild_{member.guild.id}(user, cumulative) VALUES(?, ?) ON CONFLICT(user) "
                "DO UPDATE SET cumulative = cumulative + ?",
                (member.id, points, points),
            )

            # Get the new cumulative score for logging purposes
            new_cumulative_req = await scores.execute(
                f"SELECT cumulative FROM guild_{member.guild.id} WHERE user = ?",
                (member.id,),
            )
            new_cumulative = await new_cumulative_req.fetchone()

            await scores.commit()

        if update_roles and (bonus_cog := self.bot.get_cog("BonusRoles")) is not None:
            await bonus_cog.update_bonus_roles(member.guild)

        self.logger.debug(
            f"Updated {member.name}'s cumulative score to {new_cumulative}"
        )

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
