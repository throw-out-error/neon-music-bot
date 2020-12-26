from discord.ext.commands.context import Context
from discord.ext.commands.errors import CommandNotFound

from .config import cfg
from .player.player import setup as setup_player
from .bot import bot, run_bot
import traceback


def main():
    setup_player(bot)

    @bot.event
    async def on_command_error(ctx, error: Exception):
        if cfg.bot.get("environment") != "production":
            traceback.print_exception(type(error), error, error.__traceback__)
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
    run_bot()
