import datetime
import functools
import logging
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .cog_config import config, configured_guilds

logger = logging.getLogger(__name__)


def gamenight_increments(db_row, guild, host_id):
    point_thresholds = config["guilds"][str(guild.id)]["thresholds"]

    # Convert keys to ints (TOML makes them strings by default)
    point_thresholds = {
        int(minutes): bonus for minutes, bonus in point_thresholds.items()
    }

    point_duration = max(
        filter(
            lambda threshold: threshold <= db_row["minutes"],
            point_thresholds,
        ),
        default=0,
    )
    participation_points = point_thresholds.get(point_duration)

    if participation_points is not None:
        points = participation_points + (17 if db_row["userid"] == host_id else 0)
        return (db_row["userid"], points)
    else:
        return None


# TODO: name this function better
def leaderboard_entry(base_str, member_info, guild, host_id):
    place = member_info[0]
    log_row = member_info[1]

    member = guild.get_member(log_row["userid"])
    if member is None:
        return base_str

    host_string = " (host)" if member.id == host_id else ""

    return (
        base_str + f"{place}{host_string} - {member.mention} ({log_row['formatted']})\n"
    )


@app_commands.guilds(*configured_guilds)
class GameNights(commands.GroupCog, group_name="gamenight"):
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = bot.db_pool

    async def cog_load(self):
        async with self.db_pool.acquire() as con:
            # Ongoing gamenights
            await con.execute(
                "CREATE TABLE IF NOT EXISTS gamenights"
                "(voice_channel BIGINT UNIQUE, guild BIGINT, host BIGINT, "
                "start_channel BIGINT, UNIQUE(guild, host))"
            )

            # Voice channel duration tracking
            await con.execute(
                "CREATE TABLE IF NOT EXISTS voice_logs"
                "(channel BIGINT, guild BIGINT, userid BIGINT, "
                "duration INTERVAL, join_time TIMESTAMP WITH TIME ZONE, "
                "UNIQUE(channel, userid))"
            )

        self.clear_voice_logs.start()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Ignore if a user is a bot or only mutes/deafens
        if member.bot or before.channel == after.channel:
            return

        # Check if user's current/previous voice channel had ongoing game night(s)
        async with self.db_pool.acquire() as con:
            if before.channel is not None:
                # UPDATE is a noop if the WHERE clause doesn't match
                left_gamenight = await con.fetchval(
                    "WITH left_gamenight AS (SELECT TRUE FROM gamenights WHERE voice_channel = $2) "
                    "UPDATE voice_logs SET duration = duration + (CURRENT_TIMESTAMP - join_time) WHERE userid = $1 and channel = $2 RETURNING (SELECT * FROM left_gamenight)",
                    member.id,
                    before.channel.id,
                )

            if after.channel is not None:
                await con.execute(
                    "INSERT INTO voice_logs VALUES($1, $2, $3, '0S'::INTERVAL, CURRENT_TIMESTAMP) "
                    "ON CONFLICT(channel, userid) DO UPDATE SET join_time = EXCLUDED.join_time",
                    after.channel.id,
                    after.channel.guild.id,
                    member.id,
                )
                left_gamenight = False

        if left_gamenight and not before.channel.members:
            await self.end_gamenight(before.channel)

    async def end_gamenight(self, channel):
        # in db:
        async with self.db_pool.acquire() as con:
            #  get game night info (error if ending nonexistent?)
            gamenight_info = await con.fetch(
                "SELECT start_channel, host FROM gamenights WHERE voice_channel = $1 AND guild = $2",
                channel.id,
                channel.guild.id,
            )

            #  grab user/duration combos (only need/extract hour/minute)
            participants = await con.fetch(
                "SELECT userid, EXTRACT(EPOCH FROM duration)/60 AS minutes, to_char(duration, 'HH24:MI') AS formatted "
                "FROM voice_logs WHERE channel = $1 ORDER BY duration DESC",
                channel.id,
            )

            #  delete from voice_logs/gamenights (or just gamenights? logs cleared at midnight)
            await con.execute(
                "DELETE FROM gamenights WHERE voice_channel = $1", channel.id
            )

        if gamenight_info is None:
            logger.warn(
                "Tried to end game night in channel {channel.name} when one wasn't started"
            )
            return

        host_id = gamenight_info[0]["host"]

        # outside db:
        #  enumerate users based on duration
        make_leaderboard = functools.partial(
            leaderboard_entry, guild=channel.guild, host_id=host_id
        )

        #  functools.reduce into embed description?
        leaderboard = functools.reduce(
            make_leaderboard, enumerate(participants, start=1)
        )

        #  bulk update scores for users
        if (scores_cog := self.bot.get_cog("Scores")) is not None:
            guild_increments = functools.partial(
                gamenight_increments,
                guild=channel.guild,
                host_id=host_id,
            )
            point_increments = filter(
                lambda bonus: bonus is not None, map(guild_increments, participants)
            )
            await scores_cog.bulk_increment_scores(channel.guild, point_increments)

        summary_channel = channel.guild.get_channel(gamenight_info[0]["start_channel"])
        await summary_channel.send(
            embed=discord.Embed(
                title=f"Game night summary - {channel.name}",
                description=leaderboard,
            )
        )

    @app_commands.command(
        name="host",
        description="Start a game night in your current voice channel.",
    )
    @app_commands.describe(host="The host of the gamenight (default you)")
    async def gamenight_host(
        self, interaction: discord.Interaction, host: discord.Member = None
    ):
        if config["guilds"][str(interaction.guild_id)].get("thresholds") is None:
            logger.warn(
                f"Attempted to start game night in unconfigured guild {interaction.guild.name}"
            )
            return await interaction.response.send_message(
                "Game nights for this aren't configured for this server :)",
                ephemeral=True,
            )

        # TODO: Add a channel parameter to retroactively declare a game night (?)
        if (voice_state := interaction.user.voice) is None:
            return await interaction.response.send_message(
                "You need to be in a voice channel to start a game night!",
                ephemeral=True,
            )

        if host is None:
            host = interaction.user

        gamenight_channel = voice_state.channel

        async with self.db_pool.acquire() as con:
            # Add host/voice channel to guild game night table
            await con.execute(
                f"INSERT INTO gamenights VALUES($1, $2, $3, $4)",
                gamenight_channel.id,
                interaction.guild_id,
                host.id,
                interaction.channel_id,
            )

        await interaction.response.send_message(
            f"Started game night in voice channel {gamenight_channel.name}!"
        )
        logger.info(
            f"Started game night in channel {gamenight_channel.name} "
            f"with {len(gamenight_channel.members)} initial members"
        )

    @tasks.loop(time=datetime.time(11, 59, 0, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def clear_voice_logs(self):
        async with self.db_pool.acquire() as con:
            # Don't delete logs from channels with an ongoing gamenight
            await con.execute(
                "DELETE FROM voice_logs WHERE channel NOT IN (SELECT voice_channel FROM gamenights"
            )


async def setup(bot):
    await bot.add_cog(GameNights(bot))
