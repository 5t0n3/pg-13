import asyncio
import datetime
import logging

import aiosqlite
import discord
from discord.ext import commands, tasks
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType as OptionType
from discord_slash.context import SlashContext
from discord_slash.utils.manage_commands import create_option

from .guild_ids import GUILD_IDS


class ChannelDailyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.dailies")

    @cog_ext.cog_subcommand(
        base="daily",
        name="create",
        description="Attach a daily reward to messages in a channel.",
        guild_ids=GUILD_IDS,
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
            create_option(
                name="attachment",
                description="Whether an attachment (e.g. image or link) is necessary to get the bonus (default false).",
                option_type=OptionType.BOOLEAN,
                required=False,
            ),
        ],
    )
    async def daily_create(self, ctx: SlashContext, channel, bonus=1, attachment=False):
        if not isinstance(channel, discord.TextChannel):
            return await ctx.send(
                "Please supply a text channel, not a voice channel or category!"
            )

        async with aiosqlite.connect("databases/dailies.db") as dailies:
            # Add entry in guild table (create if doesn't exist?) with increment
            await dailies.execute(
                f"CREATE TABLE IF NOT EXISTS guild_{ctx.guild_id}(channel INT PRIMARY KEY, increment INT, attachment BOOLEAN)",
            )
            exists_request = await dailies.execute(
                f"SELECT * FROM guild_{ctx.guild_id} WHERE channel = ?", (channel.id,)
            )
            entry_exists = await exists_request.fetchone()

            if entry_exists:
                return await ctx.send(f"#{channel} already has a daily point reward!")

            else:
                # Update guild table with increment
                await dailies.execute(
                    f"INSERT INTO guild_{ctx.guild_id} (channel, increment, attachment) VALUES (?, ?, ?)",
                    (channel.id, bonus, attachment),
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
        if message.author.bot:
            self.logger.info(f"Message {message.id} was a bot message")

        else:
            # Give user daily bonus if applicable
            async with aiosqlite.connect("databases/dailies.db") as dailies:
                # Check if guild has dailies
                guild_table = await dailies.execute(
                    f"SELECT * FROM sqlite_master WHERE type = 'table' AND name = 'guild_{message.guild.id}'"
                )
                has_dailies = await guild_table.fetchone()

                if has_dailies is not None:
                    # Check if message's channel has a daily bonus
                    channel_request = await dailies.execute(
                        f"SELECT increment, attachment FROM guild_{message.guild.id} WHERE channel = ?",
                        (message.channel.id,),
                    )
                    channel_bonus = await channel_request.fetchone()

                    if channel_bonus is not None:
                        claim_request = await dailies.execute(
                            f"SELECT claimed FROM channel_{message.channel.id} WHERE user = ?",
                            (message.author.id,),
                        )
                        claimed_today = await claim_request.fetchone()

                        # Check for message attachment if required
                        if channel_bonus[1] and not (
                            message.attachments or message.embeds
                        ):
                            self.logger.info(
                                f"User {message.author.name} didn't provide necessary attachment/embeds"
                            )

                        # Bonus not claimed and attachment(s) supplied if necessary
                        elif claimed_today is None:
                            async with aiosqlite.connect("scores.db") as scores:
                                # Fetch user score or default to (a row containing) 0
                                score_request = await scores.execute(
                                    f"SELECT score FROM guild_{message.guild.id} WHERE user = ?",
                                    (message.author.id,),
                                )
                                current_score = await score_request.fetchone()

                                # Update user's score
                                new_score = (current_score or (0,))[0] + channel_bonus[
                                    0
                                ]
                                await scores.execute(
                                    f"INSERT INTO guild_{message.guild.id}(user, score) VALUES(?, ?) ON CONFLICT(user) DO UPDATE SET score = ?",
                                    (
                                        message.author.id,
                                        new_score,
                                        new_score,
                                    ),
                                )

                                await scores.commit()
                                self.logger.info(
                                    f"Successfully updated score of user {message.author.name} to {new_score}"
                                )

                            # Updated daily claimed table
                            await dailies.execute(
                                f"INSERT INTO channel_{message.channel.id}(user, claimed) VALUES(?, ?)",
                                (message.author.id, True),
                            )
                            await dailies.commit()
                            self.logger.info(
                                f"Added user {message.author.name} to claimed table for {message.channel.name}"
                            )

                        else:
                            self.logger.info(
                                f"User {message.author.name} already claimed daily"
                            )

        await self.bot.process_commands(message)

    @commands.Cog.listener()
    async def on_ready(self):
        self.clear_daily_claims.start()

    @tasks.loop(hours=24)
    async def clear_daily_claims(self):
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            tables = await dailies.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )

            # Clear (not delete) all channel tables
            for (name,) in tables:
                if name.startswith("channel_"):
                    await dailies.execute(f"DELETE FROM {name}")

            await dailies.commit()

        self.logger.info("Successfully cleared all claim tables")

    @clear_daily_claims.before_loop
    async def ensure_clear_time(self):
        hour, minute = 23, 58
        await self.bot.wait_until_ready()

        now = datetime.datetime.now()
        future = datetime.datetime(now.year, now.month, now.day, hour, minute)
        if now.hour >= hour and now.minute >= minute:
            future += datetime.timedelta(days=1)

        self.logger.info("Delaying claim clear until proper time")
        await asyncio.sleep((future - now).seconds)
        self.logger.info("Finished delaying claim clear")


def setup(bot):
    bot.add_cog(ChannelDailyCog(bot))
