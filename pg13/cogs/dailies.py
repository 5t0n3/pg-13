import asyncio
import datetime
import logging

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks

from .cog_config import configured_guilds, admin_check


@app_commands.guilds(*configured_guilds)
class DailyBonuses(commands.GroupCog, group_name="daily"):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("pg13.dailies")

        # Schedule clearing of daily tables
        self.clear_daily_claims.start()

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
    @app_commands.command(
        name="claim",
        description="Claim a daily reward of some points.",
    )
    async def daily_claim(self, interaction: discord.Interaction):
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            # Check if user has already claimed today's bonus
            user_request = await dailies.execute(
                f"SELECT * FROM bonus_{interaction.guild_id} WHERE user = ?",
                (interaction.user.id,),
            )
            user_claimed = await user_request.fetchone()

            if user_claimed is not None:
                self.logger.debug(
                    f"User {interaction.user.name} already claimed bonus today"
                )
                return await interaction.response.send_message(
                    "You've already claimed today's daily reward!", ephemeral=True
                )

            # Give user points if they haven't claimed it
            # TODO: confirm point amount
            if (scores_cog := self.bot.get_cog("Scores")) is not None:
                await scores_cog.increment_score(interaction.user, 3)

            # Update daily claim table for guild
            await dailies.execute(
                f"INSERT INTO bonus_{interaction.guild_id} VALUES(?)",
                (interaction.user.id,),
            )
            await dailies.commit()

        await interaction.response.send_message("Succesfully claimed your daily bonus!")

    # CHANNEL DAILY BONUSES
    @app_commands.command(
        name="attach",
        description="Attach a daily point bonus to messages in a channel.",
    )
    @app_commands.describe(
        channel="Channel to reward messages in",
        bonus="Number of bonus points",
        attachment="Whether to require an attachment to get points",
    )
    @app_commands.check(admin_check)
    async def attach_bonus(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        bonus: int = 1,
        attachment: bool = False,
    ):
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "Please supply a text channel, not a voice channel or category!",
                ephemeral=True,
            )

        async with aiosqlite.connect("databases/dailies.db") as dailies:
            # Ensure channel doesn't already have a daily bonus
            exists_request = await dailies.execute(
                f"SELECT * FROM guild_{interaction.guild_id} WHERE channel = ?",
                (channel.id,),
            )
            entry_exists = await exists_request.fetchone()

            if entry_exists is not None:
                return await interaction.response.send_message(
                    f"#{channel} already has a daily point reward!", ephemeral=True
                )

            else:
                # Update guild table with bonus
                await dailies.execute(
                    f"INSERT INTO guild_{interaction.guild_id} VALUES (?, ?, ?)",
                    (channel.id, bonus, attachment),
                )

                # Create channel cooldown table
                await dailies.execute(
                    f"CREATE TABLE channel_{channel.id} (user INT PRIMARY KEY, claimed BOOLEAN)",
                )

            # Commit all changes
            await dailies.commit()

        await interaction.response.send_message(
            f"Successfully added {bonus}-point daily bonus to #{channel}!",
            ephemeral=True,
        )

    @app_commands.command(
        name="remove", description="Remove a daily message bonus from a text channel."
    )
    @app_commands.describe(channel="Channel to remove bonus from")
    @app_commands.check(admin_check)
    async def bonus_remove(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        # Bonuses can only be attached to text channels
        if not isinstance(channel, discord.TextChannel):
            self.logger.debug(f"Channel {channel.name} was not a text channel")
            return await interaction.response.send_message(
                "Please supply a text channel, not a voice channel or category!",
                ephemeral=True,
            )

        async with aiosqlite.connect("databases/dailies.db") as dailies:
            channel_request = await dailies.execute(
                f"SELECT channel FROM guild_{interaction.guild_id} WHERE channel = ?",
                (channel.id,),
            )
            channel_exists = await channel_request.fetchone()

            # If the daily doesn't exist, the above query returns None
            if channel_exists is None:
                return await interaction.response.send_message(
                    f"{channel.mention} doesn't have a daily bonus attached to it!",
                    ephemeral=True,
                )

            # Delete channel's claim table & entry in guild table
            await dailies.execute(f"DROP TABLE channel_{channel.id}")
            await dailies.execute(
                f"DELETE FROM guild_{interaction.guild_id} WHERE channel = ?",
                (channel.id,),
            )

            await dailies.commit()

        await interaction.response.send_message(
            f"Succesfully detached daily bonus from channel {channel.name}!",
            ephemeral=True,
        )
        self.logger.debug(
            f"Succesfully detached daily bonus from channel {channel.name}"
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            self.logger.debug(f"Message {message.id} was a bot message")

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
                        self.logger.debug(
                            f"User {message.author.name} didn't provide necessary attachment/embeds"
                        )

                    # Bonus not claimed and attachment(s) supplied if necessary
                    elif claimed_today is None:
                        # Update cumulative score
                        score_cog = self.bot.get_cog("Scores")

                        if score_cog is not None:
                            await score_cog.increment_score(
                                message.author, channel_bonus[0]
                            )

                        # Updated daily claimed table
                        await dailies.execute(
                            f"INSERT INTO channel_{message.channel.id} VALUES(?, ?)",
                            (message.author.id, True),
                        )
                        await dailies.commit()

                        self.logger.debug(
                            f"Added user {message.author.name} to claimed table for {message.channel.name}"
                        )

                    else:
                        self.logger.debug(
                            f"User {message.author.name} already claimed daily"
                        )

        await self.bot.process_commands(message)

    @commands.Cog.listener()
    async def on_ready(self):
        # Initialize daily tables
        await self.init_guild_daily_tables()

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
                await dailies.execute(f"DELETE FROM bonus_{guild.id}")

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

        self.logger.debug("Delaying claim clear until proper time")
        await asyncio.sleep((future - now).seconds)
        self.logger.debug("Finished delaying claim clear")


async def setup(bot):
    await bot.add_cog(DailyBonuses(bot))
