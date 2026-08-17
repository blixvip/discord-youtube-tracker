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


def test_classifies_retryable_and_permanent_transcript_failures():
    waiting = classify_transcript_failure("Captions are still processing")
    assert waiting.reason == TranscriptFailureReason.WAITING_FOR_CAPTIONS
    assert waiting.retryable is True

    private = classify_transcript_failure("This video is private")
    assert private.reason == TranscriptFailureReason.PRIVATE_OR_DELETED
    assert private.retryable is False

    disabled = classify_transcript_failure("Captions disabled by owner")
    assert disabled.reason == TranscriptFailureReason.CAPTIONS_DISABLED
    assert disabled.retryable is False
