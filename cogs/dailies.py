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


class DailyBonuses(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.dailies")

    async def init_guild_daily_tables(self):
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            for guild in self.bot.guilds:
                # Channel bonus(es)
                await dailies.execute(
                    f"CREATE TABLE IF NOT EXISTS guild_{guild.id}"
                    "(channel INT PRIMARY KEY, bonus INT, attachment BOOLEAN)",
                )

                # For "/daily claim" command
                await dailies.execute(
                    f"CREATE TABLE IF NOT EXISTS bonus_{guild.id}"
                    "(user INT PRIMARY KEY)"
                )

            await dailies.commit()

        self.logger.info("Successfully initialized all guild daily tables.")

    # DAILY BONUS COMMAND
    @cog_ext.cog_subcommand(
        base="daily",
        name="claim",
        description="Claim a daily reward of some points.",
        guild_ids=GUILD_IDS,
    )
    async def daily_claim(self, ctx: SlashContext):
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            # Check if user has already claimed today's bonus
            user_request = await dailies.execute(
                f"SELECT * FROM bonus_{ctx.guild_id} WHERE user = ?", (ctx.author_id,)
            )
            user_claimed = await user_request.fetchone()

            if user_claimed is not None:
                self.logger.info(f"User {ctx.author.name} already claimed bonus today")
                return await ctx.send("You've already claimed today's daily reward!")

            # Give user points if they haven't claimed it
            # TODO: confirm point amount
            if (scores_cog := self.bot.get_cog("Scores")) is not None:
                await scores_cog.update_scores(ctx.author, 3, adjust=True)

            # Update daily claim table for guild
            await dailies.execute(
                f"INSERT INTO bonus_{ctx.guild_id} VALUES(?)", (ctx.author_id,)
            )
            await dailies.commit()

        await ctx.send("Succesfully claimed your daily bonus!")

    # CHANNEL DAILY BONUSES
    @cog_ext.cog_subcommand(
        base="bonus",
        name="attach",
        description="Attach a daily point bonus to messages in a channel.",
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
    async def bonus_attach(self, ctx: SlashContext, channel, bonus=1, attachment=False):
        if not isinstance(channel, discord.TextChannel):
            return await ctx.send(
                "Please supply a text channel, not a voice channel or category!"
            )

        async with aiosqlite.connect("databases/dailies.db") as dailies:
            # Ensure channel doesn't already have a daily bonus
            exists_request = await dailies.execute(
                f"SELECT * FROM guild_{ctx.guild_id} WHERE channel = ?", (channel.id,)
            )
            entry_exists = await exists_request.fetchone()

            if entry_exists is not None:
                return await ctx.send(f"#{channel} already has a daily point reward!")

            else:
                # Update guild table with bonus
                await dailies.execute(
                    f"INSERT INTO guild_{ctx.guild_id} VALUES (?, ?, ?)",
                    (channel.id, bonus, attachment),
                )

                # Create channel cooldown table
                await dailies.execute(
                    f"CREATE TABLE channel_{channel.id} (user INT PRIMARY KEY, claimed BOOLEAN)",
                )

            # Commit all changes
            await dailies.commit()

        await ctx.send(f"Successfully added {bonus}-point daily bonus to #{channel}!")

    @cog_ext.cog_subcommand(
        base="bonus",
        name="detach",
        description="Remove a daily message bonus from a text channel.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="channel",
                description="The channel to remove a bonus from.",
                option_type=OptionType.CHANNEL,
                required=True,
            )
        ],
    )
    async def bonus_detach(self, ctx: SlashContext, channel):
        # Bonuses can only be attached to text channels
        if not isinstance(channel, discord.TextChannel):
            self.logger.info(f"Channel {channel.name} was not a text channel")
            return await ctx.send(
                "Please supply a text channel, not a voice channel or category!"
            )

        async with aiosqlite.connect("databases/dailies.db") as dailies:
            channel_request = await dailies.execute(
                f"SELECT channel FROM guild_{ctx.guild_id} WHERE channel = ?",
                (channel.id,),
            )
            channel_exists = await channel_request.fetchone()

            # If the daily doesn't exist, the above query returns None
            if channel_exists is None:
                return await ctx.send(
                    f"{channel.mention} doesn't have a daily bonus attached to it!"
                )

            # Delete channel's claim table & entry in guild table
            await dailies.execute(f"DROP TABLE channel_{channel.id}")
            await dailies.execute(
                f"DELETE FROM guild_{ctx.guild_id} WHERE channel = ?", (channel.id,)
            )

            await dailies.commit()

        await ctx.send(f"Succesfully detached daily bonus from channel {channel.name}!")
        self.logger.info(
            f"Succesfully detached daily bonus from channel {channel.name}"
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            self.logger.info(f"Message {message.id} was a bot message")

        else:
            # Give user daily bonus if applicable
            async with aiosqlite.connect("databases/dailies.db") as dailies:
                # Check if message's channel has a daily bonus
                channel_request = await dailies.execute(
                    f"SELECT bonus, attachment FROM guild_{message.guild.id} WHERE channel = ?",
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
                    if channel_bonus[1] and not (message.attachments or message.embeds):
                        self.logger.info(
                            f"User {message.author.name} didn't provide necessary attachment/embeds"
                        )

                    # Bonus not claimed and attachment(s) supplied if necessary
                    elif claimed_today is None:
                        # Update both cumulative & current scores
                        score_cog = self.bot.get_cog("Scores")

                        if score_cog is not None:
                            await score_cog.update_scores(
                                message.author, channel_bonus[0], adjust=True
                            )

                        # Updated daily claimed table
                        await dailies.execute(
                            f"INSERT INTO channel_{message.channel.id} VALUES(?, ?)",
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
        # Initialize daily tables
        await self.init_guild_daily_tables()

        # Schedule clearing of daily tables
        self.clear_daily_claims.start()

    @tasks.loop(hours=24)
    async def clear_daily_claims(self):
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            # Clear all daily claim tables in every guild the bot is in
            for guild in self.bot.guilds:
                # Channel bonus tables
                async with dailies.execute(
                    f"SELECT channel FROM guild_{guild.id}"
                ) as channels:
                    async for (channel_id,) in channels:
                        await dailies.execute(f"DELETE FROM channel_{channel_id}")

                # Clear "/daily claim" table
                await dailies.execute("DELETE FROM bonus_{guild.id}")

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
    bot.add_cog(DailyBonuses(bot))
