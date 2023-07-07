import discord
from discord.ext import commands

import logging
import pathlib
import random
import re

logger = logging.getLogger(__name__)

# file name format: <name>-<weight>.png (or another file format ig)
WEIGHT_RE = re.compile(r".+-(\d+)")


def choose_response(response_dir):
    responses = []
    cumulative_weights = [0]

    for resp_file in response_dir.iterdir():
        responses.append(resp_file)

        weight = int(WEIGHT_RE.match(resp_file.name).group(1))
        cumulative_weights.append(cumulative_weights[-1] + weight)

    # only random.choices supports weights, so it's just used here to select a single element
    return random.choices(responses, cum_weights=cumulative_weights[1:])[0]


class Picture8Ball(commands.Cog):

    @commands.command(
        name="ask",
        description="Receive an answer from the almighty oracle (me).")
    async def ask(self, ctx: commands.Context):
        response_dir = pathlib.Path(f"8ball/{ctx.guild.id}")

        if not response_dir.is_dir():
            await ctx.reply(
                "I'm not configured to answer your questions in this server silly :)",
                mention_author=False,
            )

        else:
            response = choose_response(response_dir)

            with open(response, "rb") as resp:
                await ctx.reply(
                    file=discord.File(resp, filename=response.name),
                    mention_author=False,
                )


async def setup(bot):
    await bot.add_cog(Picture8Ball())
