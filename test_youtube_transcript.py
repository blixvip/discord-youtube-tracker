import pytest

from youtube_transcript import (
    TranscriptFailureReason,
    YouTubeTranscriptClient,
    classify_transcript_failure,
    extract_youtube_player_response,
    parse_json3_captions,
)


def test_extract_youtube_player_response_handles_braces_in_strings():
    source = 'var ytInitialPlayerResponse = {"videoDetails":{"title":"A } title"}}; next();'

    assert extract_youtube_player_response(source) == {
        "videoDetails": {"title": "A } title"}
    }


def test_parse_json3_captions_merges_sentence_fragments():
    cues = parse_json3_captions({
        "events": [
            {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "What's your"}]},
            {"tStartMs": 1000, "dDurationMs": 1000, "segs": [{"utf8": " biggest mistake?"}]},
        ]
    })

    assert len(cues) == 1
    assert cues[0].text == "What's your biggest mistake?"
    assert cues[0].start == 0
    assert cues[0].end == 2
    assert cues[0].duration == 2


def test_orders_preferred_creator_tracks_and_ignores_malformed_entries():
    player = {
        "captions": {
            "playerCaptionsTracklistRenderer": {
                "captionTracks": [
                    None,
                    {"languageCode": "es", "kind": "asr"},
                    {"languageCode": "en"},
                ]
            }
        }
    }
    tracks = YouTubeTranscriptClient._ordered_tracks(player, ("en", "es"))
    assert [track["languageCode"] for track in tracks] == ["en", "es"]


def test_prefers_regional_language_over_unpreferred_default():
    player = {
        "captions": {
            "playerCaptionsTracklistRenderer": {
                "captionTracks": [{"languageCode": "es"}, {"languageCode": "en-GB"}],
                "defaultCaptionTrackIndex": 0,
            }
        }
    }

    tracks = YouTubeTranscriptClient._ordered_tracks(player, ("en",))

    assert [track["languageCode"] for track in tracks] == ["en-GB", "es"]


def test_orders_exact_and_regional_matches_by_language_preference():
    player = {
        "captions": {
            "playerCaptionsTracklistRenderer": {
                "captionTracks": [
                    {"languageCode": "es"},
                    {"languageCode": "en-CA", "kind": "asr"},
                    {"languageCode": "en-GB"},
                    {"languageCode": "en-US"},
                    {"languageCode": "en-AU"},
                    {"languageCode": "en"},
                ],
                "defaultCaptionTrackIndex": 3,
            }
        }
    }

    tracks = YouTubeTranscriptClient._ordered_tracks(player, ("EN", "es"))

    assert [track["languageCode"] for track in tracks] == [
        "en", "en-US", "en-GB", "en-AU", "en-CA", "es",
    ]


def test_classifies_retryable_and_permanent_transcript_failures():
    waiting = classify_transcript_failure("Captions are still processing")
    assert waiting.reason == TranscriptFailureReason.WAITING_FOR_CAPTIONS
    assert waiting.retryable is True

    private = classify_transcript_failure("This video is private")
    assert private.reason == TranscriptFailureReason.PRIVATE_OR_DELETED
    assert private.retryable is False

    unavailable = classify_transcript_failure("This video is unavailable")
    assert unavailable.reason == TranscriptFailureReason.PRIVATE_OR_DELETED
    assert unavailable.retryable is False

    disabled = classify_transcript_failure("Captions disabled by owner")
    assert disabled.reason == TranscriptFailureReason.CAPTIONS_DISABLED
    assert disabled.retryable is False


@pytest.mark.parametrize(
    "message",
    [
        "Failed to load the watch page",
        "Unexpected response message",
        "Usage information for this language is missing",
        "Captions are temporarily unavailable",
        "Video is unavailable. Try again later.",
        "Region access is temporarily restricted. Try again later.",
        "Caption access is temporarily disabled. Try again later.",
        "Age verification is temporarily unavailable",
        "Private captions are temporarily unavailable",
    ],
)
def test_keeps_transient_or_unknown_failures_retryable(message):
    error = classify_transcript_failure(message)

    assert error.reason == TranscriptFailureReason.UNKNOWN
    assert error.retryable is True


@pytest.mark.parametrize(
    "message",
    [
        "Sign in to confirm your age",
        "Sign in to confirm your age. Try again after signing in.",
        "This is an age-restricted video",
        "This video is unavailable in your country",
        "This video is blocked in your country",
    ],
)
def test_classifies_actual_restrictions_as_permanent(message):
    error = classify_transcript_failure(message)

    assert error.reason == TranscriptFailureReason.RESTRICTED
    assert error.retryable is False


def test_keeps_throttling_retryable_even_when_captions_are_unavailable():
    error = classify_transcript_failure(
        "Captions unavailable in your region: 429 Too Many Requests. Try again later."
    )

    assert error.reason == TranscriptFailureReason.REQUEST_BLOCKED
    assert error.retryable is True


def test_keeps_caption_processing_as_a_specific_retryable_reason():
    error = classify_transcript_failure("Captions are still processing. Try again later.")

    assert error.reason == TranscriptFailureReason.WAITING_FOR_CAPTIONS
    assert error.retryable is True
