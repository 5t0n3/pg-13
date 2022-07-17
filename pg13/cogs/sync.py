import logging

import discord
from discord.ext import commands

from .cog_config import configured_guilds


async def is_me(ctx: commands.Context):
    return await ctx.bot.is_owner(ctx.author)


class Sync(commands.Cog):
    def __init__(self):
        self.logger = logging.getLogger("pg13.sync")

    @commands.command(name="sync", description="Sync all slash commands")
    @commands.check(is_me)
    async def sync(self, ctx: commands.Context):
        # TODO: Sync global commands instead
        for guild in configured_guilds:
            await ctx.bot.tree.sync(guild=discord.Object(guild))
        await ctx.message.add_reaction("🔄")
        self.logger.info("Successfully synced all application commands!")

    @sync.error
    async def sync_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.message.add_reaction("👎")
        else:
            self.logger.error("Error syncing commands:", exc_info=error)


async def setup(bot):
    await bot.add_cog(Sync())
