import logging

import aiosqlite
import discord
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType as OptionType
from discord_slash.context import SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice

from .slash_config import loaded_guilds, admin_perms


class Scores(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.scores")

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

    @cog_ext.cog_slash(
        name="leaderboard",
        description="Display the score leaderboard for the current server.",
        **loaded_guilds,
    )
    async def leaderboard(self, ctx: SlashContext):
        # Fetch top 15 guild scores
        async with aiosqlite.connect("databases/scores.db") as scores:
            user_scores = await scores.execute_fetchall(
                f"SELECT user, cumulative FROM guild_{ctx.guild_id} ORDER BY cumulative DESC"
            )

        guild = self.bot.get_guild(ctx.guild_id)

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

        await ctx.send(embed=leaderboard)

    @cog_ext.cog_slash(
        name="total",
        description="Check the total amount of points of members in this server.",
        **loaded_guilds,
    )
    async def total(self, ctx: SlashContext):
        guild_total = 0

        # Sum up all scores within the server
        async with aiosqlite.connect("databases/scores.db") as scores:
            async with scores.execute(
                f"SELECT cumulative FROM guild_{ctx.guild_id}"
            ) as guild_scores:
                async for (score,) in guild_scores:
                    guild_total += score

        await ctx.send(f"Total points for this server: **{guild_total}**")

    @cog_ext.cog_slash(
        name="rank",
        description="Display a user's rank & score in this server.",
        options=[
            create_option(
                name="user",
                description="The user to display the rank of (default you).",
                option_type=OptionType.USER,
                required=False,
            ),
        ],
        **loaded_guilds,
    )
    async def rank(self, ctx: SlashContext, user=None):
        if user is None:
            user = ctx.author

        # TODO: Implement caching of guild leaderboards
        # Get guild & user's score(s) for standings comparison
        async with aiosqlite.connect("databases/scores.db") as scores:
            guild_standings = await scores.execute_fetchall(
                f"SELECT DISTINCT cumulative FROM guild_{ctx.guild_id} ORDER BY cumulative DESC"
            )

            user_request = await scores.execute(
                f"SELECT cumulative FROM guild_{ctx.guild_id} WHERE user = ?",
                (user.id,),
            )
            user_row = await user_request.fetchone()

        # Row doesn't exist -> user hasn't gotten any points yet
        if user_row is None:
            return await ctx.send("That user doesn't have any points yet!")

        # Rank by correct score
        user_score = user_row[0]

        # Fetch user's place (treating ties as a single place)
        user_rank = next(
            filter(
                lambda row: row[1][0] == user_score, enumerate(guild_standings, start=1)
            )
        )[0]

        await ctx.send(
            f"{user.name} is in **{self.make_ordinal(user_rank)} place** with **{user_score}** points."
        )

    @cog_ext.cog_subcommand(
        base="score",
        name="set",
        description="Set a user's score to a specific value.",
        options=[
            create_option(
                name="user",
                description="The user whose score to set.",
                option_type=OptionType.USER,
                required=True,
            ),
            create_option(
                name="points",
                description="The user's new score.",
                option_type=OptionType.INTEGER,
                required=True,
            ),
        ],
        **loaded_guilds,
        **admin_perms,
    )
    async def score_set(self, ctx: SlashContext, user, points):
        # Bots are ignored for score purposes
        if user.bot:
            return await ctx.send(f"{user.name} is a bot and cannot get points.")

        # Update user's score in guild database table
        async with aiosqlite.connect("databases/scores.db") as scores:
            await scores.execute(
                f"INSERT INTO guild_{ctx.guild_id}(user, cumulative) VALUES(?, ?) "
                f"ON CONFLICT(user) DO UPDATE SET cumulative = ?",
                (user.id, points, points),
            )
            await scores.commit()

        # Update bonus roles, if applicable
        if (bonus_cog := self.bot.get_cog("BonusRoles")) is not None:
            await bonus_cog.update_bonus_roles(user.guild)

        await ctx.send(f"Successfully updated {user.name}'s score to **{points}**!")
        self.logger.info(f"Successfully updated {user.name}'s score to {points}")

    @cog_ext.cog_subcommand(
        base="score",
        name="adjust",
        description="Give points to or take points away from a user.",
        options=[
            create_option(
                name="user",
                description="The user whose score to change.",
                option_type=OptionType.USER,
                required=True,
            ),
            create_option(
                name="points",
                description="The number of points to give or take away.",
                option_type=OptionType.INTEGER,
                required=True,
            ),
            create_option(
                name="mode",
                description="Whether to give or take points (default give).",
                option_type=OptionType.STRING,
                required=False,
                choices=[
                    create_choice(value="increment", name="Give user points"),
                    create_choice(value="decrement", name="Take points away from user"),
                ],
            ),
        ],
        **loaded_guilds,
        **admin_perms,
    )
    async def score_adjust(self, ctx: SlashContext, user, points, mode="increment"):
        # Bots are ignored for score purposes
        if user.bot:
            return await ctx.send(f"{user.name} is a bot and cannot get points.")

        # Negate change if decrementing
        if mode == "decrement":
            points = -points

        # Update scores in database
        await self.update_scores(user, points)

        if mode == "increment":
            await ctx.send(f"Gave {user.name} {points} points!")

        # (mode == "decrement")
        else:
            await ctx.send(f"Took {-points} points from {user.name}!")

        self.logger.info(f"Changed {user.name}'s cumulative score by {points} points.")

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

        self.logger.info(
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


def setup(bot):
    bot.add_cog(Scores(bot))
