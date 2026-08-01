from unittest.mock import AsyncMock

import pytest

from youtube_client import SubscriptionStore, VideoSubscription, YouTubeFeedClient


SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Example Channel</title>
  <entry>
    <yt:videoId>video123</yt:videoId>
    <title>New &amp; Useful Video</title>
    <published>2026-07-31T12:00:00+00:00</published>
    <media:group><media:thumbnail url="https://img.example/video123.jpg" /></media:group>
  </entry>
</feed>
"""


@pytest.mark.asyncio
async def test_fetch_videos_parses_feed():
    client = YouTubeFeedClient()
    client._request_text = AsyncMock(return_value=SAMPLE_FEED)

    videos = await client.fetch_videos("UC1234567890123456789012")

    assert videos == [
        {
            "video_id": "video123",
            "title": "New & Useful Video",
            "url": "https://www.youtube.com/watch?v=video123",
            "published": "2026-07-31T12:00:00+00:00",
            "channel_title": "Example Channel",
            "thumbnail_url": "https://img.example/video123.jpg",
        }
    ]


@pytest.mark.asyncio
async def test_resolve_direct_channel_id():
    client = YouTubeFeedClient()
    client.fetch_videos = AsyncMock(
        return_value=[{"channel_title": "Example Channel"}]
    )

    result = await client.resolve_channel("UC1234567890123456789012")

    assert result == {
        "channel_id": "UC1234567890123456789012",
        "channel_name": "Example Channel",
    }


@pytest.mark.asyncio
async def test_resolve_handle_prefers_page_owner_id():
    client = YouTubeFeedClient()
    client._request_text = AsyncMock(
        return_value='related UCaaaaaaaaaaaaaaaaaaaaaa "externalId":"UC1234567890123456789012"'
    )
    client.fetch_videos = AsyncMock(
        return_value=[{"channel_title": "Example Channel"}]
    )

    result = await client.resolve_channel("https://youtube.com/@example")

    assert result["channel_id"] == "UC1234567890123456789012"


def test_subscription_store_persists_and_deduplicates(tmp_path):
    path = tmp_path / "subscriptions.json"
    store = SubscriptionStore(str(path))
    subscription = VideoSubscription(
        youtube_channel_id="UC1234567890123456789012",
        youtube_channel_name="Example Channel",
        discord_channel_id=42,
        last_video_id="video123",
    )

    assert store.add(subscription) is True
    assert store.add(subscription) is False

    reloaded = SubscriptionStore(str(path))
    assert reloaded.subscriptions == [subscription]
    assert reloaded.remove(subscription.youtube_channel_id, 42) is True
    assert reloaded.remove(subscription.youtube_channel_id, 42) is False
