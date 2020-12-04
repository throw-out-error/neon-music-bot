import discord
from discord.ext.commands.context import Context
from discord.ext import commands
from discord.ext.commands.errors import CommandNotFound
from discord.utils import get
import pafy
import lazyConfig
from pathlib import Path

def main():
    cfg_path = Path("config").resolve()
    cfg = lazyConfig.from_path(
        config=cfg_path,
    )
    bot = commands.Bot(command_prefix=cfg.bot.get("prefix", "#"))

    def vc_check(ctx):
        voice_client = get(ctx.bot.voice_clients, guild=ctx.guild)
        return voice_client, voice_client and voice_client.is_connected()

    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, CommandNotFound):
            return await ctx.channel.send(f"Invalid command: {error}")
        raise error

    @bot.command(
        name="play",
        brief="Plays music (from a stream)",
        description=f"Plays music, optionally from a youtube url or stream type. Valid stream types include: {list(cfg.get('streams'))}",
    )
    async def play(ctx: Context, stream):
        stream = stream or "lofi"
        streams = cfg.get("streams")
        url = ""
        if stream in streams:
            url = streams.get(stream)
        else:
            url = stream
        if "youtube" in url:
            video = pafy.new(url)
            best = video.getbest()
            playurl = best.url
            if ctx.author.voice and ctx.author.voice.channel:
                voice_client, is_connected = vc_check(ctx)
                if not is_connected:
                    vc = await ctx.author.voice.channel.connect()
                else:
                    vc = voice_client
                try:
                    vc.stop()
                except:
                    pass
                vc.play(discord.FFmpegPCMAudio(playurl))
                await ctx.channel.send("Now playing music in your vc!")
            else:
                await ctx.channel.send("You are not connected to a voice channel.")
        else:
            if ctx.author.voice and ctx.author.voice.channel:
                voice_client, is_connected = vc_check(ctx)
                if not is_connected:
                    vc = await ctx.author.voice.channel.connect()
                else:
                    vc = voice_client
                try:
                    vc.stop()
                except:
                    pass
                vc.play(discord.FFmpegPCMAudio(url))
                await ctx.channel.send("Now playing music in your vc!")
            else:
                await ctx.channel.send("You are not connected to a voice channel.")

    @bot.command(
        name="dis",
        brief="Disconnects from vc",
        description="Disconnects from a voice channel.",
    )
    async def disconnect(ctx: Context):
        if ctx.author.voice and ctx.author.voice.channel:
            voice_client, is_connected = vc_check(ctx)
            if is_connected:
                await voice_client.disconnect()
                await ctx.channel.send("Disconnected from your vc.")

    print("Loading bot.")
    bot.run(cfg.bot.get("token"))
