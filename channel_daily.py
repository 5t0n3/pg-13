import sqlite3

from discord.ext import commands


class ChannelDailyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.dailies = None

    @commands.Cog.listener()
    async def on_ready():
        if self.dailies is None:
            self.dailies = sqlite3.connect("dailies.dailies")

    @commands.Cog.listener()
    async def on_disconnect(self):
        if self.dailies is not None:
            self.dailies.close()
            self.dailies = None

    @commands.Cog.listener()
    async def on_message(self, message):
        self.dailies.execute(
            "SELECT * FROM sqlite_master WHERE name = ?", (message.guild.id,)
        )
        current_guild = self.dailies.fetchone()

        if current_guild is not None:
            self.dailies.execute(
                "SELECT claimed FROM ? WHERE user_id = ?",
                (message.channel.id, message.author.id),
            )
            claimed_today = self.dailies.fetchone()

            if not claimed_today:
                scores = self.bot.scores_db
                scores.execute(
                    "SELECT score FROM ? WHERE user_id = ?",
                    (message.guild.id, message.author.id),
                )
                user_score = self.bot.scores.fetchone() or 0

                # Fetch channel's increment
                self.dailies.execute(
                    "SELECT increment FROM ? WHERE channel_id = ?",
                    (message.guild.id, message.channel.id),
                )
                increment = self.dailies.fetchone()

                # Update user's score
                new_score = user_score + increment
                with scores:
                    scores.execute(
                        "INSERT INTO ? (user_id, score) values (?, ?) ON DUPLICATE KEY UPDATE score = ?",
                        (message.guild.id, message.author.id, new_score, new_score),
                    )

        await self.bot.process_commands(message)
