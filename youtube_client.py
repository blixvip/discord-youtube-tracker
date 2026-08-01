import html
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import aiohttp


CHANNEL_ID_RE = re.compile(r"UC[A-Za-z0-9_-]{22}")


@dataclass
class VideoSubscription:
    youtube_channel_id: str
    youtube_channel_name: str
    discord_channel_id: int
    last_video_id: Optional[str] = None


class SubscriptionStore:
    """Small JSON store for YouTube-to-Discord subscriptions."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.subscriptions: List[VideoSubscription] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.subscriptions = [
                VideoSubscription(**item) for item in payload.get("subscriptions", [])
            ]
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self.subscriptions = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {"subscriptions": [asdict(item) for item in self.subscriptions]}
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temp_path, self.path)

    def add(self, subscription: VideoSubscription) -> bool:
        duplicate = any(
            item.youtube_channel_id == subscription.youtube_channel_id
            and item.discord_channel_id == subscription.discord_channel_id
            for item in self.subscriptions
        )
        if duplicate:
            return False
        self.subscriptions.append(subscription)
        self.save()
        return True

    def remove(self, youtube_channel_id: str, discord_channel_id: int) -> bool:
        before = len(self.subscriptions)
        self.subscriptions = [
            item
            for item in self.subscriptions
            if not (
                item.youtube_channel_id == youtube_channel_id
                and item.discord_channel_id == discord_channel_id
            )
        ]
        if len(self.subscriptions) == before:
            return False
        self.save()
        return True


class YouTubeFeedClient:
    """Resolve YouTube channels and read their public Atom feeds."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": "DiscordVideoWatcher/1.0"},
            )
        return self._session

    async def _request_text(self, url: str) -> str:
        session = await self._get_session()
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.text()

    async def resolve_channel(self, value: str) -> Dict[str, str]:
        value = value.strip().strip("<>")
        direct_match = CHANNEL_ID_RE.fullmatch(value)
        if direct_match:
            channel_id = direct_match.group(0)
        else:
            if value.startswith("@"):
                value = f"https://www.youtube.com/{value}"
            elif not urlparse(value).scheme:
                value = f"https://www.youtube.com/{value.lstrip('/')}"

            path_match = re.search(r"/channel/(UC[A-Za-z0-9_-]{22})", value)
            if path_match:
                channel_id = path_match.group(1)
            else:
                page = await self._request_text(value)
                patterns = [
                    r'"externalId":"(UC[A-Za-z0-9_-]{22})"',
                    r'<link rel="canonical" href="https?://(?:www\.)?youtube\.com/channel/(UC[A-Za-z0-9_-]{22})"',
                    r'<meta itemprop="channelId" content="(UC[A-Za-z0-9_-]{22})"',
                ]
                channel_id = None
                for pattern in patterns:
                    match = re.search(pattern, page)
                    if match:
                        channel_id = match.group(1)
                        break
                if not channel_id:
                    raise ValueError("Could not find a YouTube channel ID at that address")

        videos = await self.fetch_videos(channel_id, limit=1)
        name = videos[0]["channel_title"] if videos else channel_id
        return {"channel_id": channel_id, "channel_name": name}

    async def fetch_videos(self, channel_id: str, limit: int = 10) -> List[Dict[str, str]]:
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        xml_text = await self._request_text(feed_url)
        root = ET.fromstring(xml_text)
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
            "media": "http://search.yahoo.com/mrss/",
        }
        channel_title = root.findtext("atom:title", default=channel_id, namespaces=namespaces)
        videos: List[Dict[str, str]] = []
        for entry in root.findall("atom:entry", namespaces)[:limit]:
            video_id = entry.findtext("yt:videoId", default="", namespaces=namespaces)
            if not video_id:
                continue
            title = entry.findtext("atom:title", default="Untitled", namespaces=namespaces)
            published = entry.findtext("atom:published", default="", namespaces=namespaces)
            thumbnail = entry.find("media:group/media:thumbnail", namespaces)
            thumbnail_url = (
                thumbnail.get("url")
                if thumbnail is not None and thumbnail.get("url")
                else f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            )
            videos.append(
                {
                    "video_id": video_id,
                    "title": html.unescape(title),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "published": published,
                    "channel_title": html.unescape(channel_title),
                    "thumbnail_url": thumbnail_url,
                }
            )
        return videos

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
