"""
Please understand Music bots are complex, and that even this basic example can be daunting to a beginner.
For this reason it's highly advised you familiarize yourself with discord.py, python and asyncio, BEFORE
you attempt to write a music bot.
This example makes use of: Python 3.6
For a more basic voice example please read:
    https://github.com/Rapptz/discord.py/blob/rewrite/examples/basic_voice.py
This is a very basic playlist example, which allows per guild playback of unique queues.
The commands implement very basic logic for basic usage. But allow for expansion. It would be advisable to implement
your own permissions and usage logic for commands.
e.g You might like to implement a vote before skipping the song or only allow admins to stop the player.
Music bots require lots of work, and tuning. Goodluck.
If you find any bugs feel free to ping me on discord. @Eviee#0666
"""
from bot.player.source import FFmpegSource, MusicSource, YTDLError, YTDLSource
from async_timeout import timeout
from youtube_dl import YoutubeDL
import discord
from discord.ext import commands
from ..config import cfg
from ..bot import ffmpeg_opts
import asyncio
import itertools
import math
import random

ytdlopts = {
    "format": "bestaudio/best",
    "outtmpl": "downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",  # ipv6 addresses cause issues sometimes
}
ytdl = YoutubeDL(ytdlopts)


class VoiceError(Exception):
    pass


class Song:
    __slots__ = ("source", "requester")

    def __init__(self, source: MusicSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        embed = (
            discord.Embed(
                title="Now playing",
                description=f"```css\n{self.source.get('title', 'Untitled Song')}\n```",
                color=discord.Color.blurple(),
            )
            .add_field(name="Duration", value=self.source.get("duration", 0))
            .add_field(name="Requested by", value=self.requester.mention)
            .add_field(
                name="Uploader",
                value=f"[{self.source.get('uploader', 'Unknown')}]({self.source.get('uploader_url', '')})",
            )
            .add_field(name="URL", value=f"[Click]({self.source.get('url', '')})")
            .set_thumbnail(url=self.source.get("thumbnail", ""))
            .set_author(name=self.requester.name, icon_url=self.requester.avatar_url)
        )

        return embed


class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]


class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx

        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()
        self.exists = True

        self._loop = False
        self._volume = 0.5
        self.skip_votes = set()

        self.audio_player = bot.loop.create_task(self.audio_player_task())

    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self):
        while True:
            self.next.clear()
            self.now = None

            if self.loop == False:
                # Try to get the next song within 3 minutes.
                # If no song will be added to the queue in time,
                # the player will disconnect due to performance
                # reasons.
                try:
                    async with timeout(180):  # 3 minutes
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    self.bot.loop.create_task(self.stop())
                    self.exists = False
                    return

                self.current.source.volume = self._volume
                self.voice.play(self.current.source, after=self.play_next_song)
                await self.current.source.channel.send(
                    embed=self.current.create_embed()
                )

            # If the song is looped
            elif self.loop == True:
                self.now = discord.FFmpegPCMAudio(
                    self.current.source.stream_url, **ffmpeg_opts
                )
                self.voice.play(self.now, after=self.play_next_song)

            await self.next.wait()

    def play_next_song(self, error=None):
        if error:
            raise VoiceError(str(error))

        self.next.set()

    def skip(self):
        self.skip_votes.clear()

        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()

        if self.voice:
            await self.voice.disconnect()
            self.voice = None


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state or not state.exists:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state

        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(_, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage(
                "This command can't be used in DM channels."
            )

        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    @commands.command(name="join", invoke_without_subcommand=True)
    async def _join(_, ctx: commands.Context):
        """Joins a voice channel."""

        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name="summon")
    @commands.has_permissions(manage_guild=True)
    async def _summon(
        _, ctx: commands.Context, *, channel: discord.VoiceChannel = None
    ):
        """Summons the bot to a voice channel.
        If no channel was specified, it joins your channel.
        """

        if not channel and not ctx.author.voice:
            raise VoiceError(
                "You are neither connected to a voice channel nor specified a channel to join."
            )

        destination = channel or ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name="leave", aliases=["disconnect"])
    @commands.has_permissions(manage_guild=True)
    async def _leave(self, ctx: commands.Context):
        """Clears the queue and leaves the voice channel."""

        if not ctx.voice_state.voice:
            return await ctx.send("Not connected to any voice channel.")

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]

    @commands.command(name="volume")
    @commands.is_owner()
    async def _volume(_, ctx: commands.Context, *, volume: int):
        """Sets the volume of the player."""

        if not ctx.voice_state.is_playing:
            return await ctx.send("Nothing being played at the moment.")

        if 0 > volume > 100:
            return await ctx.send("Volume must be between 0 and 100")

        ctx.voice_state.volume = volume / 100
        await ctx.send("Volume of the player set to {}%".format(volume))

    @commands.command(name="now", aliases=["current", "playing"])
    async def _now(_, ctx: commands.Context):
        """Displays the currently playing song."""
        embed = ctx.voice_state.current.create_embed()
        await ctx.send(embed=embed)

    @commands.command(name="pause", aliases=["pa"])
    @commands.has_permissions(manage_guild=True)
    async def _pause(self, ctx: commands.Context):
        """Pauses the currently playing song."""
        if ctx.voice_state.is_playing and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction("⏯")

    @commands.command(name="resume", aliases=["re", "res"])
    @commands.has_permissions(manage_guild=True)
    async def _resume(_, ctx: commands.Context):
        """Resumes a currently paused song."""

        if ctx.voice_state.is_playing and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction("⏯")

    @commands.command(name="stop")
    @commands.has_permissions(manage_guild=True)
    async def _stop(_, ctx: commands.Context):
        """Stops playing song and clears the queue."""

        ctx.voice_state.songs.clear()

        if ctx.voice_state.is_playing:
            ctx.voice_state.voice.stop()
            await ctx.message.add_reaction("⏹")

    @commands.command(name="skip", aliases=["s"])
    async def _skip(_, ctx: commands.Context):
        """Vote to skip a song. The requester can automatically skip.
        3 skip votes are needed for the song to be skipped.
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send("Not playing any music right now...")

        voter = ctx.message.author
        if voter == ctx.voice_state.current.requester:
            await ctx.message.add_reaction("⏭")
            ctx.voice_state.skip()

        elif voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            if total_votes >= 3:
                await ctx.message.add_reaction("⏭")
                ctx.voice_state.skip()
            else:
                await ctx.send(
                    "Skip vote added, currently at **{}/3**".format(total_votes)
                )

        else:
            await ctx.send("You have already voted to skip this song.")

    @commands.command(name="queue")
    async def _queue(_, ctx: commands.Context, *, page: int = 1):
        """Shows the player's queue.
        You can optionally specify the page to show. Each page contains 10 elements.
        """

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send("Empty queue.")

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ""
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue += f"`{i + 1}.` [**{song.source.get('title', 'Untitled Song')}**]({song.source.get('url', '')})\n"

        embed = discord.Embed(
            description="**{} tracks:**\n\n{}".format(len(ctx.voice_state.songs), queue)
        ).set_footer(text="Viewing page {}/{}".format(page, pages))
        await ctx.send(embed=embed)

    @commands.command(name="shuffle")
    async def _shuffle(_, ctx: commands.Context):
        """Shuffles the queue."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send("Empty queue.")

        ctx.voice_state.songs.shuffle()
        await ctx.message.add_reaction("✅")

    @commands.command(name="remove")
    async def _remove(_, ctx: commands.Context, index: int):
        """Removes a song from the queue at a given index."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send("Empty queue.")

        ctx.voice_state.songs.remove(index - 1)
        await ctx.message.add_reaction("✅")

    @commands.command(name="loop")
    async def _loop(_, ctx: commands.Context):
        """Loops the currently playing song.
        Invoke this command again to unloop the song.
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send("Nothing being played at the moment.")

        # Inverse boolean value to loop and unloop.
        ctx.voice_state.loop = not ctx.voice_state.loop
        await ctx.message.add_reaction("✅")

    @commands.command(
        name="play",
        aliases=["sing"],
        description=f"Plays music, optionally from a youtube url or stream type. Valid stream types include: {list(cfg.get('streams', {}))}",
    )
    async def _play(self, ctx, *, search: str, streamId="1"):
        """Request a song and add it to the queue.
        This command attempts to join a valid voice channel if the bot is not already in one.
        Uses YTDL to automatically search and retrieve a song.
        Parameters
        ------------
        search: str [Required]
            The song to search and retrieve using YTDL. This could be a simple search, an ID or URL.
        streamId: str [Optional]
            Required if the stream is a specific stream type and not a url.
        """
        await ctx.trigger_typing()

        vc = ctx.voice_client

        if not vc:
            await ctx.invoke(self._join)

        source = None
        url = ""
        streams = cfg.get("streams", {})
        if not search or search == "":
            search = search or "lofi"
        if search in streams:
            try:
                url = streams.get(search).get(streamId)
            except:
                return await ctx.channel.send(
                    "Error: invalid stream type or stream id! Type '#help play' for more information."
                )
        else:
            url = search
        if "youtube" in url:
            # If download is False, source will be a dict which will be used later to regather the stream.
            # If download is True, source will be a discord.FFmpegPCMAudio with a VolumeTransformer.
            try:
                async with timeout(2):
                    source = await YTDLSource.create_source(
                        ctx, search, loop=self.bot.loop
                    )
            except:
                source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
        else:
            try:
                source = await FFmpegSource.create_source(
                    {"url": search}, ctx, url, loop=self.bot.loop
                )
            except Exception as err:
                if "ffmpeg" in err.__repr__():
                    print(err)
                    return await ctx.channel.send(
                        "Error: ffmpeg not found! Contact the developer or host of this bot if this issue persists."
                    )
                print(err.__repr__())
                return await ctx.channel.send(
                    "Error: invalid stream url! Type '#help play' for more information."
                )
        song = Song(source)
        await ctx.voice_state.songs.put(song)

    @commands.command(name="search")
    async def _search(self, ctx: commands.Context, *, search: str):
        """Searches youtube.
        It returns an imbed of the first 10 results collected from youtube.
        Then the user can choose one of the titles by typing a number
        in chat or they can cancel by typing "cancel" in chat.
        Each title in the list can be clicked as a link.
        """
        async with ctx.typing():
            try:
                source = await YTDLSource.search_source(ctx, search, loop=self.bot.loop)
            except YTDLError as e:
                await ctx.send(
                    "An error occurred while processing this request: {}".format(str(e))
                )
            else:
                if source == "sel_invalid":
                    await ctx.send("Invalid selection")
                elif source == "cancel":
                    await ctx.send(":white_check_mark:")
                elif source == "timeout":
                    await ctx.send(":alarm_clock: **Time's up bud**")
                else:
                    if not ctx.voice_state.voice:
                        await ctx.invoke(self._join)

                    song = Song(source)
                    await ctx.voice_state.songs.put(song)
                    await ctx.send("Enqueued {}".format(str(source)))

    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError("You are not connected to any voice channel.")

        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError("Bot is already in a voice channel.")


def setup(bot):
    bot.add_cog(Music(bot))
