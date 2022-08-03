import functools

import discord


def build_embed(base_str, member_info):
    place = member_info[0]
    score_info = member_info[1]
    username = "[user left]" if score_info[0] is None else score_info[0].display_name

    return base_str + f"{place}: {username} - {score_info[1]}\n"


class Leaderboard(discord.ui.View):
    def __init__(self, guild, db_pool):
        super().__init__()
        self.guild = guild
        self.db_pool = db_pool
        self.offset = 0

    async def init_leaderboard(self):
        async with self.db_pool.acquire() as con:
            user_scores = await con.fetch(
                "SELECT userid, score FROM scores WHERE guild = $1 "
                "ORDER BY score DESC, userid DESC FETCH NEXT 30 ROWS ONLY",
                self.guild.id,
                self.offset,
            )

        self.current_users = [(member, row["score"]) for row in user_scores[:15]]
        self.next_users = user_scores[15:]

        self.leaderboard_right.disabled = len(self.next_users) == 0

        leaderboard = functools.reduce(
            build_embed, enumerate(self.current_users, start=1), ""
        )
        leaderboard_embed = discord.Embed(
            title=f"{self.guild.name} Leaderboard", description=leaderboard
        )
        await interaction.response.send_message(embed=leaderboard_embed, view=self)

    async def update(self, interaction):
        self.leaderboard_left.disabled = self.offset == 0
        self.leaderboard_right.disabled = len(self.next_users) == 0

        leaderboard = functools.reduce(
            build_embed, enumerate(self.current_users, start=self.offset + 1), ""
        )
        leaderboard_embed = discord.Embed(
            title=f"{self.guild.name} Leaderboard", description=leaderboard
        )
        await interaction.response.edit_message(embed=leaderboard_embed, view=self)

    @discord.ui.button(emoji="⬅️", custom_id="leaderboard:left", disabled=True)
    async def leaderboard_left(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.next_users = self.current_users
        self.offset -= 15

        async with self.db_pool.acquire() as con:
            self.current_users = await con.fetch(
                "SELECT userid, score FROM scores WHERE guild = $1 "
                "ORDER BY score DESC, userid DESC OFFSET $2 ROWS FETCH NEXT 15 ROWS ONLY",
                self.guild.id,
                self.offset,
            )

        await self.update(interaction)

    @discord.ui.button(emoji="➡️", custom_id="leaderboard:right")
    async def leaderboard_right(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_users = self.next_users
        self.offset += 15

        async with self.db_pool.acquire() as con:
            self.next_users = await con.fetch(
                "SELECT userid, score FROM scores WHERE guild = $1 "
                "ORDER BY score DESC, userid DESC OFFSET $2 ROWS FETCH NEXT 15 ROWS ONLY",
                self.guild.id,
                self.offset,
            )

        await self.update(interaction)
