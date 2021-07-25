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


def setup(bot):
    bot.add_cog(ScoresCog(bot))
