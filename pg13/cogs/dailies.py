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

        self.clear_daily_claims.start()

    async def init_db(self):
        async with aiosqlite.connect("pg-13.db") as db:
            # TODO: Should these have unique constraints?
            # Channel bonuses
            await db.execute(
                "CREATE TABLE IF NOT EXISTS channel_bonuses"
                "(channel INT, guild INT, points INT, attachment BOOLEAN, UNIQUE(channel, guild))"
            )

            # Channel bonus claims
            await db.execute(
                "CREATE TABLE IF NOT EXISTS channel_claims"
                "(channel INT, guild INT, user INT, UNIQUE(channel, user))"
            )

            # `/daily claim` uses
            await db.execute(
                "CREATE TABLE IF NOT EXISTS daily_claims"
                "(guild INT, user INT, UNIQUE(guild, user))"
            )

            await db.commit()

    # DAILY BONUS COMMAND
    @app_commands.command(
        name="claim",
        description="Claim a daily reward of some points.",
    )
    async def daily_claim(self, interaction: discord.Interaction):
        async with aiosqlite.connect("pg-13.db") as db:
            # Check if user has already claimed today's bonus
            async with db.execute(
                f"SELECT * FROM daily_claims WHERE user = ? AND guild = ?",
                (interaction.user.id, interaction.guild_id),
            ) as user_request:
                user_claimed = await user_request.fetchone()

            if user_claimed is not None:
                self.logger.debug(
                    f"User {interaction.user.name} already claimed bonus today"
                )
                return await interaction.response.send_message(
                    "You've already claimed today's daily reward :)", ephemeral=True
                )

            # Give user points if they haven't claimed it
            if (scores_cog := self.bot.get_cog("Scores")) is not None:
                await scores_cog.increment_score(interaction.user, 3)

            # Update daily claim table for guild
            await db.execute(
                "INSERT INTO daily_claims VALUES(?, ?)",
                (
                    interaction.guild_id,
                    interaction.user.id,
                ),
            )
            await db.commit()

        await interaction.response.send_message("Succesfully claimed your daily bonus!")

    # CHANNEL DAILY BONUSES
    # FIXME: points argument seems to be broken
    @app_commands.command(
        name="attach",
        description="Attach a daily point bonus to messages in a channel.",
    )
    @app_commands.describe(
        channel="Channel to reward messages in",
        points="Number of bonus points",
        attachment="Whether to require an attachment to get points",
    )
    @app_commands.check(admin_check)
    async def daily_attach(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        points: int = 1,
        attachment: bool = False,
    ):
        async with aiosqlite.connect("pg-13.db") as db:
            # Ensure channel doesn't already have a daily bonus
            async with db.execute(
                f"SELECT * FROM channel_bonuses WHERE channel = ? AND guild = ?",
                (channel.id, interaction.guild_id),
            ) as exists_request:
                entry_exists = await exists_request.fetchone()

            if entry_exists is not None:
                return await interaction.response.send_message(
                    f"#{channel} already has a daily point reward!", ephemeral=True
                )

            else:
                await db.execute(
                    f"INSERT INTO channel_bonuses VALUES (?, ?, ?, ?)",
                    (channel.id, interaction.guild_id, points, attachment),
                )
                await db.commit()

        await interaction.response.send_message(
            f"Successfully added {points}-point daily bonus to {channel.mention}!",
            ephemeral=True,
        )

    @app_commands.command(
        name="remove", description="Remove a daily message bonus from a text channel."
    )
    @app_commands.describe(channel="Channel to remove bonus from")
    @app_commands.check(admin_check)
    async def daily_remove(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        async with aiosqlite.connect("pg-13.db") as db:
            async with db.execute(
                "SELECT channel FROM channel_bonuses "
                "WHERE channel = ? AND guild = ?",
                (channel.id, interaction.guild_id),
            ) as channel_request:
                channel_exists = await channel_request.fetchone()

            if channel_exists is None:
                return await interaction.response.send_message(
                    f"{channel.mention} doesn't have a daily bonus attached to it!",
                    ephemeral=True,
                )

            # Remove bonus & claim entries from corresponding tables
            await db.execute(
                f"DELETE FROM channel_bonuses WHERE channel = ? AND guild = ?",
                (channel.id, interaction.guild_id),
            )
            await db.execute(
                f"DELETE FROM channel_claims WHERE channel = ? AND guild = ?",
                (channel.id, interaction.guild_id),
            )
            await db.commit()

        await interaction.response.send_message(
            f"Succesfully detached daily bonus from channel {channel.mention}!",
            ephemeral=True,
        )
        self.logger.debug(
            f"Succesfully detached daily bonus from channel #{channel.name}"
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.author.bot:
            # Give user daily bonus if applicable
            async with aiosqlite.connect("pg-13.db") as db:
                db.row_factory = aiosqlite.Row

                # Check if message's channel has a daily bonus
                async with db.execute(
                    f"SELECT points, attachment FROM channel_bonuses "
                    "WHERE channel = ? AND guild = ?",
                    (message.channel.id, message.guild.id),
                ) as channel_request:
                    channel_bonus = await channel_request.fetchone()

                if channel_bonus is not None:
                    # Necessary message attachment wasn't provided
                    if channel_bonus["attachment"] and not (
                        message.attachments or message.embeds
                    ):
                        self.logger.debug(
                            f"User {message.author.name} didn't provide necessary attachment/embeds for bonus in #{channel.name}"
                        )

                    else:
                        async with db.execute(
                            f"SELECT * FROM channel_claims"
                            " WHERE user = ? AND channel = ? AND guild = ?",
                            (message.author.id, message.channel.id, message.guild.id),
                        ) as claim_request:
                            claimed_today = await claim_request.fetchone()

                        # Bonus not claimed and attachment(s) supplied if necessary
                        if claimed_today is None:
                            score_cog = self.bot.get_cog("Scores")
                            if score_cog is not None:
                                await score_cog.increment_score(
                                    message.author, channel_bonus["points"]
                                )

                            # Updated daily claimed table
                            await db.execute(
                                f"INSERT INTO channel_claims VALUES(?, ?, ?)",
                                (
                                    message.channel.id,
                                    message.guild.id,
                                    message.author.id,
                                ),
                            )
                            await db.commit()

                            self.logger.debug(
                                f"User {message.author.name} claimed a daily in #{message.channel.name}"
                            )

                        else:
                            self.logger.debug(
                                f"User {message.author.name} tried to claim daily in #{message.channel.name} again"
                            )

            # await self.bot.process_commands(message)

    @tasks.loop(hours=24)
    async def clear_daily_claims(self):
        async with aiosqlite.connect("pg-13.db") as db:
            await db.execute("DELETE FROM channel_claims")
            await db.execute("DELETE FROM daily_claims")
            await db.commit()

        self.logger.info("Cleared all daily reward tables")

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


async def setup(bot):
    cog = DailyBonuses(bot)
    await cog.init_db()
    await bot.add_cog(cog)
