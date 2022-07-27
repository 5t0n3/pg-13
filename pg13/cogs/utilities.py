import logging

import aiosqlite
import discord
from discord.ext import commands

from .cog_config import configured_guilds

logger = logging.getLogger(__name__)


class Utilities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = bot.db_pool

    @commands.command(name="sync", description="Sync all slash commands")
    async def sync(self, ctx: commands.Context):
        # TODO: Sync global commands instead
        for guild in configured_guilds:
            await ctx.bot.tree.sync(guild=discord.Object(guild))
        await ctx.message.add_reaction("🔄")
        logger.info("Successfully synced all application commands!")

    @commands.command(description="Migrate the bot databases from SQLite to PostgreSQL")
    async def migratedb(self, ctx: commands.Context):
        score_rows = []
        # User scores
        async with aiosqlite.connect("databases/scores.db") as scores:
            scores.row_factory = aiosqlite.Row
            score_tables = await scores.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
            for table in score_tables:
                guild_id = int(table["name"][6:])
                guild_scores = await scores.execute_fetchall(
                    f"SELECT * FROM {table['name']}"
                )
                migrated_scores = map(
                    lambda row: (guild_id, row["user"], row["cumulative"]), guild_scores
                )
                score_rows.extend(migrated_scores)

        # DailyBonuses cog data
        channel_bonuses = []
        channel_claims = []
        daily_claims = []
        async with aiosqlite.connect("databases/dailies.db") as dailies:
            dailies.row_factory = aiosqlite.Row

            daily_tables = await dailies.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )

            for guild_table in filter(
                lambda table: table["name"].startswith("guild_"), daily_tables
            ):
                guild_id = int(guild_table["name"][6:])
                guild_bonuses = await dailies.execute_fetchall(
                    f"SELECT * FROM {guild_table['name']}"
                )

                migrated_bonuses = map(
                    lambda row: (
                        row["channel"],
                        guild_id,
                        row["bonus"],
                        row["attachment"],
                    ),
                    guild_bonuses,
                )
                channel_bonuses.extend(migrated_bonuses)

                # channel -> guild associations
                channel_guilds = {row[0]: row[1] for row in channel_bonuses}

                # other claims
                for table in filter(
                    lambda table: not table["name"].startswith("guild_"), daily_tables
                ):
                    table_contents = await dailies.execute_fetchall(
                        f"SELECT * FROM {table['name']}"
                    )

                    # Channel bonus claims
                    # TODO: Check if this actually works when they are present
                    if table["name"].startswith("channel_"):
                        channel_id = int(table["name"][8:])
                        new_claims = map(
                            lambda row: (
                                channel_id,
                                channel_guilds[channel_id],
                                row["user"],
                            ),
                            table_contents,
                        )
                        channel_claims.extend(new_claims)

                    # `/daily claim` claims
                    elif table["name"].startswith("bonus_"):
                        guild_id = int(table["name"][6:])
                        new_claims = map(
                            lambda row: (guild_id, row["user"]), table_contents
                        )
                        daily_claims.extend(new_claims)

                    # DoorToDarkness claims (ignored because cog is no longer in use)
                    elif table["name"].startswith("door_"):
                        pass

                    else:
                        logger.warn(f"Unknown dailies table: {table['name']}")

        # Writing to the Postgres database
        async with self.db_pool.acquire() as con:
            # scores
            await con.executemany("INSERT INTO scores VALUES($1, $2, $3)", score_rows)

            # dailies
            await con.executemany(
                "INSERT INTO channel_bonuses VALUES($1, $2, $3, $4)",
                channel_bonuses,
            )
            await con.executemany(
                "INSERT INTO channel_claims VALUES($1, $2, $3)", channel_claims
            )
            await con.executemany(
                "INSERT INTO daily_claims VALUES($1, $2)", daily_claims
            )

        logger.info("Databases successfully migrated to PostgreSQL")
        await ctx.message.add_reaction("✅")

    async def cog_check(self, ctx: commands.Context):
        return await ctx.bot.is_owner(ctx.author)

    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.message.add_reaction("👎")
        else:
            await ctx.message.add_reaction("❌")
            logger.error(
                f"Error executing command `{ctx.prefix}{ctx.command.qualified_name}`:",
                exc_info=error,
            )


async def setup(bot):
    await bot.add_cog(Utilities(bot))
