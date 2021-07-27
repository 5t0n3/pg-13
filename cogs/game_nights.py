import datetime
import logging

import aiosqlite
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType as OptionType
from discord_slash.context import SlashContext

from .guild_ids import GUILD_IDS


class GameNightCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.gamenights")

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_gamenight_tables()

    async def init_gamenight_tables(self):
        async with aiosqlite.connect("databases/gamenights.db") as gamenights:
            for guild in self.bot.guilds:
                await gamenights.execute(
                    f"CREATE TABLE IF NOT EXISTS guild_{guild.id}"
                    "(voice_channel INT PRIMARY KEY, host INT UNIQUE, start_channel INT)"
                )

            await gamenights.commit()
        self.logger.info("Successfully initialized all gamenight tables.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # TODO: Add logging to this event listener
        # Ignore bots (e.g. Rythm/Groovy)
        if member.bot:
            return

        # Ignore if a user mutes/deafens
        if before.channel == after.channel:
            return

        # Check if user's current/previous voice channel had ongoing game night(s)
        async with aiosqlite.connect("databases/gamenights.db") as gamenights:
            before_request = await gamenights.execute(
                f"SELECT * FROM guild_{member.guild.id} WHERE voice_channel = ?",
                (before.channel,),
            )
            before_had_gamenight = await before_request.fetchone()

            after_request = await gamenights.execute(
                f"SELECT * FROM guild_{member.guild.id} WHERE voice_channel = ?",
                (after.channel,),
            )
            after_had_gamenight = await after_request.fetchone()

        # User left a game night channel
        if before_had_gamenight is not None:
            async with aiosqlite.connect("databases/gamenights.db") as gamenights:
                # Note: user theoretically guaranteed to have row in game night table
                join_request = await gamenights.execute(
                    f"SELECT last_join FROM gamenight_{before.channel} WHERE user = ?",
                    (member.id,),
                )
                join_timestamp = await join_request.fetchone()
                minutes_spent = (
                    datetime.datetime.now()
                    - datetime.datetime.fromisoformat(join_timestamp)
                ).minutes

                # Update minutes spent in game night
                await gamenights.execute(
                    f"UPDATE gamenight_{before.channel} SET minutes = minutes + ? WHERE user = ?",
                    (minutes_spent, member.id),
                )

                await gamenights.commit()

        # User joined a game night channel
        if after_has_gamenight is not None:
            join_time = datetime.datetime.now().isoformat()

            # Update user's last_join timestamp
            async with aiosqlite.connect("databases/gamenights.db") as gamenights:
                await gamenights.execute(
                    f"INSERT INTO gamenight_{after.channel} VALUES(?, ?, 0)"
                    "ON CONFLICT(user) DO UPDATE SET last_join = ?",
                    (member.id, join_time, join_time),
                )

                await gamenights.commit()

    @cog_ext.cog_subcommand(
        base="gamenight",
        name="host",
        description="Start a game night in your current voice channel.",
        guild_ids=GUILD_IDS,
    )
    async def gamenight_host(self, ctx: SlashContext):
        if (voice_state := ctx.author.voice) is None:
            return await ctx.send(
                "You need to be in a voice channel to start a game night!"
            )

        # TODO: Ensure one user doesn't host multiple game nights at once

        gamenight_channel = voice_state.channel
        gamenight_starttime = datetime.datetime.now().isoformat()

        async with aiosqlite.connect("databases/gamenights.db") as gamenights:
            # Add host/voice channel to guild game night table
            await gamenights.execute(
                f"INSERT INTO guild_{ctx.guild_id} VALUES(?, ?, ?)",
                (gamenight_channel.id, ctx.author_id, ctx.channel_id),
            )

            # Initialize game-night-specific table
            await gamenights.execute(
                f"CREATE TABLE gamenight_{gamenight_channel.id}"
                "(user INT PRIMARY KEY, last_join DATETIME, minutes INT)"
            )

            # Add all users in call to newly-created table
            for user in gamenight_channel.members:
                await gamenights.execute(
                    f"INSERT INTO gamenight_{gamenight_channel.id} VALUES(?, ?, 0)",
                    (user.id, gamenight_starttime),
                )

            await gamenights.commit()

        await ctx.send(f"Started game night in voice channel {gamenight_channel.name}!")
        self.logger.info(
            f"Successfully started game night in channel {gamenight_channel.id} "
            f"with {len(gamenight_channel.members)} users"
        )


def setup(bot):
    bot.add_cog(GameNightCog(bot))
