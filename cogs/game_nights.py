import datetime
import logging

import aiosqlite
import discord
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType as OptionType
from discord_slash.context import SlashContext

from .slash_config import loaded_guilds


class GameNights(commands.Cog):
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
            # These if statements are necessary to handle a case where one channel is None
            if before.channel is not None:
                before_request = await gamenights.execute(
                    f"SELECT * FROM guild_{member.guild.id} WHERE voice_channel = ?",
                    (before.channel.id,),
                )
                before_had_gamenight = await before_request.fetchone()
            else:
                # A nonexistent channel won't have a game night going on
                before_had_gamenight = None

            if after.channel is not None:
                after_request = await gamenights.execute(
                    f"SELECT * FROM guild_{member.guild.id} WHERE voice_channel = ?",
                    (after.channel.id,),
                )
                after_has_gamenight = await after_request.fetchone()
            else:
                after_has_gamenight = None

        # User left a game night channel
        if before_had_gamenight is not None:
            async with aiosqlite.connect("databases/gamenights.db") as gamenights:
                # Note: user theoretically guaranteed to have row in game night table
                join_request = await gamenights.execute(
                    f"SELECT last_join FROM gamenight_{before.channel.id} WHERE user = ?",
                    (member.id,),
                )
                join_timestamp = await join_request.fetchone()
                seconds_spent = (
                    datetime.datetime.now()
                    - datetime.datetime.fromisoformat(join_timestamp[0])
                ).seconds

                # Update seconds spent in game night
                await gamenights.execute(
                    f"UPDATE gamenight_{before.channel.id} SET seconds = seconds + ? WHERE user = ?",
                    (seconds_spent, member.id),
                )

                await gamenights.commit()

            self.logger.info(f"User {member.name} left channel {before.channel.name}")

            # Automatically end game night if everyone leaves a channel
            if not before.channel.members:
                await self.end_gamenight(before.channel)

        # User joined a game night channel
        if after_has_gamenight is not None:
            join_time = datetime.datetime.now().isoformat()

            # Update user's last_join timestamp
            async with aiosqlite.connect("databases/gamenights.db") as gamenights:
                await gamenights.execute(
                    f"INSERT INTO gamenight_{after.channel.id} VALUES(?, ?, 0)"
                    "ON CONFLICT(user) DO UPDATE SET last_join = ?",
                    (member.id, join_time, join_time),
                )

                await gamenights.commit()

            self.logger.info(f"User {member.name} joined channel {after.channel.name}")

    async def end_gamenight(self, channel):
        async with aiosqlite.connect("databases/gamenights.db") as gamenights:
            # Fetch participation times
            member_times = await gamenights.execute_fetchall(
                f"SELECT user, seconds FROM gamenight_{channel.id} ORDER BY seconds DESC"
            )

            # This has to be iterated over multiple times
            member_times = list(member_times)

            # Get channel command was executed from to send summary in
            summary_request = await gamenights.execute(
                f"SELECT start_channel, host FROM guild_{channel.guild.id} "
                "WHERE voice_channel = ?",
                (channel.id,),
            )
            # Theoretically guaranteed to be non-None
            summary_info = await summary_request.fetchone()
            summary_channel = self.bot.get_channel(summary_info[0])

            # Delete game night table & entry in guild table
            await gamenights.execute(f"DROP TABLE gamenight_{channel.id}")
            await gamenights.execute(
                f"DELETE FROM guild_{channel.guild.id} WHERE voice_channel = ?",
                (channel.id,),
            )

            await gamenights.commit()

        # Fetch current guild thresholds, or default to None if they aren't defined
        guild_thresholds = self.bot.guild_configs[str(channel.guild.id)].get(
            "thresholds", None
        )

        # Convert keys to ints (TOML makes them strings by default)
        guild_thresholds = {
            int(minutes): bonus for minutes, bonus in guild_thresholds.items()
        }

        # Dole out bonuses to everyone that attended
        if (scores := self.bot.get_cog("Scores")) is not None:
            # Use thresholds to give out bonuses
            if guild_thresholds is not None:
                for user_id, seconds in member_times:
                    # Fetch point bonus based on time spent in game night
                    highest = max(
                        filter(
                            lambda threshold: threshold <= seconds // 60,
                            guild_thresholds,
                        ),
                        default=0,
                    )
                    user_bonus = guild_thresholds.get(highest, 0)

                    # Fetch member associated with user id
                    member = channel.guild.get_member(user_id)

                    # Update user's score
                    await scores.update_scores(member, user_bonus)

            # Give the host 17 points for hosting
            host = channel.guild.get_member(summary_info[1])
            await scores.update_scores(host, 17)

        self.logger.info(f"Cleaned up game night in channel {channel.name}")

        # Turn member times into an embed
        await self.send_summary(summary_channel, channel, member_times)

    async def send_summary(self, summary_channel, voice_channel, member_times):
        """Sends a summary of a gamenight, including how long members played for"""
        embed_desc = ""

        # Construct "leaderboard" of users (ties treated as separate places)
        for place, (user_id, seconds) in enumerate(member_times, start=1):
            user = self.bot.get_user(user_id)
            minutes = seconds // 60
            duration_hmm = f"{minutes // 60}:{minutes % 60:02d}"
            embed_desc += f"{place} - {user.mention} ({duration_hmm})\n"

        summary = discord.Embed(
            title=f"Game night summary - {voice_channel.name}", description=embed_desc
        )
        await summary_channel.send(embed=summary)
        self.logger.info(
            f"Sent summary embed in {summary_channel.name} for game night in {voice_channel.name}"
        )

    @cog_ext.cog_subcommand(
        base="gamenight",
        name="host",
        description="Start a game night in your current voice channel.",
        **loaded_guilds,
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
                "(user INT PRIMARY KEY, last_join DATETIME, seconds INT)"
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
            f"Successfully started game night in channel {gamenight_channel.name} "
            f"with {len(gamenight_channel.members)} initial users"
        )


def setup(bot):
    bot.add_cog(GameNights(bot))
