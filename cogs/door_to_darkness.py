import logging
import re

import aiosqlite
from discord.ext import commands


class DoorToDarkness(commands.Cog):
    """A really niche cog for asking a specific person if they've heard
    about the door to darkness.

    I doubt anyone will run this bot but if you decide you want to, make
    sure to change the member id in the constructor.
    """

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.doortodarkness")
        self.mention_member = self.bot.get_member(120008629943402496)
        self.door_regex = re.compile(r"door to darkness", re.I)  # case-insensitive

    @commands.Cog.listener()
    async def on_ready(self):
        self.init_guild_door_tables()

    async def init_guild_door_tables():
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            # Create a table in the dailies database for each guild/server
            for guild in self.bot.guilds:
                await dailies.execute(
                    f"CREATE TABLE IF NOT EXISTS door_{guild.id}"
                    "(user INT PRIMARY KEY)",
                )

            await dailies.commit()

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bot messages
        if message.author.bot:
            return

        # Users have to mention a specific user
        if self.mention_member not in message.mentions:
            return

        # Make sure that "door to darkness" is also included in the message
        if re.match(self.door_regex, message.content) is None:
            return

        # Make sure that a user hasn't already gotten these points today
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            user_request = await dalilies.execute(
                f"SELECT * FROM door_{message.guild.id} WHERE user = ?"(
                    message.author.id,
                )
            )
            user_id = await user_request.fetchone()

            if user_id is not None:
                return

        # Assuming all of the above conditions are met, give the message author one point
        if (scores := self.bot.get_cog("Scores")) is not None:
            await scores.update_scores(message.author, 1)
            self.logger.info(f"{member.name} claimed door to darkness point")

        # Update the claim database so each user only gets one point from this a day
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            await dailies.execute(
                f"INSERT INTO door_{message.guild.id} VALUES(?)"(
                    message.author.id,
                )
            )
            await dailies.commit()


def setup(bot):
    bot.add_cog(DoorToDarkness(bot))
