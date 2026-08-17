import pytest

from gemini_summary import (
    GeminiSummaryClient,
    GeminiRequestError,
    build_question_prompt,
    build_summary_prompt,
    extract_gemini_text,
    extract_interaction_text,
)
from youtube_transcript import TranscriptBundle


@pytest.fixture
def bundle():
    return TranscriptBundle(
        video_id="wAPDmc8e22U",
        title="A useful video",
        channel_name="Example Creator",
        language="en",
        plain_text="Visit example.com for the guide. This video explains agents.",
        srt_text="",
    )


def test_summary_prompt_is_grounded_and_includes_requested_sections(bundle):
    prompt = build_summary_prompt(bundle)
    assert "**Executive overview**" in prompt
    assert "**Step-by-step methods and workflows**" in prompt
    assert "**Tools, websites, and resources mentioned**" in prompt
    assert "[mm:ss]" in prompt
    assert "Visit example.com" in prompt


def test_question_prompt_and_response_parsing_are_safe(bundle):
    prompt = build_question_prompt(bundle, "Where is the guide?")
    assert "Question: Where is the guide?" in prompt
    assert extract_gemini_text({
        "candidates": [{"content": {"parts": [{"text": "At example.com"}]}}]
    }) == "At example.com"
    with pytest.raises(RuntimeError, match="did not return"):
        extract_gemini_text({"candidates": []})
    with pytest.raises(RuntimeError, match="output budget"):
        extract_gemini_text({
            "candidates": [{
                "finishReason": "MAX_TOKENS",
                "content": {"parts": [{"text": "Truncated"}]},
            }]
        })
    assert extract_interaction_text({
        "steps": [{"type": "model_output", "content": [{"type": "text", "text": "Video fallback works"}]}]
    }) == "Video fallback works"


@pytest.mark.asyncio
async def test_summary_result_is_cached_per_video(bundle):
    client = GeminiSummaryClient("test-key", "gemini-3.6-flash")
    calls = 0

    async def fake_request(prompt):
        nonlocal calls
        calls += 1
        return "Cached summary"

    client._request = fake_request
    assert await client.summarize(bundle) == "Cached summary"
    assert await client.summarize(bundle) == "Cached summary"
    assert calls == 1


@pytest.mark.asyncio
async def test_retries_overloaded_primary_model_with_non_25_fallback():
    client = GeminiSummaryClient("test-key", "gemini-3.6-flash", "gemini-3.5-flash")
    requested_models = []

    async def fake_request_model(model, _prompt):
        requested_models.append(model)
        if model == "gemini-3.6-flash":
            raise GeminiRequestError(500, "high demand")
        return "fallback result"

    client._request_model = fake_request_model
    assert await client._request("test") == "fallback result"
    assert requested_models == ["gemini-3.6-flash", "gemini-3.5-flash"]
