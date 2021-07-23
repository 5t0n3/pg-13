import asyncio
import datetime

import aiosqlite
from discord.ext import commands, tasks
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType as OptionType
from discord_slash.context import SlashContext
from discord_slash.utils.manage_commands import create_option


class ChannelDailyCog(commands.Cog):
    GUILDS = []

    def __init__(self, bot):
        self.bot = bot
        self.GUILDS = self.bot.guild_ids

    @cog_ext.cog_subcommand(
        base="daily",
        name="create",
        description="Attach a daily reward to messages in a channel.",
        guild_ids=GUILDS,
        options=[
            create_option(
                name="channel",
                description="The channel to reward daily messages in",
                option_type=OptionType.CHANNEL,
                required=True,
            ),
            create_option(
                name="bonus",
                description="The amount of bonus points to give for a message (default 1).",
                option_type=OptionType.INTEGER,
                required=False,
            ),
        ],
    )
    async def daily_create(self, ctx: SlashContext, channel, bonus=1):
        # Note: "channel" is a `discord.channel.TextChannel`

        async with aiosqlite.connect("dailies.db") as dailies:
            # Add entry in guild table (create if doesn't exist?) with increment
            await dailies.execute(
                f"CREATE TABLE IF NOT EXISTS guild_{ctx.guild_id}(channel INT PRIMARY KEY, increment INT)",
            )
            exists_request = await dailies.execute(
                f"SELECT * FROM guild_{ctx.guild_id} WHERE channel = ?", (channel.id,)
            )
            entry_exists = await exists_request.fetchone()

            if entry_exists:
                return await ctx.send(f"#{channel} already has a daily point reward!")

            # Create channel table (named channel id)
            else:
                # Update guild table with increment
                await dailies.execute(
                    f"INSERT INTO guild_{ctx.guild_id} (channel, increment) VALUES (?, ?)",
                    (channel.id, bonus),
                )

                # Create channel cooldown table
                await dailies.execute(
                    f"CREATE TABLE channel_{channel.id} (user INT PRIMARY KEY, claimed BOOLEAN)",
                )

            # Commit all changes
            await dailies.commit()

        await ctx.send(f"Successfully added {bonus}-point daily bonus to #{channel}!")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Give user daily bonus if applicable
        async with aiosqlite.connect("dailies.db") as dailies:
            # Check if guild has dailies
            guild_table = await dailies.execute(
                f"SELECT * FROM sqlite_master WHERE type = 'table' AND name = 'guild_{message.guild.id}'"
            )
            has_dailies = await guild_table.fetchone()

            if has_dailies is not None:
                # Check if message's channel has a daily bonus
                channel_request = await dailies.execute(
                    f"SELECT increment FROM guild_{message.guild.id} WHERE channel = ?",
                    (message.channel.id,),
                )
                channel_bonus = await channel_request.fetchone()

                if channel_bonus is not None:
                    claim_request = await dailies.execute(
                        f"SELECT claimed FROM channel_{message.channel.id} WHERE user = ?",
                        (message.author.id,),
                    )
                    claimed_today = await claim_request.fetchone()

                    # Handle None case (user hasn't claimed in the past)
                    # or False case (not claimed today)
                    if claimed_today is None:
                        async with aiosqlite.connect("scores.db") as scores:
                            # Fetch user score or default to (a row containing) 0
                            score_request = await scores.execute(
                                f"SELECT score FROM guild_{message.guild.id} WHERE user = ?",
                                (message.author.id,),
                            )
                            current_score = await score_request.fetchone()

                            # Update user's score
                            new_score = (current_score or (0,))[0] + channel_bonus[0]
                            await scores.execute(
                                f"INSERT INTO guild_{message.guild.id}(user, score) VALUES(?, ?) ON CONFLICT(user) DO UPDATE SET score = ?",
                                (
                                    message.author.id,
                                    new_score,
                                    new_score,
                                ),
                            )

                            await scores.commit()
                            self.bot.logger.debug(
                                f"Successfully updated score of user {message.author.id} to {new_score}"
                            )

                        # Updated daily claimed table
                        await dailies.execute(
                            f"INSERT INTO channel_{message.channel.id}(user, claimed) VALUES(?, ?)",
                            (message.author.id, True),
                        )
                        await dailies.commit()
                        self.bot.logger.debug(
                            f"Added user to claimed table: {message.author.id}"
                        )

                    else:
                        self.bot.logger.debug(
                            f"User {message.author.id} already claimed daily"
                        )

        await self.bot.process_commands(message)

    @commands.Cog.listener()
    async def on_ready(self):
        self.clear_daily_claims.start()

    @tasks.loop(hours=24)
    async def clear_daily_claims(self):
        async with aiosqlite.connect("dailies.db") as dailies:
            tables = await dailies.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )

            # Clear (not delete) all channel tables
            for (name,) in tables:
                if name.startswith("channel_"):
                    await dailies.execute(f"DELETE FROM {name}")

            await dailies.commit()

        self.bot.logger.debug("Successfully cleared all claim tables")

    @clear_daily_claims.before_loop
    async def ensure_clear_time(self):
        hour, minute = 23, 58
        await self.bot.wait_until_ready()

        now = datetime.datetime.now()
        future = datetime.datetime(now.year, now.month, now.day, hour, minute)
        if now.hour >= hour and now.minute >= minute:
            future += datetime.timedelta(days=1)

        self.bot.logger.debug("Delaying claim clear until proper time")
        await asyncio.sleep((future - now).seconds)
        self.bot.logger.debug("Finished delaying claim clear")
