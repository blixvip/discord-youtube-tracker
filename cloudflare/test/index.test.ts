import { afterEach, describe, expect, it, vi } from "vitest";
import {
  extractChannelId,
  extractGeminiText,
  extractVideoId,
  extractVideoIdsFromText,
  extractYouTubePlayerResponse,
  fetchCaptionsFromYouTube,
  formatTranscriptFile,
  normalizeYouTubeInput,
  parseAtomFeed,
  parseCaptionCustomId,
  parseSummaryAnswerModalId,
  parseSummaryCustomId,
  parseSummaryQuestionCustomId,
  parseJson3CaptionCues,
  parseSrtSegments,
  retryDelaySeconds,
  searchTranscript,
  safeCaptionBaseName,
  slugify,
  buildSummaryPrompt,
  copyLinkResponse,
  copyPageHtml,
  editInteraction,
  geminiRetryDelayMs,
  hasCurrentVideoActions,
  parseChatTranscriptCustomId,
  parseCopyLinkCustomId,
  staleCardVideoId,
  summaryResultComponents,
  transcriptChatChunks,
  transcriptPageHtml,
  transcriptPreview,
  transcriptSegmentBatches,
  videoActionComponents,
} from "../src/index";

describe("YouTube helpers", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("parses an Atom feed", () => {
    const videos = parseAtomFeed(`
      <feed><title>Example Creator</title><entry>
        <yt:videoId>abcdefghijk</yt:videoId>
        <title>Useful &amp; New</title>
        <published>2026-07-31T12:00:00Z</published>
      </entry></feed>
    `);
    expect(videos).toEqual([expect.objectContaining({
      videoId: "abcdefghijk",
      title: "Useful & New",
      channelName: "Example Creator",
    })]);
  });

  it("extracts direct and page channel IDs", () => {
    const id = "UC1234567890123456789012";
    expect(extractChannelId(`https://youtube.com/channel/${id}`)).toBe(id);
    expect(extractChannelId("https://youtube.com/@example", `{"channelId":"${id}"}`)).toBe(id);
  });

  it("normalizes common channel inputs and resolves video IDs", () => {
    const id = "UC1234567890123456789012";
    expect(normalizeYouTubeInput(id)).toBe(id);
    expect(normalizeYouTubeInput("@example")).toBe("https://www.youtube.com/@example");
    expect(normalizeYouTubeInput("youtube.com/watch?v=wAPDmc8e22U"))
      .toBe("https://youtube.com/watch?v=wAPDmc8e22U");
    expect(extractVideoId("https://youtu.be/wAPDmc8e22U?t=4")).toBe("wAPDmc8e22U");
    expect(extractVideoId("https://youtube.com/shorts/wAPDmc8e22U")).toBe("wAPDmc8e22U");
    expect(extractVideoIdsFromText("watch <https://youtube.com/watch?list=x&v=wAPDmc8e22U> or https://youtu.be/abcdefghijk?t=1"))
      .toEqual(["wAPDmc8e22U", "abcdefghijk"]);
    expect(() => normalizeYouTubeInput("https://example.com/video")).toThrow(/Only YouTube/);
  });

  it("parses Watch Better player data and merges JSON3 caption fragments", () => {
    const player = extractYouTubePlayerResponse(`before ytInitialPlayerResponse = {"videoDetails":{"title":"A } title"},"ok":true}; after`);
    expect(player).toEqual({ videoDetails: { title: "A } title" }, ok: true });
    expect(parseJson3CaptionCues({ events: [
      { tStartMs: 0, dDurationMs: 1000, segs: [{ utf8: "Hello" }] },
      { tStartMs: 1000, dDurationMs: 1000, segs: [{ utf8: " world." }] },
      { tStartMs: 3000, dDurationMs: 1000, segs: [{ utf8: "Next &amp; last." }] },
    ] })).toEqual([
      { startSeconds: 0, endSeconds: 2, text: "Hello world." },
      { startSeconds: 3, endSeconds: 4, text: "Next & last." },
    ]);
  });

  it("fetches a signed Watch Better caption track without a local producer", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(`ytInitialPlayerResponse = ${JSON.stringify({
        videoDetails: { title: "Cloud transcript", author: "Example" },
        captions: { playerCaptionsTracklistRenderer: { captionTracks: [
          { baseUrl: "https://captions.example/timedtext?x=1", languageCode: "en" },
        ] } },
      })};`, { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ events: [
        { tStartMs: 0, dDurationMs: 1500, segs: [{ utf8: "Works from the Worker." }] },
      ] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchCaptionsFromYouTube("wAPDmc8e22U")).resolves.toMatchObject({
      language: "en",
      title: "Cloud transcript",
      channelName: "Example",
      plainText: "Works from the Worker.",
    });
    expect(fetchMock.mock.calls[1]?.[0]).toContain("fmt=json3");
  });

  it("uses bounded exponential retry delays", () => {
    expect([1, 2, 3, 20].map(retryDelaySeconds)).toEqual([30, 60, 120, 3600]);
  });

  it("returns timestamped transcript search results", () => {
    const captions = {
      language: "en",
      plainText: "Browser agents are useful. Another point.",
      srtText: "1\n00:00:04,000 --> 00:00:07,000\nBrowser agents are useful.\n\n2\n00:01:02,000 --> 00:01:05,000\nAnother point.",
    };
    expect(parseSrtSegments(captions.srtText)).toHaveLength(2);
    expect(searchTranscript(captions, "wAPDmc8e22U", "browser agents")).toEqual([
      "• [0:04](https://www.youtube.com/watch?v=wAPDmc8e22U&t=4s) — Browser agents are useful.",
    ]);
  });

  it("keeps transcript segment writes below D1's bind-variable limit", () => {
    const segments = Array.from({ length: 25 }, (_, index) => ({
      startSeconds: index,
      durationSeconds: 1,
      text: `segment ${index}`,
    }));
    expect(transcriptSegmentBatches(segments).map((batch) => batch.length)).toEqual([10, 10, 5]);
    expect(transcriptSegmentBatches(segments).every((batch) => batch.length * 8 <= 100)).toBe(true);
  });

  it("creates Discord-safe creator slugs", () => {
    expect(slugify("AI Explained!")) .toBe("ai-explained");
  });

  it("accepts only valid caption button IDs", () => {
    expect(parseCaptionCustomId("captions:wAPDmc8e22U")).toBe("wAPDmc8e22U");
    expect(parseCaptionCustomId("captions:../../secret")).toBeNull();
    expect(parseCaptionCustomId("other:wAPDmc8e22U")).toBeNull();
  });

  it("accepts only valid summary action IDs", () => {
    expect(parseSummaryCustomId("summary:wAPDmc8e22U")).toBe("wAPDmc8e22U");
    expect(parseSummaryQuestionCustomId("summary-question:wAPDmc8e22U")).toBe("wAPDmc8e22U");
    expect(parseSummaryAnswerModalId("summary-answer:wAPDmc8e22U")).toBe("wAPDmc8e22U");
    expect(parseSummaryCustomId("summary:../../secret")).toBeNull();
    expect(parseSummaryQuestionCustomId("summary:wAPDmc8e22U")).toBeNull();
    expect(parseSummaryAnswerModalId("other:wAPDmc8e22U")).toBeNull();
  });

  it("builds an evidence-bound Gemini summary prompt and reads its response", () => {
    const prompt = buildSummaryPrompt(
      { title: "Gemini overview", channelName: "Example Creator", url: "https://www.youtube.com/watch?v=wAPDmc8e22U" },
      { language: "en", plainText: "Visit example.com for the guide.", srtText: "" },
    );
    expect(prompt).toContain("**Tools, websites, and resources mentioned**");
    expect(prompt).toContain("Visit example.com");
    expect(extractGeminiText({ candidates: [{ content: { parts: [{ text: "Useful summary" }] } }] })).toBe("Useful summary");
    expect(() => extractGeminiText({ candidates: [] })).toThrow(/did not return/);
    expect(() => extractGeminiText({
      candidates: [{ finishReason: "MAX_TOKENS", content: { parts: [{ text: "Truncated" }] } }],
    })).toThrow(/output budget/);
  });

  it("creates safe caption filenames and complete transcript text", () => {
    expect(safeCaptionBaseName("What's new: AI / agents?", "wAPDmc8e22U"))
      .toBe("What-s-new-AI-agents-wAPDmc8e22U");
    expect(formatTranscriptFile(
      { language: "en", plainText: "First line\nSecond line", srtText: "" },
      {
        title: "What's new",
        channelName: "Example Creator",
        url: "https://www.youtube.com/watch?v=wAPDmc8e22U",
        published: "2026-08-01T12:00:00Z",
      },
    )).toContain("Caption language: en\n\n---\n\nFirst line\nSecond line");
  });

  it("renders a mobile copy page without allowing transcript HTML injection", () => {
    const html = transcriptPageHtml(
      { language: "en", plainText: "First line\n<script>alert('nope')</script>", srtText: "" },
      {
        title: "A <useful> video",
        channelName: "Example & Co",
        url: "https://www.youtube.com/watch?v=wAPDmc8e22U",
      },
      "test-nonce",
    );
    expect(html).toContain("Copy full transcript");
    expect(html).toContain("Open raw text");
    expect(html).toContain("A &lt;useful&gt; video");
    expect(html).toContain("&lt;script&gt;alert(&#39;nope&#39;)&lt;/script&gt;");
    expect(html).not.toContain("<script>alert('nope')</script>");
    expect(html).toContain('<script nonce="test-nonce">');
  });

  it("keeps short transcript previews whole and clips long previews cleanly", () => {
    expect(transcriptPreview({ language: "en", plainText: "Short transcript", srtText: "" }))
      .toBe("Short transcript");
    const preview = transcriptPreview({
      language: "en",
      plainText: `Opening sentence. ${"mobile transcript text ".repeat(100)}`,
      srtText: "",
    });
    expect(preview.endsWith("…")).toBe(true);
    expect(preview.length).toBeLessThanOrEqual(1_501);
  });

  it("puts the five video actions under every video", () => {
    const [row] = videoActionComponents("wAPDmc8e22U", "https://example.workers.dev") as Array<{
      components: Array<{ label: string; url?: string; custom_id?: string }>;
    }>;
    expect(row.components.map((button) => button.label)).toEqual([
      "Watch",
      "Copy link",
      "Summarize",
      "Transcript",
      "Copy transcript",
    ]);
    expect(row.components[0].url).toBe("https://www.youtube.com/watch?v=wAPDmc8e22U");
    expect(row.components[4].url).toBe("https://example.workers.dev/transcript/wAPDmc8e22U");
    expect(parseCopyLinkCustomId(row.components[1].custom_id)).toBe("wAPDmc8e22U");
    expect(parseChatTranscriptCustomId(row.components[3].custom_id)).toBe("wAPDmc8e22U");
  });

  it("keeps all video actions plus follow-up Q&A on summary results", () => {
    const rows = summaryResultComponents("wAPDmc8e22U", "https://example.workers.dev") as Array<{
      components: Array<{ label: string; custom_id?: string }>;
    }>;
    expect(rows).toHaveLength(2);
    expect(rows[0].components.map((button) => button.label)).toEqual([
      "Watch", "Copy link", "Summarize", "Transcript", "Copy transcript",
    ]);
    expect(rows[1].components[0]).toMatchObject({
      label: "Ask a question",
      custom_id: "summary-question:wAPDmc8e22U",
    });
  });

  it("drops the transcript link button when no public origin is configured", () => {
    const [row] = videoActionComponents("wAPDmc8e22U", "") as Array<{ components: Array<{ url?: string }> }>;
    expect(row.components).toHaveLength(4);
    expect(row.components.every((button) => button.url !== "")).toBe(true);
  });

  it("recognizes cards that still need the current action row", () => {
    const current = {
      author: { id: "app", bot: true },
      components: videoActionComponents("wAPDmc8e22U", "https://example.workers.dev") as Array<{
        components: Array<{ custom_id?: string }>;
      }>,
    };
    expect(hasCurrentVideoActions(current)).toBe(true);
    const old = {
      author: { id: "app", bot: true },
      embeds: [{ url: "https://www.youtube.com/watch?v=wAPDmc8e22U" }],
      components: [{ components: [{ custom_id: "captions:wAPDmc8e22U" }] }],
    };
    expect(hasCurrentVideoActions(old)).toBe(false);
    expect(staleCardVideoId(old, "app")).toBe("wAPDmc8e22U");
    expect(staleCardVideoId({ ...old, author: { id: "other", bot: true } }, "app")).toBeNull();
    expect(staleCardVideoId(current, "app")).toBeNull();
    expect(staleCardVideoId({ author: { id: "app", bot: true }, components: [] }, "app")).toBeNull();
  });

  it("reads a video id from an old card that only carries buttons", () => {
    expect(staleCardVideoId({
      author: { id: "app", bot: true },
      components: [{ components: [{ custom_id: "summary:wAPDmc8e22U" }] }],
    }, "app")).toBe("wAPDmc8e22U");
  });

  it("returns a private copy-link response with a one-tap page", () => {
    const response = copyLinkResponse("wAPDmc8e22U", "https://example.workers.dev") as {
      data: { content: string; flags: number; components: Array<{ components: Array<{ url: string }> }> };
    };
    expect(response.data.content).toContain("https://www.youtube.com/watch?v=wAPDmc8e22U");
    expect(response.data.flags & 64).toBe(64);
    expect(response.data.components[0].components[0].url)
      .toBe("https://example.workers.dev/copy/wAPDmc8e22U");
  });

  it("escapes the copy page title", () => {
    const html = copyPageHtml("https://www.youtube.com/watch?v=wAPDmc8e22U", "A <script> title", "test-nonce");
    expect(html).toContain("A &lt;script&gt; title");
    expect(html).not.toContain("<script> title");
    expect(html).toContain('<script nonce="test-nonce">');
  });

  it("chunks a chat transcript and links the rest when it is too long", () => {
    const short = transcriptChatChunks(
      { language: "en", plainText: "One line\n\nTwo line", srtText: "" },
      { title: "Useful video", channelName: "Example Creator", url: "https://youtu.be/wAPDmc8e22U" },
      "https://example.workers.dev/transcript/wAPDmc8e22U",
    );
    expect(short).toHaveLength(1);
    expect(short[0]).toContain("**Useful video** — full transcript (Example Creator)");

    const long = transcriptChatChunks(
      { language: "en", plainText: "sentence words here ".repeat(4_000), srtText: "" },
      { title: "Long video", channelName: "Example Creator", url: "https://youtu.be/wAPDmc8e22U" },
      "https://example.workers.dev/transcript/wAPDmc8e22U",
    );
    expect(long).toHaveLength(21);
    expect(long.at(-1)).toContain("https://example.workers.dev/transcript/wAPDmc8e22U");
    expect(long.every((chunk) => chunk.length <= 1_990)).toBe(true);
  });

  it("waits the interval Gemini advertises when it rate-limits a summary", () => {
    expect(geminiRetryDelayMs("Please retry in 14.42s", 1)).toBe(14_920);
    expect(geminiRetryDelayMs("Quota exceeded", 3)).toBe(6_000);
    expect(geminiRetryDelayMs("Please retry in 900s", 1)).toBe(30_000);
  });

  it("retries a rate-limited Discord interaction update", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response("rate limited", { status: 429, headers: { "retry-after": "0" } }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await editInteraction({} as never, {
      id: "interaction",
      application_id: "application",
      token: "token",
      type: 3,
    }, "Transcript ready");

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
