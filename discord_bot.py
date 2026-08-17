import asyncio
import re
import signal
import sys
from datetime import datetime
from typing import Optional
from urllib.parse import urlsplit

import discord
from colorama import Fore as f
from colorama import init
from discord.ext import commands, tasks

from config import (
    CAPTION_CACHE_URL,
    CAPTION_INGEST_SECRET,
    DISCORD_PREFIX,
    DISCORD_TOKEN,
    GEMINI_API_KEY,
    GEMINI_FALLBACK_MODEL,
    GEMINI_MODEL,
    LOCAL_FEED_POLLING,
    MAX_MEMES_PER_REQUEST,
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    SUBSCRIPTIONS_FILE,
    SUBSCRIPTIONS_SEED_B64,
    YOUTUBE_POLL_MINUTES,
)
from caption_cache import CaptionCacheClient
from gemini_summary import GeminiSummaryClient, split_discord_messages
from reddit_client import RedditMemeFetcher
from youtube_client import SubscriptionStore, VideoSubscription, YouTubeFeedClient
from youtube_transcript import TranscriptBundle, YouTubeTranscriptClient

init(autoreset=True)

YOUTUBE_VIDEO_ID_PATTERN = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:[^\s#]*&)?v=|shorts/|live/|embed/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)
TRANSCRIPT_CHANNEL_NAME = "youtube-transcripts"
TRANSCRIPT_CHANNEL_TOPIC = "Paste a YouTube URL here for a mobile-friendly transcript with one-tap copy."
SUMMARY_CHANNEL_NAME = "summary"
SUMMARY_SECTION_NAMES = (
    "Executive overview",
    "Core ideas and reasoning",
    "Step-by-step methods and workflows",
    "Tools, websites, and resources mentioned",
    "Examples, evidence, and notable claims",
    "Practical takeaways",
    "Caveats and limits",
    "Channel",
)
TIMESTAMP_PATTERN = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\]")


def _summary_sections(summary: str) -> list[tuple[str, str]]:
    """Turn the model's fixed Markdown headings into readable Discord cards."""
    sections: list[tuple[str, str]] = []
    title = "Overview"
    lines: list[str] = []
    known = {name.casefold(): name for name in SUMMARY_SECTION_NAMES}

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text:
            sections.append((title, text))

    for raw_line in summary.replace("\r\n", "\n").split("\n"):
        candidate = raw_line.strip().strip("#").strip().strip("*").strip()
        heading = known.get(candidate.casefold())
        if heading:
            flush()
            title = heading
            lines = []
            continue
        if candidate.casefold() in {"learning brief", "video brief"} or candidate == "---":
            continue
        lines.append(raw_line)
    flush()
    return sections or [("Video brief", summary.strip())]


def _link_timestamps(text: str, video_id: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        hours, minutes, seconds = (int(value) for value in match.groups())
        total = hours * 3600 + minutes * 60 + seconds
        label = f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
        return f"[{label}](https://youtu.be/{video_id}?t={total})"

    return TIMESTAMP_PATTERN.sub(replacement, text)


class SummaryQuestionModal(discord.ui.Modal, title="Ask about this video"):
    question = discord.ui.TextInput(
        label="Question",
        placeholder="What would you like to know?",
        style=discord.TextStyle.paragraph,
        max_length=600,
    )

    def __init__(self, video_id: str):
        super().__init__()
        self.video_id = video_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        cog = interaction.client.get_cog("MemeCommands")
        if not isinstance(cog, MemeCommands):
            await interaction.followup.send("Summary service is unavailable. Try again shortly.", ephemeral=True)
            return
        await cog.answer_video_question(interaction, self.video_id, str(self.question))


class AskSummaryQuestionButton(discord.ui.Button):
    def __init__(self, video_id: str):
        super().__init__(
            label="Ask a question",
            style=discord.ButtonStyle.secondary,
            emoji="💬",
            custom_id=f"summary-question:{video_id}",
            row=1,
        )
        self.video_id = video_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SummaryQuestionModal(self.video_id))


class SummaryAnswerView(discord.ui.View):
    def __init__(self, video_id: str):
        super().__init__(timeout=None)
        _add_video_action_items(self, video_id)
        self.add_item(AskSummaryQuestionButton(video_id))


class SummaryButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"summary:(?P<video_id>[A-Za-z0-9_-]{11})$",
):
    def __init__(self, video_id: str):
        super().__init__(discord.ui.Button(
            label="Summarize",
            style=discord.ButtonStyle.primary,
            emoji="✨",
            custom_id=f"summary:{video_id}",
        ))
        self.video_id = video_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["video_id"])

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        cog = interaction.client.get_cog("MemeCommands")
        if not isinstance(cog, MemeCommands):
            await interaction.followup.send("Summary service is unavailable. Try again shortly.", ephemeral=True)
            return
        await cog.send_video_summary(interaction, self.video_id)


class VideoActionsView(discord.ui.View):
    def __init__(self, video: dict):
        super().__init__(timeout=None)
        _add_video_action_items(self, video["video_id"], video["url"])


def _transcript_page_url(video_id: str) -> str:
    cache_url = urlsplit(CAPTION_CACHE_URL)
    return f"{cache_url.scheme}://{cache_url.netloc}/transcript/{video_id}"


def _add_video_action_items(
    view: discord.ui.View,
    video_id: str,
    video_url: Optional[str] = None,
) -> None:
    view.add_item(discord.ui.Button(
        label="Watch",
        style=discord.ButtonStyle.link,
        url=video_url or f"https://www.youtube.com/watch?v={video_id}",
        emoji="▶️",
    ))
    view.add_item(discord.ui.Button(
        label="Copy link",
        style=discord.ButtonStyle.secondary,
        custom_id=f"link:{video_id}",
        emoji="🔗",
    ))
    view.add_item(SummaryButton(video_id))
    view.add_item(discord.ui.Button(
        label="Transcript",
        style=discord.ButtonStyle.secondary,
        custom_id=f"chat:{video_id}",
        emoji="💬",
    ))
    view.add_item(discord.ui.Button(
        label="Copy transcript",
        style=discord.ButtonStyle.link,
        url=_transcript_page_url(video_id),
        emoji="📋",
    ))


class TranscriptLinkView(discord.ui.View):
    def __init__(self, video_id: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="Open & Copy",
            style=discord.ButtonStyle.link,
            url=_transcript_page_url(video_id),
            emoji="📋",
        ))
        self.add_item(discord.ui.Button(
            label="Watch video",
            style=discord.ButtonStyle.link,
            url=f"https://www.youtube.com/watch?v={video_id}",
        ))


class MemeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True

        super().__init__(
            command_prefix=DISCORD_PREFIX,
            intents=intents,
            help_command=None,
        )

        self.reddit_client = (
            RedditMemeFetcher()
            if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET
            else None
        )
        self.youtube_client = YouTubeFeedClient()
        self.transcript_client = YouTubeTranscriptClient()
        self.summary_client = GeminiSummaryClient(
            GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODEL
        )
        self.caption_cache = CaptionCacheClient(
            CAPTION_CACHE_URL,
            CAPTION_INGEST_SECRET or "",
        )
        self.subscription_store = SubscriptionStore(
            SUBSCRIPTIONS_FILE, seed_b64=SUBSCRIPTIONS_SEED_B64
        )
        self._shutdown_requested = False
        self._commands_synced = False

    async def setup_hook(self):
        self.add_dynamic_items(SummaryButton)
        await self.add_cog(MemeCommands(self))
        print(f"{f.CYAN}Bot commands and video watcher loaded")
        print(
            f"Loaded {len(self.subscription_store.subscriptions)} "
            "YouTube routes"
        )

    async def on_ready(self):
        print(f"📺 {f.GREEN}Discord YouTube Tracker is online!")
        if self.user:
            print(f"Bot ID: {self.user.id}")
        if not self._commands_synced:
            for guild in self.guilds:
                guild_object = discord.Object(id=guild.id)
                self.tree.copy_global_to(guild=guild_object)
                await self.tree.sync(guild=guild_object)
                print(f"Slash commands synced to {guild.name} ({guild.id})")
            self._commands_synced = True
        transcript_cog = self.get_cog("MemeCommands")
        if transcript_cog:
            await transcript_cog.ensure_transcript_channels()
            transcript_cog.start_caption_warmer()
        print(f"Prefix: {DISCORD_PREFIX}")
        print(f"{f.YELLOW}=" * 50)

    async def close(self):
        print("\n🔄 Shutting down bot...")

        if self.reddit_client:
            try:
                await self.reddit_client.close()
                print("Reddit client closed")
            except Exception as e:
                print(f"Error closing Reddit client: {e}")

        try:
            await self.youtube_client.close()
            print("YouTube client closed")
        except Exception as e:
            print(f"Error closing YouTube client: {e}")

        try:
            await self.transcript_client.close()
            print("YouTube transcript client closed")
        except Exception as e:
            print(f"Error closing YouTube transcript client: {e}")

        try:
            await self.summary_client.close()
            print("Gemini summary client closed")
        except Exception as e:
            print(f"Error closing Gemini summary client: {e}")

        try:
            await self.caption_cache.close()
            print("Caption cache client closed")
        except Exception as e:
            print(f"Error closing caption cache client: {e}")

        try:
            await super().close()
            print("Discord client closed")
        except Exception as e:
            print(f"Error closing Discord client: {e}")

        print(f"👋 {f.RED}Bot shutdown complete!")


class MemeCommands(commands.Cog):
    def __init__(self, bot: MemeBot):
        self.bot = bot
        self.reddit_client = bot.reddit_client
        self.youtube_client = bot.youtube_client
        self.transcript_client = bot.transcript_client
        self.summary_client = bot.summary_client
        self.caption_cache = bot.caption_cache
        self.subscription_store = bot.subscription_store
        self._poll_lock = asyncio.Lock()
        self._startup_seen_video_ids = {}
        self._startup_reconciled_routes = set()
        self._caption_tasks = set()
        self._caption_video_ids = set()
        self._warmed_video_ids = set()
        self._caption_warm_task = None

    async def cog_load(self):
        if LOCAL_FEED_POLLING:
            self.poll_youtube_channels.change_interval(minutes=YOUTUBE_POLL_MINUTES)
            self.poll_youtube_channels.start()

    def cog_unload(self):
        if self.poll_youtube_channels.is_running():
            self.poll_youtube_channels.cancel()
        if self._caption_warm_task:
            self._caption_warm_task.cancel()
        for task in self._caption_tasks:
            task.cancel()

    async def _fetch_and_cache_transcript(
        self, video_id: str, cache_required: bool = True
    ) -> TranscriptBundle:
        bundle = await self.transcript_client.fetch(video_id)
        if not cache_required:
            task = asyncio.create_task(self.caption_cache.store(bundle))
            task.add_done_callback(
                lambda completed: print(
                    f"Transcript cache skipped for {video_id}: {completed.exception()}"
                ) if not completed.cancelled() and completed.exception() else None
            )
            return bundle
        try:
            await self.caption_cache.store(bundle)
        except Exception as error:
            if cache_required:
                raise
            print(f"Transcript delivered but cache failed for {video_id}: {error}")
        return bundle

    async def _cache_feed_video(self, video_id: str) -> None:
        try:
            try:
                if await self.caption_cache.exists(video_id):
                    self._warmed_video_ids.add(video_id)
                    return
            except Exception as error:
                # Cache status is an optimization. Local extraction still gives
                # the cloud its strongest fallback when the status probe fails.
                print(f"Could not check caption cache for {video_id}: {error}")
            await self._fetch_and_cache_transcript(video_id)
            self._warmed_video_ids.add(video_id)
            print(f"Caption saved for {video_id}")
        except Exception as error:
            print(f"Could not save captions for {video_id}: {error}")
        finally:
            self._caption_video_ids.discard(video_id)

    def _schedule_caption_cache(self, video_id: str) -> None:
        if video_id in self._warmed_video_ids or video_id in self._caption_video_ids:
            return
        self._caption_video_ids.add(video_id)
        task = asyncio.create_task(self._cache_feed_video(video_id))
        self._caption_tasks.add(task)
        task.add_done_callback(self._caption_tasks.discard)

    def start_caption_warmer(self) -> None:
        if self._caption_warm_task and not self._caption_warm_task.done():
            return
        self._caption_warm_task = asyncio.create_task(self._caption_warm_loop())

    async def _caption_warm_loop(self) -> None:
        while True:
            try:
                await self._warm_recent_captions()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(f"Caption backfill failed: {error}")
            await asyncio.sleep(6 * 60 * 60)

    async def _warm_recent_captions(self) -> None:
        video_ids = []
        seen = set()
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.text_channels, name="everything")
            if not channel:
                continue
            try:
                # One archive channel contains every upload. A deep pass avoids
                # old creator cards failing later when Cloudflare is challenged.
                async for message in channel.history(limit=1000):
                    for video_id in self._video_ids_from_message(message):
                        if video_id not in seen and video_id not in self._warmed_video_ids:
                            seen.add(video_id)
                            video_ids.append(video_id)
            except discord.HTTPException as error:
                print(f"Could not read recent feed captions: {error}")
        queue = asyncio.Queue()
        for video_id in video_ids:
            queue.put_nowait(video_id)

        async def worker() -> None:
            while not queue.empty():
                try:
                    video_id = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                if video_id not in self._caption_video_ids:
                    self._caption_video_ids.add(video_id)
                    await self._cache_feed_video(video_id)
                queue.task_done()
                await asyncio.sleep(0.2)

        await asyncio.gather(*(worker() for _ in range(min(3, len(video_ids)))))

    async def ensure_transcript_channels(self) -> None:
        for guild in self.bot.guilds:
            try:
                existing = discord.utils.get(
                    guild.text_channels, name=TRANSCRIPT_CHANNEL_NAME
                )
                if existing:
                    if existing.topic != TRANSCRIPT_CHANNEL_TOPIC:
                        await existing.edit(
                            topic=TRANSCRIPT_CHANNEL_TOPIC,
                            reason="Repair YouTube transcript intake topic",
                        )
                    continue
                category = discord.utils.get(guild.categories, name="AI Video Feeds")
                channel = await guild.create_text_channel(
                    TRANSCRIPT_CHANNEL_NAME,
                    category=category,
                    topic=TRANSCRIPT_CHANNEL_TOPIC,
                    reason="YouTube transcript intake",
                )
                await channel.send(
                    "Paste any YouTube video or Shorts URL here. "
                    "I will return a readable transcript with an **Open & Copy** button."
                )
            except discord.Forbidden:
                print(
                    f"Cannot create or repair #{TRANSCRIPT_CHANNEL_NAME} in "
                    f"{guild.name}: grant Manage Channels permission."
                )
            except discord.HTTPException as exc:
                print(
                    f"Could not prepare #{TRANSCRIPT_CHANNEL_NAME} in "
                    f"{guild.name}: {exc}"
                )

    async def _send_transcript(self, destination, video_id: str, reference=None) -> None:
        bundle = await self._fetch_and_cache_transcript(
            video_id, cache_required=True
        )
        transcript = bundle.plain_text.strip()
        if len(transcript) > 1500:
            clipped = transcript[:1500]
            boundary = max(clipped.rfind("\n"), clipped.rfind(" "))
            transcript = clipped[:boundary if boundary > 1200 else len(clipped)].rstrip() + "…"
        await destination.send(
            transcript + "\n\nOpen the full plain-text transcript below to copy it in one tap.",
            view=TranscriptLinkView(video_id),
            reference=reference,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _video_summary(self, video_id: str) -> str:
        try:
            bundle = await self._fetch_and_cache_transcript(
                video_id, cache_required=False
            )
        except Exception as transcript_error:
            # The configured Gemini key can generate from transcript text but is
            # not authorized for direct YouTube-video access. Do not leave a
            # Discord request hanging for its 90-second timeout.
            raise RuntimeError(
                "YouTube did not provide an accessible transcript for this video "
                f"({transcript_error}). Try again when captions are available."
            ) from transcript_error
        return await self.summary_client.summarize(bundle)

    async def _send_summary_cards(
        self, destination, video_id: str, summary: str, reference=None
    ) -> None:
        cards: list[discord.Embed] = []
        for section, body in _summary_sections(summary):
            linked_body = _link_timestamps(body, video_id)
            for index, chunk in enumerate(split_discord_messages(linked_body, 3900)):
                title = section if index == 0 else f"{section} — continued"
                embed = discord.Embed(
                    title=title[:256],
                    description=chunk[:4096],
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    colour=discord.Colour.blurple(),
                )
                embed.set_footer(text="Video learning brief • timestamps open YouTube")
                cards.append(embed)

        for index, card in enumerate(cards):
            await destination.send(
                embed=card,
                reference=reference if index == 0 else None,
                view=SummaryAnswerView(video_id) if index == len(cards) - 1 else None,
                allowed_mentions=discord.AllowedMentions.none(),
            )

    @commands.Cog.listener()
    async def on_message(self, message) -> None:
        if message.author.bot:
            category_name = getattr(
                getattr(message.channel, "category", None), "name", ""
            ).casefold()
            if (
                getattr(message.author, "id", None)
                == getattr(self.bot.user, "id", None)
                and category_name in {"ai video feeds", "ai labs & platforms"}
            ):
                for video_id in self._video_ids_from_message(message):
                    self._schedule_caption_cache(video_id)
            return
        channel_name = getattr(message.channel, "name", "").casefold()
        if channel_name == SUMMARY_CHANNEL_NAME:
            await self._process_summary_links(message)
            return
        if channel_name != TRANSCRIPT_CHANNEL_NAME:
            return
        video_ids = list(dict.fromkeys(YOUTUBE_VIDEO_ID_PATTERN.findall(message.content or "")))
        if not video_ids:
            await message.reply(
                "Paste a valid YouTube video, Shorts, or youtu.be URL.",
                mention_author=False,
            )
            return
        async with message.channel.typing():
            for video_id in video_ids[:3]:
                try:
                    await self._send_transcript(
                        message.channel,
                        video_id,
                        reference=message.to_reference(fail_if_not_exists=False),
                    )
                except Exception as error:
                    await message.reply(
                        f"Could not get that transcript: {error}",
                        mention_author=False,
                    )

    async def _process_summary_links(self, message) -> None:
        video_ids = list(dict.fromkeys(YOUTUBE_VIDEO_ID_PATTERN.findall(message.content or "")))
        if not video_ids:
            return
        async with message.channel.typing():
            for video_id in video_ids[:3]:
                try:
                    summary = await self._video_summary(video_id)
                    await self._send_summary_cards(
                        message.channel,
                        video_id,
                        summary,
                        reference=message.to_reference(fail_if_not_exists=False),
                    )
                except Exception as error:
                    await message.reply(f"Could not summarize this video: {error}", mention_author=False)

    @commands.hybrid_command(name="transcript")
    async def transcript(self, ctx, url: str):
        """Open a mobile-friendly transcript for a YouTube URL."""
        match = YOUTUBE_VIDEO_ID_PATTERN.search(url)
        if not match:
            await ctx.send("Send a valid YouTube video, Shorts, or youtu.be URL.")
            return
        await ctx.defer()
        try:
            await self._send_transcript(ctx.channel, match.group(1))
        except Exception as error:
            await ctx.send(f"Could not get that transcript: {error}")

    async def _require_reddit(self, ctx) -> bool:
        if self.reddit_client:
            return True
        await ctx.send("Reddit meme commands are disabled. YouTube watching is active.")
        return False

    @commands.command(name="meme", aliases=["m"])
    async def fetch_meme(self, ctx, *, keyword: Optional[str] = None):
        if not await self._require_reddit(ctx):
            return
        await ctx.typing()

        try:
            if keyword:
                memes = await self.reddit_client.fetch_memes_by_keyword(
                    keyword, limit=MAX_MEMES_PER_REQUEST
                )
                title = f"🎭 Memes for '{keyword}'"
            else:
                memes = await self.reddit_client.get_trending_memes(
                    limit=MAX_MEMES_PER_REQUEST
                )
                title = "🔥 Trending Memes"

            if not memes:
                embed = discord.Embed(
                    title="❌ No memes found!",
                    description="Try a different keyword or check back later.",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                return

            for index, meme in enumerate(memes, 1):
                embed = self.create_meme_embed(meme, title, index, len(memes))
                await ctx.send(embed=embed)
                await asyncio.sleep(1)
        except Exception as e:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Error fetching memes",
                    description=f"An error occurred: {e}",
                    color=discord.Color.red(),
                )
            )

    @commands.command(name="random", aliases=["r"])
    async def random_memes(self, ctx, count: int = 3):
        if not await self._require_reddit(ctx):
            return
        count = max(1, min(count, 10))
        await ctx.typing()

        try:
            memes = await self.reddit_client.fetch_random_memes(limit=count)
            if not memes:
                await ctx.send(
                    embed=discord.Embed(
                        title="❌ No memes found!",
                        description="Try again later.",
                        color=discord.Color.red(),
                    )
                )
                return

            for index, meme in enumerate(memes, 1):
                embed = self.create_meme_embed(
                    meme, "🎲 Random Memes", index, len(memes)
                )
                await ctx.send(embed=embed)
                await asyncio.sleep(1)
        except Exception as e:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Error fetching random memes",
                    description=f"An error occurred: {e}",
                    color=discord.Color.red(),
                )
            )

    @commands.command(name="search", aliases=["s"])
    async def search_memes(
        self,
        ctx,
        keyword: str,
        subreddit: Optional[str] = None,
        count: int = 3,
    ):
        if not await self._require_reddit(ctx):
            return
        count = max(1, min(count, 10))
        keyword = keyword.strip() if keyword else ""
        subreddit = subreddit.strip() if subreddit else None
        await ctx.typing()

        try:
            subreddits = [subreddit] if subreddit else None
            memes = await self.reddit_client.fetch_memes_by_keyword(
                keyword, subreddits, limit=count
            )
            if not memes:
                await ctx.send(
                    embed=discord.Embed(
                        title="❌ No memes found!",
                        description=(
                            f"No memes found for '{keyword}' in "
                            f"{subreddit or 'popular subreddits'}"
                        ),
                        color=discord.Color.red(),
                    )
                )
                return

            title = f"🔍 Search results for '{keyword}'"
            if subreddit:
                title += f" in r/{subreddit}"
            for index, meme in enumerate(memes, 1):
                embed = self.create_meme_embed(meme, title, index, len(memes))
                await ctx.send(embed=embed)
                await asyncio.sleep(1)
        except Exception as e:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Error searching memes",
                    description=f"An error occurred: {e}",
                    color=discord.Color.red(),
                )
            )

    @commands.hybrid_command(name="help", aliases=["h"])
    async def help_command(self, ctx):
        embed = discord.Embed(
            title="📺 Discord YouTube Tracker Help",
            description="Watches YouTube channels and posts new uploads.",
            color=discord.Color.blue(),
        )
        commands_info = [
            ("!addchannel <YouTube URL>", "Watch a YouTube channel here"),
            ("!removechannel <YouTube URL>", "Stop watching it here"),
            ("!channels", "List YouTube channels watched here"),
            ("!checkchannels", "Check for new videos now"),
            ("!meme [keyword]", "Fetch memes by keyword or get trending memes"),
            ("!random [count]", "Get random memes (default: 3, max: 10)"),
            ("!search <keyword> [subreddit] [count]", "Search memes"),
            ("!help", "Show this help message"),
        ]
        for command, description in commands_info:
            embed.add_field(name=command, value=description, inline=False)
        embed.add_field(
            name="📝 Examples",
            value="```\n/addchannel https://youtube.com/@OpenAI\n/channels\n/checkchannels```",
            inline=False,
        )
        embed.set_footer(text="YouTube feeds checked every 5 minutes")
        await ctx.send(embed=embed)

    def _can_manage(self, ctx) -> bool:
        permissions = getattr(getattr(ctx, "author", None), "guild_permissions", None)
        return bool(permissions and permissions.manage_guild)

    async def _ensure_feed_destinations(self, guild, creator_name: str):
        category = next(
            (
                item
                for item in guild.categories
                if item.name.casefold() == "ai video feeds"
            ),
            None,
        )
        if category is None:
            category = await guild.create_category(
                "AI Video Feeds", reason="YouTube feed setup"
            )

        everything = next(
            (
                item
                for item in category.text_channels
                if item.name.casefold() == "everything"
            ),
            None,
        )
        if everything is None:
            everything = await category.create_text_channel(
                "everything",
                topic="Every new upload from all watched creators.",
                reason="YouTube feed setup",
            )

        slug = re.sub(r"[^a-z0-9]+", "-", creator_name.casefold()).strip("-")
        slug = (slug or "youtube-creator")[:90]
        creator_channel = next(
            (
                item
                for item in category.text_channels
                if item.name.casefold() == slug.casefold()
            ),
            None,
        )
        if creator_channel is None:
            creator_channel = await category.create_text_channel(
                slug,
                topic=f"New videos from {creator_name}.",
                reason="YouTube creator feed added",
            )
        return everything, creator_channel

    @commands.hybrid_command(name="addchannel", aliases=["addyt"])
    async def add_youtube_channel(self, ctx, *, channel: str):
        if not self._can_manage(ctx):
            await ctx.send("You need Manage Server permission to add channels.")
            return
        if ctx.guild is None:
            await ctx.send("Use this command inside a Discord server.")
            return
        await ctx.typing()
        try:
            resolved = await self.youtube_client.resolve_channel(channel)
            videos = await self.youtube_client.fetch_videos(
                resolved["channel_id"], limit=1
            )
            latest_id = videos[0]["video_id"] if videos else None
            destinations = await self._ensure_feed_destinations(
                ctx.guild, resolved["channel_name"]
            )
            added = 0
            for destination in destinations:
                subscription = VideoSubscription(
                    youtube_channel_id=resolved["channel_id"],
                    youtube_channel_name=resolved["channel_name"],
                    discord_channel_id=destination.id,
                    last_video_id=latest_id,
                )
                added += int(self.subscription_store.add(subscription))

            embed = discord.Embed(
                title="YouTube feed ready" if added else "YouTube feed already active",
                description=f"**{resolved['channel_name']}** is routed correctly.",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Destinations",
                value=" + ".join(destination.mention for destination in destinations),
                inline=False,
            )
            if latest_id:
                embed.set_thumbnail(
                    url=f"https://i.ytimg.com/vi/{latest_id}/hqdefault.jpg"
                )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Could not add that YouTube channel: {e}")

    @commands.hybrid_command(name="removechannel", aliases=["removeyt"])
    async def remove_youtube_channel(self, ctx, *, channel: str):
        if not self._can_manage(ctx):
            await ctx.send("You need Manage Server permission to remove channels.")
            return
        await ctx.typing()
        try:
            resolved = await self.youtube_client.resolve_channel(channel)
            removed = self.subscription_store.remove(
                resolved["channel_id"], ctx.channel.id
            )
            if removed:
                await ctx.send(f"Stopped watching **{resolved['channel_name']}** here.")
            else:
                await ctx.send("That YouTube channel is not watched here.")
        except Exception as e:
            await ctx.send(f"Could not remove that YouTube channel: {e}")

    @commands.hybrid_command(name="channels", aliases=["ytchannels"])
    async def list_youtube_channels(self, ctx):
        subscriptions = [
            item
            for item in self.subscription_store.subscriptions
            if item.discord_channel_id == ctx.channel.id
        ]
        if not subscriptions:
            await ctx.send("No YouTube channels are watched here yet.")
            return
        lines = [
            f"• **{item.youtube_channel_name}** — "
            f"https://youtube.com/channel/{item.youtube_channel_id}"
            for item in subscriptions
        ]
        await ctx.send("Watched YouTube channels:\n" + "\n".join(lines))

    @commands.hybrid_command(name="checkchannels", aliases=["checkyt"])
    async def check_youtube_channels(self, ctx):
        if not self._can_manage(ctx):
            await ctx.send("You need Manage Server permission to run a check.")
            return
        posted = await self._poll_subscriptions(discord_channel_id=ctx.channel.id)
        await ctx.send(f"Check complete. Posted {posted} new video(s).")

    def create_video_embed(
        self, video: dict, subscription: VideoSubscription
    ) -> discord.Embed:
        channel_url = (
            f"https://www.youtube.com/channel/{subscription.youtube_channel_id}"
        )
        published = video.get("published", "")
        timestamp = None
        if published:
            try:
                timestamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                timestamp = None

        embed = discord.Embed(
            title=video["title"][:256],
            url=video["url"],
            description="New YouTube upload",
            color=discord.Color.from_rgb(255, 0, 0),
            timestamp=timestamp,
        )
        embed.set_author(
            name=subscription.youtube_channel_name,
            url=channel_url,
        )
        embed.set_image(
            url=video.get("thumbnail_url")
            or f"https://i.ytimg.com/vi/{video['video_id']}/hqdefault.jpg"
        )
        embed.set_footer(text="YouTube • New video")
        return embed

    def create_video_view(self, video: dict) -> discord.ui.View:
        return VideoActionsView(video)

    async def send_video_summary(
        self, interaction: discord.Interaction, video_id: str
    ) -> None:
        try:
            summary = await self._video_summary(video_id)
            if interaction.guild is None:
                raise RuntimeError("Use this button inside a Discord server.")
            channel = discord.utils.get(interaction.guild.text_channels, name=SUMMARY_CHANNEL_NAME)
            if channel is None:
                raise RuntimeError("Could not find #summary.")
            await self._send_summary_cards(channel, video_id, summary)
            await interaction.followup.send(
                f"Deep summary posted in {channel.mention}. Ask questions there.", ephemeral=True,
            )
        except Exception as error:
            await interaction.followup.send(
                f"Could not summarize this video: {error}", ephemeral=True
            )

    async def answer_video_question(
        self, interaction: discord.Interaction, video_id: str, question: str
    ) -> None:
        try:
            try:
                bundle = await self._fetch_and_cache_transcript(
                    video_id, cache_required=False
                )
                answer = await self.summary_client.answer(bundle, question)
            except Exception as transcript_error:
                print(f"Caption Q&A fallback for {video_id}: {transcript_error}")
                answer = await self.summary_client.answer_youtube_url(video_id, question)
            channel = interaction.channel
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                raise RuntimeError("Ask questions from #summary.")
            chunks = split_discord_messages(answer)
            for index, chunk in enumerate(chunks):
                embed = discord.Embed(
                    title="Answer" if index == 0 else "Answer — continued",
                    description=_link_timestamps(chunk, video_id)[:4096],
                    colour=discord.Colour.green(),
                )
                await channel.send(
                    embed=embed,
                    view=SummaryAnswerView(video_id) if index == len(chunks) - 1 else None,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            await interaction.followup.send("Answer posted here.", ephemeral=True)
        except Exception as error:
            await interaction.followup.send(
                f"Could not answer that question: {error}", ephemeral=True
            )

    @staticmethod
    def _video_ids_from_message(message) -> set[str]:
        text = getattr(message, "content", "") or ""
        for embed in getattr(message, "embeds", ()):
            text += f"\n{getattr(embed, 'url', '') or ''}"
        return set(YOUTUBE_VIDEO_ID_PATTERN.findall(text))

    async def _load_recent_posted_video_ids(self) -> None:
        channel_ids = {
            item.discord_channel_id
            for item in self.subscription_store.subscriptions
        }
        for channel_id in channel_ids:
            try:
                target = self.bot.get_channel(channel_id)
                if target is None:
                    target = await self.bot.fetch_channel(channel_id)
                limit = (
                    1000
                    if getattr(target, "name", "").casefold() == "everything"
                    else 100
                )
                seen = set()
                async for message in target.history(limit=limit):
                    seen.update(self._video_ids_from_message(message))
                self._startup_seen_video_ids[channel_id] = seen
            except Exception as e:
                print(f"Could not read Discord history for a feed channel: {e}")

        seen_count = sum(len(ids) for ids in self._startup_seen_video_ids.values())
        print(f"Recovered {seen_count} posted video checkpoint(s) from Discord")

    async def _poll_subscriptions(
        self, discord_channel_id: Optional[int] = None
    ) -> int:
        if self._poll_lock.locked():
            return 0
        posted = 0
        async with self._poll_lock:
            subscriptions = list(self.subscription_store.subscriptions)
            if discord_channel_id is not None:
                subscriptions = [
                    item
                    for item in subscriptions
                    if item.discord_channel_id == discord_channel_id
                ]

            grouped_subscriptions = {}
            for subscription in subscriptions:
                grouped_subscriptions.setdefault(
                    subscription.youtube_channel_id, []
                ).append(subscription)

            for youtube_channel_id, routes in grouped_subscriptions.items():
                try:
                    videos = await self.youtube_client.fetch_videos(
                        youtube_channel_id, limit=5
                    )
                    if not videos:
                        continue
                    changed = False
                    for subscription in routes:
                        route_key = (
                            subscription.youtube_channel_id,
                            subscription.discord_channel_id,
                        )
                        if route_key not in self._startup_reconciled_routes:
                            seen = self._startup_seen_video_ids.get(
                                subscription.discord_channel_id, set()
                            )
                            current_index = next(
                                (
                                    index
                                    for index, video in enumerate(videos)
                                    if video["video_id"]
                                    == subscription.last_video_id
                                ),
                                len(videos),
                            )
                            seen_index = next(
                                (
                                    index
                                    for index, video in enumerate(videos)
                                    if video["video_id"] in seen
                                ),
                                None,
                            )
                            if seen_index is not None and seen_index < current_index:
                                subscription.last_video_id = videos[seen_index][
                                    "video_id"
                                ]
                                changed = True
                            self._startup_reconciled_routes.add(route_key)

                        if not subscription.last_video_id:
                            subscription.last_video_id = videos[0]["video_id"]
                            changed = True
                            continue

                        new_videos = []
                        for video in videos:
                            if video["video_id"] == subscription.last_video_id:
                                break
                            new_videos.append(video)
                        if not new_videos:
                            continue

                        target = self.bot.get_channel(
                            subscription.discord_channel_id
                        )
                        if target is None:
                            target = await self.bot.fetch_channel(
                                subscription.discord_channel_id
                            )
                        for video in reversed(new_videos):
                            await target.send(
                                embed=self.create_video_embed(video, subscription),
                                view=self.create_video_view(video),
                                allowed_mentions=discord.AllowedMentions.none(),
                            )
                            posted += 1
                        subscription.last_video_id = videos[0]["video_id"]
                        changed = True
                    if changed:
                        self.subscription_store.save()
                except Exception as e:
                    print(
                        f"YouTube poll error for "
                        f"{youtube_channel_id}: {e}"
                    )
        return posted

    @tasks.loop(minutes=5)
    async def poll_youtube_channels(self):
        posted = await self._poll_subscriptions()
        print(f"YouTube poll complete: {posted} new video(s)")

    @poll_youtube_channels.before_loop
    async def before_youtube_poll(self):
        await self.bot.wait_until_ready()
        await self._load_recent_posted_video_ids()

    def create_meme_embed(
        self, meme: dict, title: str, current: int, total: int
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"{title} ({current}/{total})",
            description=meme["title"],
            color=discord.Color.orange(),
            url=meme["permalink"],
        )
        embed.set_image(url=meme["url"])
        embed.add_field(
            name="Subreddit", value=f"r/{meme['subreddit']}", inline=True
        )
        embed.add_field(name="Score", value=f"⬆️ {meme['score']}", inline=True)
        embed.add_field(name="Author", value=f"u/{meme['author']}", inline=True)
        if "sort_method" in meme:
            sort_display = meme["sort_method"].title()
            if meme["sort_method"] == "top" and "time_filter" in meme:
                sort_display += f" ({meme['time_filter']})"
            embed.add_field(name="Sort", value=sort_display, inline=True)
        if "search_method" in meme:
            embed.add_field(
                name="Search", value=meme["search_method"].title(), inline=True
            )
        embed.set_footer(text="Click the title to view on Reddit")
        return embed


def signal_handler(signum, frame):
    print(f"\n🛑 Received signal {signum}. Shutting down gracefully...")
    sys.exit(0)


async def main():
    if not DISCORD_TOKEN:
        print("❌ Error: DISCORD_TOKEN not found in environment variables!")
        print("Please create a .env file with your Discord bot token.")
        return

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    bot = MemeBot()
    try:
        await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Shutting down...")
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
