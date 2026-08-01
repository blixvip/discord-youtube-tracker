import { describe, expect, it } from "vitest";
import {
  extractChannelId,
  formatTranscriptFile,
  parseAtomFeed,
  parseCaptionCustomId,
  safeCaptionBaseName,
  slugify,
} from "../src/index";

describe("YouTube helpers", () => {
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

  it("creates Discord-safe creator slugs", () => {
    expect(slugify("AI Explained!")) .toBe("ai-explained");
  });

  it("accepts only valid caption button IDs", () => {
    expect(parseCaptionCustomId("captions:wAPDmc8e22U")).toBe("wAPDmc8e22U");
    expect(parseCaptionCustomId("captions:../../secret")).toBeNull();
    expect(parseCaptionCustomId("other:wAPDmc8e22U")).toBeNull();
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
});
