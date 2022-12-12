import discord
from discord import app_commands
from discord.ext import commands

import logging
import pathlib
import random

logger = logging.getLogger(__name__)


class Picture8Ball(commands.Cog):
    @app_commands.command(
        name="ask", description="Receive an answer from the almighty oracle (me)."
    )
    @app_commands.describe(question="The question you require an answer to")
    async def ask(self, interaction: discord.Interaction, question: str):
        response_dir = pathlib.Path(f"8ball/{interaction.guild_id}")

        if not response_dir.is_dir():
            await interaction.response.send_message(
                "I'm not configured to answer your questions in this server silly :)",
                ephemeral=True,
            )
            return

        responses = list(response_dir.iterdir())
        random_response = random.choice(responses)

        with open(random_response, "rb") as resp:
            await interaction.response.send_message(file=discord.File(resp))


async def setup(bot):
    await bot.add_cog(Picture8Ball())
