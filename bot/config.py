from discord.ext import commands

import lazyConfig
from pathlib import Path

cfg_path = Path("config").resolve()
cfg = lazyConfig.from_path(
    config=cfg_path,
)


def check_owner(ctx: commands.Context):
    return str(ctx.message.author.id) in cfg.bot.get("developers", [])
