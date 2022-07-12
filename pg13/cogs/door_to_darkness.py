import asyncio
import datetime
import logging
import re

import aiosqlite
from discord.ext import commands, tasks


class DoorToDarkness(commands.Cog):
    """A really niche cog for asking a specific person if they've heard
    about the door to darkness.

    I doubt anyone will run this bot but if you decide you want to, make
    sure to change the member id in the constructor.
    """

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.doortodarkness")
        self.door_regex = re.compile(r"door to darkness", re.I)  # case-insensitive
        self.door_members = {}

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_guild_door_tables()
        await self.clear_door_claims.start()

    async def init_guild_door_tables(self):
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            # Create a table in the dailies database for each guild/server
            for guild in self.bot.guilds:
                await dailies.execute(
                    f"CREATE TABLE IF NOT EXISTS door_{guild.id}"
                    "(user INT PRIMARY KEY)",
                )

            await dailies.commit()

        self.logger.info("Successfully initialized door to darkness tables!")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bot messages
        if message.author.bot:
            return

        # Fetch guild's specific member that has to be mentioned
        mention_member = self.door_members.get(message.guild.id)
        if mention_member is None:
            mention_id = self.bot.guild_configs[str(message.guild.id)]["door_member"]
            mention_member = message.guild.get_member(int(mention_id))

            # Store the member object in this cog for easy access
            self.door_members[message.guild.id] = mention_member

        # Users have to mention a specific user
        if mention_member not in message.mentions:
            self.logger.debug(f"User {message.author.id} didn't mention correct user")
            return

        # Make sure that "door to darkness" is also included in the message
        if re.search(self.door_regex, message.content) is None:
            self.logger.debug(
                f"User {message.author.id} didn't mention the door to darkness"
            )
            return

        # Make sure that a user hasn't already gotten these points today
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            user_request = await dailies.execute(
                f"SELECT * FROM door_{message.guild.id} WHERE user = ?",
                (message.author.id,),
            )
            user_id = await user_request.fetchone()

            if user_id is not None:
                self.logger.debug(
                    f"User {message.author.id} already claimed door to darkness point"
                )
                return

        # Assuming all of the above conditions are met, give the message author one point
        if (scores := self.bot.get_cog("Scores")) is not None:
            await scores.update_scores(message.author, 1)
            self.logger.debug(
                f"User {message.author.id} claimed door to darkness point"
            )

        # Update the claim database so each user only gets one point from this a day
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            await dailies.execute(
                f"INSERT INTO door_{message.guild.id} VALUES(?)", (message.author.id,)
            )
            await dailies.commit()

    # stolen from dailies.py
    @tasks.loop(hours=24)
    async def clear_door_claims(self):
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            # Clear all door to darkness claim tables in every guild the bot is in
            for guild in self.bot.guilds:
                await dailies.execute(f"DELETE FROM door_{guild.id}")

            await dailies.commit()

        self.logger.info("Successfully cleared all door to darkness claim tables")

    @clear_door_claims.before_loop
    async def ensure_clear_time(self):
        hour, minute = 23, 58
        await self.bot.wait_until_ready()

        now = datetime.datetime.now()
        future = datetime.datetime(now.year, now.month, now.day, hour, minute)
        if now.hour >= hour and now.minute >= minute:
            future += datetime.timedelta(days=1)

        self.logger.debug("Delaying door to darkness claim clear until proper time")
        await asyncio.sleep((future - now).seconds)
        self.logger.debug("Finished delaying door to darkness claim clear")


async def setup(bot):
    await bot.add_cog(DoorToDarkness(bot))
