import asyncio

from discord.ext import commands
from .config import cfg

bot = commands.Bot(
    command_prefix=cfg.bot.get("prefix", "%"),
    case_insensitive=True,
    description="Neon Radio Bot",
)

ffmpeg_opts = {
    "before_options": "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


def run_bot():
    bot.run(cfg.bot.get("token"))
    return bot
