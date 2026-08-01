# Selecting active, high-signal AI/tech YouTube creators

Research date: 2026-07-31. Primary sources only: YouTube/Google documentation, YouTube channel pages, and official organization pages.

## Recommendation

Select about 50 subscriptions with a two-stage process:

1. **Eligibility gate:** at least 5 of the latest 8 substantive uploads concern AI, software engineering, research, or important tech news. Exempt verified first-party labs/platforms because they may publish infrequently but are authoritative.
2. **Rank eligible channels:** relevance 30%, recent activity 25%, week-to-week consistency 15%, originality/authority 15%, age-normalized engagement 10%, format hygiene 5%.

Use a balanced final set:

- 8-12 first-party labs/platforms/research institutions.
- 25-30 independent news, analysis, and practical-tool channels.
- 8-12 deep technical/research explainers.

This prevents prolific reaction channels from crowding out slower primary sources. Popularity should be a weak signal: YouTube rounds public subscriber counts to three significant figures and some channels hide them. Shorts view counts also became non-comparable with long-form views because, since 2025-03-31, a Shorts view counts whenever the Short starts or replays. [YouTube channel resource](https://developers.google.com/youtube/v3/docs/channels) [YouTube video resource](https://developers.google.com/youtube/v3/docs/videos)

## Data collection

For an authenticated user's 266 subscriptions:

1. Page through `subscriptions.list(part=snippet, mine=true, maxResults=50)`. This needs six 1-unit calls. The API supports pagination and at most 50 subscriptions per call. [YouTube `subscriptions.list`](https://developers.google.com/youtube/v3/docs/subscriptions/list)
2. Batch channel IDs through `channels.list(part=snippet,contentDetails,statistics)`, up to 50 per call. Read `contentDetails.relatedPlaylists.uploads`; it is the channel's authoritative uploads playlist. [YouTube `channels.list`](https://developers.google.com/youtube/v3/docs/channels/list) [YouTube channel resource](https://developers.google.com/youtube/v3/docs/channels)
3. Read the newest 12-20 entries from each uploads playlist with `playlistItems.list`. Use `contentDetails.videoPublishedAt`; `snippet.publishedAt` is when the item was added to the playlist, not necessarily when the video was published. [YouTube playlist-item resource](https://developers.google.com/youtube/v3/docs/playlistItems) [YouTube `playlistItems.list`](https://developers.google.com/youtube/v3/docs/playlistItems/list)
4. Batch video IDs through `videos.list(part=snippet,contentDetails,status,statistics,liveStreamingDetails)`. Use duration to separate Shorts/clips, `liveBroadcastContent`/live details to separate streams, and public video statistics only as secondary quality evidence. Calls cost 1 unit and accept comma-separated IDs. [YouTube `videos.list`](https://developers.google.com/youtube/v3/docs/videos/list) [YouTube video resource](https://developers.google.com/youtube/v3/docs/videos)

Do not use `search.list` per channel. The uploads playlist is direct and authoritative; search is relevance-ranked and has its own restricted daily bucket. [YouTube `search.list`](https://developers.google.com/youtube/v3/docs/search/list)

## Concrete scoring

Calculate on the latest 12 substantive public uploads, excluding Shorts under 120 seconds, trailers, and stream countdowns:

- **Relevance (0-30):** share about AI models/tools, AI engineering, computing research, cybersecurity, developer platforms, or consequential tech-company news.
- **Activity (0-25):** 30-day substantive-upload count, capped at 8. Require latest upload within 21 days for independent channels; allow 90 days for first-party labs.
- **Consistency (0-15):** number of distinct active weeks in the last 8 weeks, not raw upload volume.
- **Originality/authority (0-15):** first-party announcement/research, original testing, interviews with accountable experts, code/demos, or citations to papers/product notes.
- **Engagement (0-10):** median age-normalized views plus like/comment rates across long-form uploads. Winsorize outliers and compare within format; do not let one viral video dominate.
- **Format hygiene (0-5):** clear titles, useful descriptions/sources, limited duplicate clips, and a manageable posting volume.

Manually review the top 60 before taking 50. Topic classification and originality cannot be established reliably from metadata alone.

## Exclusions and demotions

Exclude or demote channels when any applies:

- No substantive upload in 60 days, unless it is a first-party source.
- More than 40% of the latest 12 substantive uploads are off-topic.
- Primarily Shorts, podcast clips, livestream archives, sponsor promos, compilation/repost content, or generated-voice summaries.
- Repeated near-duplicate uploads, misleading title/thumbnail patterns, unsourced rumor recaps, or content whose main purpose is selling trading, "get rich quick," SEO, or course funnels.
- Several uploads per day with little original reporting; route these to an optional firehose rather than the core news feed.

YouTube itself identifies repetitive engagement manipulation, off-platform diversion, scams, and maliciously misleading clickbait as spam patterns. Treat those as exclusion evidence, not merely an aesthetic preference. [YouTube spam policy](https://support.google.com/youtube/answer/2801973)

For realistic AI-generated footage or cloned third-party voices, prefer creators who disclose synthetic media. YouTube requires disclosure for meaningfully altered or generated realistic content and can penalize repeated nondisclosure. [YouTube altered/synthetic-content policy](https://support.google.com/youtube/answer/14328491)

## High-confidence anchors if present in the subscriptions

These are roles to preserve in the final mix, not a claim that every channel must be imported. The activity estimate is a direct snapshot of the eight newest videos visible on each official YouTube channel page on 2026-07-31; bursts can overstate long-run cadence.

| Channel | Role | Recent cadence snapshot |
|---|---|---:|
| [OpenAI](https://www.youtube.com/@OpenAI/videos) | First-party model/product announcements | launch burst; 8 videos in 2 days |
| [Anthropic](https://www.youtube.com/@anthropic-ai/videos) | First-party model/research announcements | about 0.3/week |
| [Google DeepMind](https://www.youtube.com/@GoogleDeepMind/videos) | First-party research and product work | about 3.1/week |
| [NVIDIA](https://www.youtube.com/@NVIDIA/videos) | First-party AI compute/platform news | about 6.1/week |
| [Hugging Face](https://www.youtube.com/@HuggingFace/videos) | Open-model ecosystem and technical talks | about 0.8/week |
| [IBM Technology](https://www.youtube.com/@IBMTechnology/videos) | Frequent enterprise/technical explainers | about 6.1/week |
| [The AI Daily Brief](https://www.youtube.com/@AIDailyBrief/videos) | Daily independent news digest | about 7/week |
| [Matt Wolfe](https://www.youtube.com/@mreflow/videos) | Tool/news roundup | about 1.6/week |
| [Wes Roth](https://www.youtube.com/@WesRoth/videos) | Fast model/company news commentary | about 2.7/week |
| [AI Explained](https://www.youtube.com/@aiexplained-official/videos) | Lower-volume model/research synthesis | about 0.6/week |
| [Two Minute Papers](https://www.youtube.com/@TwoMinutePapers/videos) | Research-paper explanations | about 1.3/week |
| [Fireship](https://www.youtube.com/@Fireship/videos) | High-signal developer/platform news | about 2.3/week |
| [MattVidPro AI](https://www.youtube.com/@MattVidPro/videos) | Generative-media tools and tests | about 0.8/week |

Favor independent channels with complementary roles rather than five channels repeating the same model rumor. Keep trading, general podcasts, creator-marketing, and broad productivity channels outside the core AI-news 50 unless their latest-upload relevance passes the gate.

## Ongoing tracking

Prefer YouTube's official push-notification path instead of frequent polling. Subscribe a webhook to `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`. YouTube sends Atom notifications for uploads and also for title/description updates, so deduplicate by `yt:videoId` and only announce an unseen video ID. [YouTube push-notification guide](https://developers.google.com/youtube/v3/guides/push_notifications)

If a public callback is unavailable, poll each official Atom feed conservatively, retain the last-seen video IDs, and run a slower periodic API reconciliation. Never treat a title update as a new upload.
