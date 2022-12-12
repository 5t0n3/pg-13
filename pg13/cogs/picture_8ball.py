import discord
from discord import app_commands
from discord.ext import commands

import logging
import pathlib
import random

logger = logging.getLogger(__name__)


class Picture8Ball(commands.Cog):
    @commands.command(
        name="ask", description="Receive an answer from the almighty oracle (me)."
    )
    async def ask(self, ctx: commands.Context):
        response_dir = pathlib.Path(f"8ball/{ctx.guild.id}")

        if not response_dir.is_dir():
            await ctx.reply(
                "I'm not configured to answer your questions in this server silly :)",
                mention_author=False,
            )
            return

        responses = list(response_dir.iterdir())
        random_response = random.choice(responses)

        with open(random_response, "rb") as resp:
            await ctx.reply(
                file=discord.File(resp, filename=random_response.name),
                mention_author=False,
            )


async def setup(bot):
    await bot.add_cog(Picture8Ball())
