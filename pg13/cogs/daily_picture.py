import datetime
import logging
import pathlib
import random
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..config import picture_channels

logger = logging.getLogger(__name__)


class DailyPicture(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # TODO: change to non-test time
    @tasks.loop(time=datetime.time(16, 25, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def send_pictures(self):
        for guild_id, channel_id in picture_channels:
            if (guild := self.bot.get_guild(guild_id)) is None:
                logger.warn(f"Unable to fetch guild {guild_id}")

            elif (picture_channel := guild.get_channel(channel_id)) is None:
                logger.warn(f"Guild {guild.name} has no channel with id {channel_id}")

            else:
                picture_dir = pathlib.Path(f"dailyphotos/{guild_id}")

                if not picture_dir.is_dir():
                    logger.warn(
                        f"Daily picture directory for guild {guild_id} does not exist; skipping"
                    )

                else:
                    # recursively glob for files (i.e. not directories)
                    pictures = list(picture_dir.rglob("*.*"))
                    random_picture = random.choice(responses)

                    with open(random_picture, "rb") as picture:
                        await ctx.send(
                            file=discord.File(picture, filename=random_picture.name),
                        )


async def setup(bot):
    await bot.add_cog(DailyPicture(bot))