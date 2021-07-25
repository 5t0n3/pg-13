import logging

import aiosqlite
from discord.ext import commands


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


def setup(bot):
    bot.add_cog(ScoresCog(bot))
