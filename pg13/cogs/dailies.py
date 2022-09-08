import asyncio
import datetime
import logging
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .checks import admin_check

logger = logging.getLogger(__name__)


class DailyBonuses(
    commands.GroupCog,
    group_name="daily",
    group_description="Channel & command daily bonus management",
):
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = bot.db_pool

    async def cog_load(self):
        async with self.db_pool.acquire() as con:
            # Channel bonuses
            await con.execute(
                "CREATE TABLE IF NOT EXISTS channel_bonuses"
                "(channel BIGINT, guild BIGINT, points INT, attachment BOOLEAN, UNIQUE(channel, guild))"
            )

            # Channel bonus claims
            await con.execute(
                "CREATE TABLE IF NOT EXISTS channel_claims"
                "(channel BIGINT, guild BIGINT, userid BIGINT, UNIQUE(channel, userid))"
            )

            # `/daily claim` uses
            await con.execute(
                "CREATE TABLE IF NOT EXISTS daily_claims"
                "(guild BIGINT, userid BIGINT, UNIQUE(guild, userid))"
            )

        self.clear_daily_claims.start()

    # DAILY BONUS COMMAND
    @app_commands.command(
        name="claim",
        description="Claim a daily reward of some points.",
    )
    async def daily_claim(self, interaction: discord.Interaction):
        async with self.db_pool.acquire() as con:
            claim_result = await con.execute(
                "INSERT INTO daily_claims VALUES($1, $2) ON CONFLICT(guild, userid) DO NOTHING",
                interaction.guild_id,
                interaction.user.id,
            )

        rows_updated = int(claim_result.split(" ")[-1])
        if rows_updated == 0:
            logger.debug(f"User {interaction.user.name} already claimed bonus today")
            await interaction.response.send_message(
                "You've already claimed today's daily reward :)", ephemeral=True
            )

        else:
            # Give user points if they haven't claimed it
            if (scores_cog := self.bot.get_cog("Scores")) is not None:
                await scores_cog.increment_score(
                    interaction.user, 3, "Claimed daily reward"
                )

            await interaction.response.send_message(
                "Succesfully claimed your daily bonus!"
            )

    # CHANNEL DAILY BONUSES
    @app_commands.command(
        name="attach",
        description="Attach a daily point bonus to messages in a channel.",
    )
    @app_commands.describe(
        channel="Channel to reward messages in",
        points="Number of bonus points",
        attachment="Whether to require an attachment (image/link) to get points",
    )
    @app_commands.check(admin_check)
    async def daily_attach(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        points: int,
        attachment: bool = False,
    ):
        async with self.db_pool.acquire() as con:
            bonus_result = await con.execute(
                "INSERT INTO channel_bonuses VALUES($1, $2, $3, $4) ON CONFLICT(channel, guild) DO NOTHING",
                channel.id,
                channel.guild.id,
                points,
                attachment,
            )

        rows_updated = int(bonus_result.split(" ")[-1])
        if rows_updated == 0:
            await interaction.response.send_message(
                f"{channel.mention} already has a daily point reward!", ephemeral=True
            )
        else:
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
        async with self.db_pool.acquire() as con:
            delete_result = await con.execute(
                f"DELETE FROM channel_bonuses WHERE channel = $1 AND guild = $2",
                channel.id,
                interaction.guild_id,
            )
            await con.execute(
                f"DELETE FROM channel_claims WHERE channel = $1 AND guild = $2",
                channel.id,
                interaction.guild_id,
            )

        deleted_bonuses = int(delete_result.split(" ")[-1])
        if deleted_bonuses == 0:
            await interaction.response.send_message(
                f"{channel.mention} doesn't have a daily bonus attached to it!",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"Succesfully detached daily bonus from channel {channel.mention}!",
                ephemeral=True,
            )
            logger.debug(
                f"Succesfully detached daily bonus from channel #{channel.name}"
            )

    @app_commands.command(
        name="list", description="List all channel daily bonuses in this server."
    )
    async def daily_list(self, interaction: discord.Interaction):
        async with self.db_pool.acquire() as con:
            guild_dailies = await con.fetch(
                "SELECT channel, points, attachment FROM channel_bonuses WHERE guild = $1",
                interaction.guild_id,
            )

        if not guild_dailies:
            await interaction.response.send_message(
                "There aren't any daily channel bonuses in this server yet :)",
                ephemeral=True,
            )

        else:
            formatted_bonuses = []
            for bonus in guild_dailies:
                channel_mention = getattr(
                    interaction.guild.get_channel(bonus["channel"]),
                    "mention",
                    "<deleted channel>",
                )
                attachment_comment = (
                    " (picture/link required)" if bonus["attachment"] else ""
                )
                formatted_bonuses.append(
                    f"{channel_mention}: {bonus['points']} points{attachment_comment}"
                )

            await interaction.response.send_message(
                embed=discord.Embed(
                    title=f"{interaction.guild.name} Channel Bonuses",
                    description="\n".join(formatted_bonuses),
                )
            )

    @app_commands.command(
        name="clean-deleted",
        description="Cleans up daily bonuses from deleted channels",
    )
    @app_commands.check(admin_check)
    async def daily_clean_deleted(self, interaction: discord.Interaction):
        async with self.db_pool.acquire() as con:
            daily_channels = await con.fetch(
                "SELECT channel FROM channel_bonuses WHERE guild = $1",
                interaction.guild_id,
            )

            deleted_channels = [
                bonus["channel"]
                for bonus in daily_channels
                if interaction.guild.get_channel(bonus["channel"]) is None
            ]

            delete_result = await con.execute(
                "DELETE FROM channel_bonuses WHERE channel = ANY($1::BIGINT[])",
                deleted_channels,
            )

        if int(delete_result.split(" ")[-1]) > 0:
            await interaction.response.send_message(
                "Cleaned up daily bonuses from deleted channels!", ephemeral=True
            )
            logger.debug(
                f"Cleaned up daily bonuses from deleted channels in guild {interaction.guild.name}"
            )
        else:
            await interaction.response.send_message(
                "There were no bonuses from deleted channels to clean up :)",
                ephemeral=True,
            )

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        provided_attachment = bool(message.attachments or message.embeds)

        async with self.db_pool.acquire() as con:
            bonus_points = await con.fetchval(
                "WITH bonus_info AS (SELECT points, attachment FROM channel_bonuses WHERE channel = $1 AND guild = $2), "
                "claim_row AS (SELECT $1::BIGINT, $2::BIGINT, $3::BIGINT FROM bonus_info WHERE attachment IN ($4, FALSE))"
                "INSERT INTO channel_claims (SELECT * FROM claim_row) "
                "ON CONFLICT(channel, userid) DO NOTHING "
                "RETURNING (SELECT points FROM bonus_info)",
                message.channel.id,
                message.guild.id,
                message.author.id,
                provided_attachment,
            )

        if (
            bonus_points is not None
            and (scores_cog := self.bot.get_cog("Scores")) is not None
        ):
            await scores_cog.increment_score(
                message.author,
                bonus_points,
                reason=f"Bonus claim in #{message.channel.name}",
            )

    @tasks.loop(time=datetime.time(23, 58, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def clear_daily_claims(self):
        async with self.db_pool.acquire() as con:
            await con.execute("TRUNCATE TABLE channel_claims")
            await con.execute("TRUNCATE TABLE daily_claims")

        logger.debug("Cleared all daily reward tables")


async def setup(bot):
    await bot.add_cog(DailyBonuses(bot))
