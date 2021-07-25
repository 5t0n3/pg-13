import logging

import aiosqlite
import discord
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType as OptionType
from discord_slash.context import SlashContext
from discord_slash.utils.manage_commands import create_option

from .guild_ids import GUILD_IDS


class ScoresCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.scores")

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_guild_scores()

    async def init_guild_scores(self):
        async with aiosqlite.connect("scores.db") as scores:
            for guild in self.bot.guilds:
                await scores.execute(
                    f"CREATE TABLE IF NOT EXISTS guild_{guild.id}(user INT PRIMARY KEY, score INT)"
                )

            await scores.commit()
            self.logger.info("Successfully initialized all guild score tables.")

    @cog_ext.cog_slash(
        name="leaderboard",
        description="Display the score leaderboard for the current server.",
        guild_ids=GUILD_IDS,
    )
    async def leaderboard(self, ctx: SlashContext):
        # Fetch top 10 guild scores
        async with aiosqlite.connect("scores.db") as scores:
            user_scores = await scores.execute_fetchall(
                f"SELECT * FROM guild_{ctx.guild_id} ORDER BY score DESC LIMIT 10"
            )

        guild = self.bot.get_guild(ctx.guild_id)
        # Convert rows to leaderboard
        formatted_leaderboard = ""
        for place, (user_id, score) in enumerate(user_scores, start=1):
            member = guild.get_member(user_id)
            formatted_leaderboard += f"{place}: {member.mention} - {score}"

        leaderboard_embed = discord.Embed(
            title=f"{guild.name} Leaderboard", description=formatted_leaderboard
        )
        await ctx.send(embed=leaderboard_embed)

    @cog_ext.cog_slash(
        name="rank",
        description="Display a user's rank & score in this server.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="user",
                description="The user to display the rank of (default you).",
                option_type=OptionType.USER,
                required=False,
            )
        ],
    )
    async def rank(self, ctx: SlashContext, user=None):
        if user is None:
            user = ctx.author

        # TODO: Implement caching of guild leaderboards
        # Get guild & user's score(s) for standings comparison
        async with aiosqlite.connect("scores.db") as scores:
            guild_standings = await scores.execute_fetchall(
                f"SELECT DISTINCT score FROM guild_{ctx.guild_id} ORDER BY score DESC"
            )

            async with scores.execute(
                f"SELECT score FROM guild_{ctx.guild_id} WHERE user = ?",
                (user.id,),
            ) as user_cursor:
                user_row = await user_cursor.fetchone()

        # Row doesn't exist -> user hasn't gotten any points yet
        if user_row is None:
            return await ctx.send("That user doesn't have any points yet!")

        # Fetch user's place (treating ties as a single place)
        user_score = user_row[0]
        user_rank = next(
            filter(
                lambda row: row[1][0] == user_score, enumerate(guild_standings, start=1)
            )
        )[0]

        await ctx.send(
            f"{user.name} is in **{self.make_ordinal(user_rank)} place** with **{user_score}** points."
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
    bot.add_cog(ScoresCog(bot))
