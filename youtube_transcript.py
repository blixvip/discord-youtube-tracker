import asyncio
import html
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp


ANDROID_PLAYER_URL = "https://www.youtube.com/youtubei/v1/player"
ANDROID_USER_AGENT = "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip"
WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class TranscriptFailureReason(str, Enum):
    WAITING_FOR_CAPTIONS = "waiting_for_captions"
    CAPTIONS_DISABLED = "captions_disabled"
    PRIVATE_OR_DELETED = "private_or_deleted"
    RESTRICTED = "restricted"
    REQUEST_BLOCKED = "request_blocked"
    NETWORK = "network"
    MALFORMED = "malformed"
    UNKNOWN = "unknown"


class TranscriptProviderError(RuntimeError):
    def __init__(self, reason: TranscriptFailureReason, message: str, retryable: bool):
        super().__init__(message)
        self.reason = reason
        self.retryable = retryable


class TranscriptProvider(Protocol):
    provider_name: str

    def supports(self, video_id: str) -> bool: ...

    async def fetch(
        self, video_id: str, preferred_languages: Sequence[str] = ("en",)
    ) -> "TranscriptBundle": ...


@dataclass
class TranscriptCue:
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class TranscriptBundle:
    video_id: str
    title: str
    channel_name: str
    language: str
    plain_text: str
    srt_text: str
    segments: List[TranscriptCue] = field(default_factory=list)
    provider: str = "youtube-player"
    source_type: str = "creator_captions"
    is_auto_generated: bool = False


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value).replace("\u200b", "")).strip()


def extract_youtube_player_response(source: str) -> Optional[Dict[str, Any]]:
    """Extract Watch Better's balanced ytInitialPlayerResponse bootstrap JSON."""
    key_index = source.find("ytInitialPlayerResponse")
    if key_index < 0:
        return None
    start = source.find("{", key_index)
    if start < 0:
        return None
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(source)):
        character = source[index]
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            continue
        if character == '"':
            quoted = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                try:
                    value = json.loads(source[start:index + 1])
                except json.JSONDecodeError:
                    return None
                return value if isinstance(value, dict) else None
    return None


def parse_json3_captions(payload: Any) -> List[TranscriptCue]:
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        return []
    cues = []
    for event in payload["events"]:
        if not isinstance(event, dict) or not isinstance(event.get("segs"), list):
            continue
        try:
            start_ms = float(event["tStartMs"])
            duration_ms = float(event["dDurationMs"])
        except (KeyError, TypeError, ValueError):
            continue
        text = _clean_text("".join(
            segment.get("utf8", "")
            for segment in event["segs"]
            if isinstance(segment, dict)
        ))
        if text:
            cues.append(TranscriptCue(
                start=start_ms / 1000,
                end=(start_ms + max(1, duration_ms)) / 1000,
                text=text,
            ))
    return _merge_cues(cues)


def _merge_cues(cues: List[TranscriptCue]) -> List[TranscriptCue]:
    output: List[TranscriptCue] = []
    for cue in sorted(cues, key=lambda item: item.start):
        if cue.end <= cue.start or cue.start < 0 or not cue.text:
            continue
        if output and cue.text == output[-1].text and abs(cue.start - output[-1].start) < 0.1:
            continue
        previous = output[-1] if output else None
        separated = previous is not None and cue.start - previous.end > 1.5
        if (
            previous
            and not separated
            and len(previous.text) + len(cue.text) < 180
            and previous.end - previous.start < 8
            and not re.search(r"[.!?…][\"')\]]?$", previous.text)
        ):
            previous.end = max(previous.end, cue.end)
            previous.text = _clean_text(f"{previous.text} {cue.text}")
        else:
            output.append(cue)
    return output


def _timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _to_srt(cues: List[TranscriptCue]) -> str:
    return "\n\n".join(
        f"{index}\n{_timestamp(cue.start)} --> {_timestamp(cue.end)}\n{cue.text}"
        for index, cue in enumerate(cues, start=1)
    )


def _caption_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["fmt"] = "json3"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def classify_transcript_failure(message: str) -> TranscriptProviderError:
    normalized = message.casefold()
    retry_hint = re.search(r"\b(?:temporarily|try again)\b", normalized) is not None

    if re.search(r"\b(?:429|too many requests)\b", normalized):
        return TranscriptProviderError(TranscriptFailureReason.REQUEST_BLOCKED, message, True)
    if not retry_hint and re.search(r"\b(?:private|removed|deleted)\b", normalized):
        return TranscriptProviderError(TranscriptFailureReason.PRIVATE_OR_DELETED, message, False)
    if re.search(r"\b(?:confirm your age|age[- ]restricted)\b", normalized) or (
        not retry_hint and re.search(r"\b(?:age|region|country|restricted)\b", normalized)
    ):
        return TranscriptProviderError(TranscriptFailureReason.RESTRICTED, message, False)
    if re.search(r"\bblocked\b", normalized):
        return TranscriptProviderError(TranscriptFailureReason.REQUEST_BLOCKED, message, True)
    if not retry_hint and re.search(r"\b(?:disabled|not allowed)\b", normalized):
        return TranscriptProviderError(TranscriptFailureReason.CAPTIONS_DISABLED, message, False)
    if re.search(r"\b(?:yet|processing|no readable caption track)\b", normalized):
        return TranscriptProviderError(TranscriptFailureReason.WAITING_FOR_CAPTIONS, message, True)
    if not retry_hint and re.search(r"\bunavailable\b", normalized):
        return TranscriptProviderError(TranscriptFailureReason.PRIVATE_OR_DELETED, message, False)
    return TranscriptProviderError(TranscriptFailureReason.UNKNOWN, message, True)


class YouTubeTranscriptClient:
    """Public-caption provider using YouTube player data (unofficial and optional)."""

    provider_name = "youtube-player"

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    @staticmethod
    def supports(video_id: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id))

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                # Summary clicks must fail over quickly; a stalled YouTube
                # caption endpoint must not keep Discord's typing indicator up.
                timeout=aiohttp.ClientTimeout(total=4),
            )
        return self._session

    @staticmethod
    def _ordered_tracks(
        player: Dict[str, Any], preferred_languages: Sequence[str] = ("en",)
    ) -> List[Dict[str, Any]]:
        tracklist = player.get("captions", {}).get("playerCaptionsTracklistRenderer", {})
        tracks = tracklist.get("captionTracks", [])
        if not isinstance(tracks, list):
            return []
        default_index = tracklist.get("defaultCaptionTrackIndex")
        language_order = {language.casefold(): index for index, language in enumerate(preferred_languages)}
        valid_tracks = [
            (index, track)
            for index, track in enumerate(tracks)
            if isinstance(track, dict)
        ]
        return [track for _, track in sorted(
            valid_tracks,
            key=lambda item: (
                language_order.get(str(item[1].get("languageCode", "")).casefold(), len(language_order)),
                item[1].get("kind") == "asr",
                item[0] != default_index,
            ),
        ) if isinstance(track, dict)]

    async def _load_first_track(
        self,
        session: aiohttp.ClientSession,
        player: Dict[str, Any],
        preferred_languages: Sequence[str] = ("en",),
    ) -> tuple[Optional[Dict[str, Any]], List[TranscriptCue]]:
        for track in self._ordered_tracks(player, preferred_languages):
            base_url = track.get("baseUrl")
            if not base_url:
                continue
            async with session.get(
                _caption_url(base_url),
                headers={"User-Agent": WEB_USER_AGENT},
            ) as response:
                if not response.ok:
                    continue
                text = await response.text()
            try:
                cues = parse_json3_captions(json.loads(text))
            except json.JSONDecodeError:
                cues = []
            if cues:
                return track, cues
        return None, []

    async def fetch(
        self, video_id: str, preferred_languages: Sequence[str] = ("en",)
    ) -> TranscriptBundle:
        if not self.supports(video_id):
            raise TranscriptProviderError(
                TranscriptFailureReason.MALFORMED,
                "Invalid YouTube video ID.",
                retryable=False,
            )
        session = await self._get_session()
        player: Dict[str, Any] = {}
        selected: Optional[Dict[str, Any]] = None
        cues: List[TranscriptCue] = []

        # Exact Watch Better path: read the signed caption track from YouTube's page.
        try:
            async with session.get(
                f"https://www.youtube.com/watch?v={video_id}",
                headers={"User-Agent": WEB_USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            ) as response:
                if response.ok:
                    page_player = extract_youtube_player_response(await response.text())
                    if page_player:
                        selected, cues = await self._load_first_track(
                            session, page_player, preferred_languages
                        )
                        if selected and cues:
                            player = page_player
        except aiohttp.ClientError:
            pass

        if not selected or not cues:
            # Watch Better's Android fallback also works when page metadata is blocked.
            body = {
                "videoId": video_id,
                "context": {
                    "client": {
                        "clientName": "ANDROID",
                        "clientVersion": "20.10.38",
                        "androidSdkVersion": 30,
                        "userAgent": ANDROID_USER_AGENT,
                        "hl": "en",
                        "gl": "US",
                    }
                },
            }
            try:
                async with session.post(
                    ANDROID_PLAYER_URL,
                    json=body,
                    headers={"User-Agent": ANDROID_USER_AGENT},
                ) as response:
                    response.raise_for_status()
                    player = await response.json()
            except aiohttp.ContentTypeError as error:
                raise TranscriptProviderError(
                    TranscriptFailureReason.MALFORMED,
                    "YouTube returned malformed transcript metadata.",
                    retryable=True,
                ) from error
            except aiohttp.ClientResponseError as error:
                if error.status == 429:
                    raise TranscriptProviderError(
                        TranscriptFailureReason.REQUEST_BLOCKED,
                        "YouTube rate limited the transcript provider.",
                        retryable=True,
                    ) from error
                raise TranscriptProviderError(
                    TranscriptFailureReason.NETWORK,
                    f"YouTube player request failed with HTTP {error.status}.",
                    retryable=error.status >= 500,
                ) from error
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                raise TranscriptProviderError(
                    TranscriptFailureReason.NETWORK,
                    "Temporary network failure while retrieving captions.",
                    retryable=True,
                ) from error
            except json.JSONDecodeError as error:
                raise TranscriptProviderError(
                    TranscriptFailureReason.MALFORMED,
                    "YouTube returned malformed transcript metadata.",
                    retryable=True,
                ) from error
            selected, cues = await self._load_first_track(
                session, player, preferred_languages
            )

        if not selected or not cues:
            reason = player.get("playabilityStatus", {}).get("reason")
            raise classify_transcript_failure(
                reason or "This video has no readable caption track yet."
            )

        details = player.get("videoDetails", {})
        is_auto_generated = selected.get("kind") == "asr"
        return TranscriptBundle(
            video_id=video_id,
            title=details.get("title") or f"YouTube video {video_id}",
            channel_name=details.get("author") or "Unknown channel",
            language=selected.get("languageCode") or "unknown",
            plain_text="\n".join(cue.text for cue in cues),
            srt_text=_to_srt(cues),
            segments=cues,
            provider=self.provider_name,
            source_type="automatic_captions" if is_auto_generated else "creator_captions",
            is_auto_generated=is_auto_generated,
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
