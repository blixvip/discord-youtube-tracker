import { describe, expect, it } from "vitest";
import { extractChannelId, parseAtomFeed, slugify } from "../src/index";

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
});
