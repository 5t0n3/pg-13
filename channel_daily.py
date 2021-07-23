import aiosqlite

from discord.ext import commands


class ChannelDailyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        # Give user daily bonus if applicable
        async with aiosqlite.connect("dailies.db") as dailies:
            # Check if guild has dailies
            guild_dailies = await dailies.execute(
                "SELECT * FROM sqlite_master WHERE name = ?", (message.guild.id,)
            ).fetchone()

            if guild_dailies is not None:
                # Check if message's channel has a daily bonus
                channel_bonus = await dailies.execute(
                    "SELECT increment FROM ? WHERE channel = ?",
                    (message.guild.id, message.channel.id),
                ).fetchone()

                if channel_bonus is not None:
                    claimed_today = await dailies.execute(
                        "SELECT claimed FROM ? WHERE user_id = ?",
                        (message.channel.id, message.author.id),
                    ).fetchone()

                    # Handle None case (user hasn't claimed in the past)
                    # or False case (not claimed today)
                    if claimed_today is None:
                        async with aiosqlite.connect("scores.db") as scores:
                            # Fetch user score or default to (a row containing) 0
                            user_score = (
                                await scores.execute(
                                    "SELECT score FROM ? WHERE user_id = ?",
                                    (message.guild.id, message.author.id),
                                ).fetchone()
                                or (0,)
                            )

                            # Update user's score
                            new_score = user_score["score"] + channel_bonus["increment"]
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
