import functools

import discord


def build_embed(base_str, member_info):
    place = member_info[0]
    score_info = member_info[1]

    return base_str + f"{place}: {score_info[0].mention} - {score_info[1]}\n"


class Leaderboard(discord.ui.View):
    def __init__(self, guild, db_pool):
        self.guild = guild
        self.db_pool = db_pool
        self.start_place = 1
        self.offset = 0

    async def build_leaderboard(self):
        async with self.db_pool.acquire() as con:
            user_scores = await con.fetch(
                "SELECT userid, score FROM scores WHERE guild = $1 "
                "ORDER BY score DESC OFFSET $2 ROWS FETCH NEXT 15 ROWS ONLY",
                self.guild.id,
                self.offset,
            )

        valid_members = [
            (member, row["score"])
            for row in user_scores
            if (member := self.guild.get_member(row["userid"])) is not None
        ]
        leaderboard = functools.reduce(
            build_embed, enumerate(valid_members, start=self.start_place), ""
        )

        return leaderboard, len(valid_members)

    async def init_leaderboard(self):
        description, num_members = await self.build_leaderboard()
        self.start_place += num_members

        leaderboard = discord.Embed(
            title=f"{interaction.guild.name} Leaderboard", description=description
        )
        await interaction.response.edit_message(embed=leaderboard, view=self)

    @discord.ui.button(emoji="◀️", custom_id="leaderboard:left", disabled=True)
    async def leaderboard_left(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.offset -= 15
        description, num_members = await self.build_leaderboard()
        self.start_place -= num_members

        if self.offset == 0:
            button.disabled = True

        self.leaderboard_right.disabled = False

        leaderboard = discord.Embed(
            title=f"{interaction.guild.name} Leaderboard", description=description
        )
        await interaction.response.edit_message(embed=leaderboard, view=self)

    @discord.ui.button(emoji="◀️", custom_id="leaderboard:right")
    async def leaderboard_right(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.offset += 15
        description, num_members = await self.build_leaderboard(interaction.guild)

        if num_members == 0:
            button.disabled = True
            await interaction.response.edit_message(view=self)

        else:
            self.start_place += num_members
            self.leaderboard_left.disabled = False

            leaderboard = discord.Embed(
                title=f"{interaction.guild.name} Leaderboard", description=description
            )
            await interaction.response.edit_message(embed=leaderboard, view=self)
