async def setup(bot):
    from .cog import Say

    await bot.add_cog(Say(bot))
