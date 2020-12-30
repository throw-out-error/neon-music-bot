import json
import traceback

import discord
import functools
from youtube_dl import YoutubeDL
from discord.ext import commands
import asyncio
from ..bot import bot, ffmpeg_opts
from youtube_search import YoutubeSearch


class YTDLError(Exception):
    pass


class FFmpegError(Exception):
    pass


class MusicSource(discord.PCMVolumeTransformer):
    def __init__(
        self,
        ctx: commands.Context,
        source: discord.FFmpegPCMAudio,
        data: dict,
        volume: float = 0.5,
    ):
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data

    def __str__(self):
        return "**{0.title}**".format(self)

    def get(self, name: str, default=None):
        """
        :raises ValueError: when the default value is invalid and the original value is invalid
        """
        try:
            return self.__getattribute__(name)
        except AttributeError:
            if default:
                return default
            else:
                raise ValueError(f"Invalid default value: {default}")


class FFmpegSource(MusicSource):
    def __init__(
        self,
        ctx: commands.Context,
        source: discord.FFmpegPCMAudio,
        data: dict,
        volume: float = 0.5,
    ):
        super().__init__(ctx, source, data, volume)
        self.title = data.get("url", "")
        self.url = self.title

    @classmethod
    async def create_source(
        cls,
        data: dict,
        ctx: commands.Context,
        search: str,
        *,
        loop: asyncio.BaseEventLoop = None,
    ):
        loop or asyncio.get_event_loop()

        if data is None:
            raise YTDLError("Couldn't find anything that matches `{}`".format(search))

        return cls(
            ctx, discord.FFmpegPCMAudio(data.get("url", ""), **ffmpeg_opts), data=data
        )


class YTDLSource(MusicSource):
    YTDL_OPTIONS = {
        "format": "bestaudio/best",
        "extractaudio": True,
        "audioformat": "mp3",
        "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
        "restrictfilenames": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "quiet": True,
        "no_warnings": True,
        "default_search": "ytsearch",
        "source_address": "0.0.0.0",
    }

    ytdl = YoutubeDL(YTDL_OPTIONS)

    def __init__(
        self,
        ctx: commands.Context,
        source: discord.FFmpegPCMAudio,
        data: dict,
        volume: float = 0.5,
    ):
        super().__init__(ctx, source, data, volume)
        self.uploader = data.get("uploader")
        self.uploader_url = data.get("uploader_url", "")
        date = data.get("upload_date")
        self.upload_date = date[6:8] + "." + date[4:6] + "." + date[0:4]
        self.stream_url = data.get("url", "")
        self.dislikes = data.get("dislike_count")
        self.likes = data.get("like_count")
        self.views = data.get("view_count")
        self.url = data.get("url", "")
        self.tags = data.get("tags")
        self.duration = self.parse_duration(int(data.get("duration")))
        self.title = data.get("title")
        self.thumbnail = data.get("thumbnail")
        self.description = data.get("description")

    def __str__(self):
        return "**{0.title}** by **{0.uploader}**".format(self)

    @classmethod
    async def create_source(
        cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None
    ):
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(
            cls.ytdl.extract_info, search, download=False, process=False
        )
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError("Couldn't find anything that matches `{}`".format(search))

        if "entries" not in data:
            process_info = data
        else:
            process_info = None
            for entry in data["entries"]:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YTDLError(
                    "Couldn't find anything that matches `{}`".format(search)
                )

        webpage_url = process_info.get("webpage_url", "")
        partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError("Couldn't fetch `{}`".format(webpage_url))

        if "entries" not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = list(processed_info["entries"]).pop(0)
                except IndexError:
                    raise YTDLError(
                        "Couldn't retrieve any matches for `{}`".format(webpage_url)
                    )

        return cls(
            ctx, discord.FFmpegPCMAudio(info["url"] or "", **ffmpeg_opts), data=info
        )

    @classmethod
    async def search_source(
        cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None
    ):
        channel = ctx.channel
        loop = loop or asyncio.get_event_loop()

        cls.search = {
            "title": f"Search results for:\n**{search}**",
            "type": "rich",
            "color": 7506394,
            "author": {
                "name": f"{ctx.author.name}",
                "url": f"{ctx.author.avatar_url}",
                "icon_url": f"{ctx.author.avatar_url}",
            },
        }

        lst = []
        count = 0
        yt = YoutubeSearch(search, max_results=10).to_json()
        info = json.loads(yt)
        for e in info["videos"]:
            # lst.append(f'`{info["entries"].index(e) + 1}.` {e.get("title")} **[{YTDLSource.parse_duration(int(
            # e.get("duration")))}]**\n')
            v_id = e.get("id")
            v_url = "https://www.youtube.com/watch?v=%s" % v_id
            lst.append(f'`{count + 1}.` [{e.get("title")}]({v_url})\n')
            count += 1

        lst.append("\n**Type a number to make a choice, Type `cancel` to exit**")
        cls.search["description"] = "\n".join(lst)

        em = discord.Embed.from_dict(cls.search)
        await ctx.send(embed=em, delete_after=45.0)

        def check(msg):
            return (
                msg.content.isdigit() is True
                and msg.channel == channel
                or msg.content == "cancel"
                or msg.content == "Cancel"
            )

        try:
            m = await bot.wait_for("message", check=check, timeout=45.0)

        except asyncio.TimeoutError:
            rtrn = "timeout"

        else:
            if m.content.isdigit() is True:
                sel = int(m.content)
                data = None
                if 0 < sel <= 10:
                    v_id = info["videos"][sel - 1]["id"]
                    v_url = "https://www.youtube.com/watch?v=%s" % v_id
                    # print(v_url)
                    partial = functools.partial(
                        cls.ytdl.extract_info, v_url, download=False
                    )
                    data = await loop.run_in_executor(None, partial)
                    rtrn = cls(
                        ctx,
                        discord.FFmpegPCMAudio(data["url"], **ffmpeg_opts),
                        data=data,
                    )
                else:
                    rtrn = "sel_invalid"
            elif m.content == "cancel":
                rtrn = "cancel"
            else:
                rtrn = "sel_invalid"

        return rtrn

    @staticmethod
    def parse_duration(duration: int):
        value = ""
        if duration > 0:
            minutes, seconds = divmod(duration, 60)
            hours, minutes = divmod(minutes, 60)
            days, hours = divmod(hours, 24)

            duration = []
            if days > 0:
                duration.append("{}".format(days))
            if hours > 0:
                duration.append("{}".format(hours))
            if minutes > 0:
                duration.append("{}".format(minutes))
            if seconds > 0:
                duration.append("{}".format(seconds))

            value = ":".join(duration)

        elif duration == 0:
            value = "LIVE"

        return value
