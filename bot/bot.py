import discord
from discord.ext.commands.context import Context
from discord.ext import commands
from discord.ext.commands.errors import CommandNotFound
from .player import setup as setupPlayer
from .config import cfg

def main():
    bot = commands.Bot(command_prefix=cfg.bot.get("prefix", "%"))

    setupPlayer(bot)

    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, CommandNotFound):
            return await ctx.channel.send(f"Invalid command: {error}")
        else:
            return await ctx.channel.send(f"Unknown error: {error}")

    @bot.command(name="streamlist")
    async def streams(ctx: Context):
        await ctx.channel.send(
            "Go to https://bot.neonradio.net/streams.html for a list of music streams."
        )

    print("Loading bot.")
    bot.run(cfg.bot.get("token"))
