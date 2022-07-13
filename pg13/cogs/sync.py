import logging

from discord.ext import commands


async def is_me(ctx: commands.Context):
    return await ctx.bot.is_owner(ctx.author)


class Sync(commands.Cog):
    def __init__(self):
        self.logger = logging.getLogger("pg13.sync")

    @commands.command(name="sync", description="Sync all slash commands")
    @commands.check(is_me)
    async def sync(self, ctx: commands.Context):
        await ctx.bot.tree.sync()
        await ctx.message.add_reaction("🔄")
        self.logger.info("Successfully synced all application commands!")

    @sync.error
    async def sync_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.message.add_reaction("👎")


async def setup(bot):
    await bot.add_cog(Sync())
