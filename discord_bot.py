import asyncio
import re
import signal
import sys
from datetime import datetime
from typing import Optional

import discord
from colorama import Fore as f
from colorama import init
from discord.ext import commands, tasks

from config import (
    DISCORD_PREFIX,
    DISCORD_TOKEN,
    MAX_MEMES_PER_REQUEST,
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    SUBSCRIPTIONS_FILE,
    YOUTUBE_POLL_MINUTES,
)
from reddit_client import RedditMemeFetcher
from youtube_client import SubscriptionStore, VideoSubscription, YouTubeFeedClient

init(autoreset=True)


class MemeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False
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
        self.subscription_store = SubscriptionStore(SUBSCRIPTIONS_FILE)
        self._shutdown_requested = False
        self._commands_synced = False

    async def setup_hook(self):
        await self.add_cog(MemeCommands(self))
        print(f"{f.CYAN}Bot commands and video watcher loaded")

    async def on_ready(self):
        print(f"🎭 {f.GREEN}Meme Fetcher Bot / Video Watcher is online!")
        if self.user:
            print(f"Bot ID: {self.user.id}")
        if not self._commands_synced:
            for guild in self.guilds:
                guild_object = discord.Object(id=guild.id)
                self.tree.copy_global_to(guild=guild_object)
                await self.tree.sync(guild=guild_object)
                print(f"Slash commands synced to {guild.name} ({guild.id})")
            self._commands_synced = True
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
        self.subscription_store = bot.subscription_store
        self._poll_lock = asyncio.Lock()

    async def cog_load(self):
        self.poll_youtube_channels.change_interval(minutes=YOUTUBE_POLL_MINUTES)
        self.poll_youtube_channels.start()

    def cog_unload(self):
        self.poll_youtube_channels.cancel()

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
            title="🎭 Meme Fetcher Bot Help",
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
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                label="Watch on YouTube",
                style=discord.ButtonStyle.link,
                url=video["url"],
                emoji="▶️",
            )
        )
        return view

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
        await self._poll_subscriptions()

    @poll_youtube_channels.before_loop
    async def before_youtube_poll(self):
        await self.bot.wait_until_ready()

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
