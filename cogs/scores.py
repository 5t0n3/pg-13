import logging

import aiosqlite
import discord
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType as OptionType
from discord_slash.context import SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice

from .guild_ids import GUILD_IDS


class ScoresCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.scores")

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_guild_scores()

    async def init_guild_scores(self):
        async with aiosqlite.connect("databases/scores.db") as scores:
            for guild in self.bot.guilds:
                # TODO: Split score into cumulative/current scores
                await scores.execute(
                    f"CREATE TABLE IF NOT EXISTS "
                    f"guild_{guild.id}(user INT PRIMARY KEY, current INT, cumulative INT)"
                )

            await scores.commit()
        self.logger.info("Successfully initialized all guild score tables.")

    @cog_ext.cog_slash(
        name="leaderboard",
        description="Display the score leaderboard for the current server.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="sort",
                description="Which score to order users by (default cumulative)",
                option_type=OptionType.STRING,
                required=False,
                choices=[
                    create_choice(value="cumulative", name="Cumulative score"),
                    create_choice(value="current", name="Current score"),
                ],
            )
        ],
    )
    async def leaderboard(self, ctx: SlashContext, sort="cumulative"):
        # Fetch top 10 guild scores
        async with aiosqlite.connect("databases/scores.db") as scores:
            user_scores = await scores.execute_fetchall(
                f"SELECT * FROM guild_{ctx.guild_id} ORDER BY {sort} DESC LIMIT 15"
            )

        guild = self.bot.get_guild(ctx.guild_id)

        # Initialize embed
        leaderboard = discord.Embed(title=f"{guild.name} Leaderboard", description="")
        leaderboard.set_footer(text=f"(sorted by {sort} score)")

        # Used to deal with score ties
        place = 1
        previous_score = None

        # Convert rows to leaderboard
        for user_id, current, cumulative in user_scores:
            member = guild.get_member(user_id)

            if sort == "cumulative":
                if cumulative != previous_score:
                    place_str = f"{place}:"
                    place += 1
                else:
                    place_str = " "

                leaderboard.description += f"{place_str} {member.mention} - {cumulative} points (current {current})\n"
                previous_score = cumulative

            # Ordered by current score
            else:
                if current != previous_score:
                    place_str = f"{place}:"
                    place += 1
                else:
                    place_str = " "

                leaderboard.description += f"{place_str} {member.mention} - {current} points (cumulative {cumulative})\n"
                previous_score = current

        await ctx.send(embed=leaderboard)

    @cog_ext.cog_slash(
        name="rank",
        description="Display a user's rank & score in this server.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="score_type",
                description="Which score to rank the user based on (default cumulative).",
                option_type=OptionType.STRING,
                required=False,
                choices=[
                    create_choice(value="cumulative", name="Cumulative score"),
                    create_choice(value="current", name="Current score"),
                ],
            ),
            create_option(
                name="user",
                description="The user to display the rank of (default you).",
                option_type=OptionType.USER,
                required=False,
            ),
        ],
    )
    async def rank(self, ctx: SlashContext, score_type="cumulative", user=None):
        if user is None:
            user = ctx.author

        # TODO: Implement caching of guild leaderboards
        # Get guild & user's score(s) for standings comparison
        async with aiosqlite.connect("databases/scores.db") as scores:
            guild_standings = await scores.execute_fetchall(
                f"SELECT DISTINCT {score_type} FROM guild_{ctx.guild_id} ORDER BY {score_type} DESC"
            )

            user_request = await scores.execute(
                f"SELECT {score_type} FROM guild_{ctx.guild_id} WHERE user = ?",
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
            f"{user.name} is in **{self.make_ordinal(user_rank)} place** with **{user_score}** ({score_type}) points."
        )

    # TODO: Split into 2 commands: set & something for giving/taking points (flag for which one)
    @cog_ext.cog_subcommand(
        base="score",
        name="set",
        description="Set a user's score to a specific value.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="user",
                description="The user whose score to set.",
                option_type=OptionType.USER,
                required=True,
            ),
            create_option(
                name="score",
                description="The user's new score.",
                option_type=OptionType.INTEGER,
                required=True,
            ),
            # TODO: Add flag for changing current/cumulative score?
        ],
    )
    async def score_set(self, ctx: SlashContext, user, score):
        # Bots are ignored for score purposes
        if user.bot:
            return await ctx.send(f"{user.name} is a bot and cannot get points.")

        # Update cumulative & current scores
        await self.update_scores(user, score)

        await ctx.send(f"Successfully updated {user.name}'s score to **{score}**!")

    @cog_ext.cog_subcommand(
        base="score",
        name="adjust",
        description="Give points to or take points away from a user.",
        guild_ids=GUILD_IDS,
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
    )
    async def score_adjust(self, ctx: SlashContext, user, points, mode="increment"):
        # Bots are ignored for score purposes
        if user.bot:
            return await ctx.send(f"{user.name} is a bot and cannot get points.")

        # Negate change if decrementing
        if mode == "decrement":
            points = -points

        # Update scores in database
        await self.update_scores(user, points, adjust=True)

        if mode == "increment":
            await ctx.send(f"Gave {user.name} {points} points!")

        # (mode == "decrement")
        else:
            await ctx.send(f"Took {-points} points from {user.name}!")

        self.logger.info(f"Changed {user.name}'s current score by {points} points.")

    async def update_scores(self, member, points, adjust=False):
        """Updates both a user's current and cumulative scores"""
        async with aiosqlite.connect("databases/scores.db") as scores:
            # Fetch current score for updating cumulative
            current_request = await scores.execute(
                f"SELECT current FROM guild_{member.guild.id} WHERE user = ?",
                (member.id,),
            )
            current_score = await current_request.fetchone()

            # Default to 0 if score doesn't exist
            current_score = (current_score or (0,))[0]

            # Incrementing/decrementing score
            if adjust:
                new_score = current_score + points

            # Directly setting score
            else:
                new_score = points

            # The cumulative score should only increase
            cumulative_change = max(new_score - current_score, 0)

            await scores.execute(
                f"INSERT INTO guild_{member.guild.id} VALUES(?, ?, ?) ON CONFLICT(user) "
                "DO UPDATE SET current = ?, cumulative = cumulative + ?",
                (member.id, new_score, new_score, new_score, cumulative_change),
            )

            await scores.commit()

        # TODO: Also log cumulative score?
        self.logger.info(f"Updated {member.name}'s current score to {new_score}")

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
    bot.add_cog(ScoresCog(bot))
