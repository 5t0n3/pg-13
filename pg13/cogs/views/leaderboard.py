import collections
import functools

import discord

ScoreInfo = collections.namedtuple("ScoreInfo", ["member", "score"])


def build_embed(base_str, member_info):
    place = member_info[0]
    score_info = member_info[1]

    return (
        base_str + f"{place}: {score_info.member.display_name} - {score_info.score}\n"
    )


def filter_members(bundles, users_needed):
    valid_members = []
    total_users = 0

    for bundle in bundles:
        if bundle.member is not None:
            valid_members.append(bundle)

        total_users += 1

        if len(valid_members) == users_needed:
            break

    return valid_members, total_users


class Leaderboard(discord.ui.View):
    def __init__(self, guild, db_pool):
        super().__init__()
        self.guild = guild
        self.db_pool = db_pool
        self.page = 0

        # TODO: should scores be stored directly instead?
        self.offsets = [0]

    @property
    def current_offset(self):
        return self.offsets[self.page]

    @property
    def next_offset(self):
        return self.offsets[self.page + 1]

    async def interaction_check(self, interaction: discord.Interaction):
        # Ensure that only the original author can interact with a leaderboard
        return interaction.user.id == self.leaderboard_user

    async def init_leaderboard(self, interaction):
        self.leaderboard_user = interaction.user.id

        async with self.db_pool.acquire() as con:
            user_scores = await con.fetch(
                "SELECT userid, score FROM scores WHERE guild = $1 "
                "ORDER BY score DESC, userid DESC FETCH NEXT 30 ROWS ONLY",
                self.guild.id,
            )

        bundled_users = [
            ScoreInfo(self.guild.get_member(row["userid"]), row["score"])
            for row in user_scores
        ]
        valid_users, next_offset = filter_members(bundled_users, 15)
        self.current_users = valid_users
        self.offsets.append(next_offset)

        valid_next_users, lookahead = filter_members(bundled_users[next_offset:], 15)
        self.next_users = valid_next_users
        self.lookahead_length = lookahead

        self.leaderboard_right.disabled = len(self.next_users) == 0

        leaderboard = functools.reduce(
            build_embed, enumerate(self.current_users, start=1), ""
        )
        leaderboard_embed = discord.Embed(
            title=f"{self.guild.name} Leaderboard", description=leaderboard
        )
        await interaction.response.send_message(embed=leaderboard_embed, view=self)

    async def update(self, interaction):
        self.leaderboard_left.disabled = self.offsets[self.page] == 0
        self.leaderboard_right.disabled = len(self.next_users) == 0

        leaderboard = functools.reduce(
            build_embed,
            enumerate(self.current_users, start=self.page * 15 + 1),
            "",
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
        self.page -= 1

        async with self.db_pool.acquire() as con:
            unbundled_current = await con.fetch(
                "SELECT userid, score FROM scores WHERE guild = $1 "
                "ORDER BY score DESC, userid DESC OFFSET $2 ROWS FETCH NEXT $3 ROWS ONLY",
                self.guild.id,
                self.current_offset,
                self.next_offset - self.current_offset,
            )

        self.current_users = [
            ScoreInfo(member, row["score"])
            for row in unbundled_current
            if (member := self.guild.get_member(row["userid"])) is not None
        ]

        await self.update(interaction)

    @discord.ui.button(emoji="➡️", custom_id="leaderboard:right")
    async def leaderboard_right(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_users = self.next_users
        self.page += 1

        if len(self.current_users) < 15:
            async with self.db_pool.acquire() as con:
                unbundled_complement = await con.fetch(
                    "SELECT userid, score FROM scores WHERE guild = $1 "
                    "ORDER BY score DESC, userid DESC OFFSET $2 ROWS FETCH NEXT $3 ROWS ONLY",
                    self.guild.id,
                    self.current_offset + len(self.current_users),
                    15 - len(self.current_users) + 15,
                )

            raw_bundled = [
                ScoreInfo(self.guild.get_member(row["userid"]), row["score"])
                for row in unbundled_complement
            ]
            self.logger.debug(f"Raw bundled: {raw_bundled}")

            current_complement, total_complement = filter_members(
                raw_bundled, 15 - len(self.current_users)
            )
            self.current_users.extend(current_complement)

            self.offsets.append(
                self.current_offset + self.lookahead_length + total_complement
            )
            raw_next_bundles = raw_bundled[total_complement:]
            self.logger.debug(f"Raw next bundles: {raw_next_bundles}")

        # An offset exists 2 pages ahead of this one
        elif len(self.offsets) > self.page + 2:
            async with self.db_pool.acquire() as con:
                unbundled_next = await con.fetch(
                    "SELECT userid, score FROM scores WHERE guild = $1 "
                    "ORDER BY score DESC, userid DESC OFFSET $2 ROWS FETCH NEXT $3 ROWS ONLY",
                    self.guild.id,
                    self.next_offset,
                    self.offsets[self.page + 2] - self.next_offset,
                )

            self.next_users = [
                ScoreInfo(self.guild.get_member(row["userid"]), row["score"])
                for row in unbundled_next
                if (member := self.guild.get_member(row["userid"])) is not None
            ]

            return await self.update(interaction)

        else:
            async with self.db_pool.acquire() as con:
                unbundled_next = await con.fetch(
                    "SELECT userid, score FROM scores WHERE guild = $1 "
                    "ORDER BY score DESC, userid DESC OFFSET $2 ROWS FETCH NEXT 15 ROWS ONLY",
                    self.guild.id,
                    self.next_offset,
                )

            raw_next_bundles = [
                ScoreInfo(self.guild.get_member(row["userid"]), row["score"])
                for row in unbundled_next
            ]

            self.offsets.append(self.current_offset + self.lookahead_length)

        valid_next, lookahead = filter_members(raw_next_bundles, 15)
        self.next_users = valid_next
        self.lookahead_length = lookahead

        await self.update(interaction)
