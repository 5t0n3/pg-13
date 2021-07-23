import aiosqlite

from discord.ext import commands
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
        guild_ids=GUILDS,
        description="Attach a daily reward to messages in a channel.",
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
        print(channel)
        await ctx.send(content="got your command!")
        pass

    @commands.Cog.listener()
    async def on_message(self, message):
        # Give user daily bonus if applicable
        async with aiosqlite.connect("dailies.db") as dailies:
            # Check if guild has dailies
            guild_table = await dailies.execute(
                "SELECT * FROM sqlite_master WHERE name = ?", (message.guild.id,)
            )
            has_dailies = await guild_table.fetchone()

            if has_dailies is not None:
                # Check if message's channel has a daily bonus
                channel_request = await dailies.execute(
                    "SELECT increment FROM ? WHERE channel = ?",
                    (message.guild.id, message.channel.id),
                )
                channel_bonus = await channel_request.fetchone()

                if channel_bonus is not None:
                    claim_request = await dailies.execute(
                        "SELECT claimed FROM ? WHERE user_id = ?",
                        (message.channel.id, message.author.id),
                    )
                    claimed_today = await claim_request.fetchone()

                    # Handle None case (user hasn't claimed in the past)
                    # or False case (not claimed today)
                    if claimed_today is None:
                        async with aiosqlite.connect("scores.db") as scores:
                            # Fetch user score or default to (a row containing) 0
                            score_request = (
                                await scores.execute(
                                    "SELECT score FROM ? WHERE user_id = ?",
                                    (message.guild.id, message.author.id),
                                ).fetchone()
                                or (0,)
                            )
                            current_score = await score_request.fetchone()

                            # Update user's score
                            new_score = (current_score[0] or (0,))[0] + channel_bonus[
                                "increment"
                            ]
                            await scores.execute(
                                "INSERT INTO ? (user_id, score) values (?, ?) ON DUPLICATE KEY UPDATE score = ?",
                                (
                                    message.guild.id,
                                    message.author.id,
                                    new_score,
                                    new_score,
                                ),
                            )
                            await scores.commit()

        await self.bot.process_commands(message)
