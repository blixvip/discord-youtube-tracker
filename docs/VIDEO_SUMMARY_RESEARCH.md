# Video summary design research

## Recommendation

Do not add a third-party "skill" or framework. The bot already uses Gemini and
Discord's interaction API; the reliable implementation is a source-preserving
pipeline around those APIs. It avoids two present quality losses:

1. `transcriptForGemini()` discards the middle of very long videos.
2. `sendVideoSummary()` uses `discordText()` rather than `splitDiscordText()`,
   so Discord receives at most the first 1,900 characters of a generated brief.

The feature should be explicitly user initiated: every tracked video card gets
one **Summarize** button; no summary is generated or posted until it is clicked.
On click, create one learning card in `#summary` (or a thread on that card),
then keep its **Ask about this video** button/thread context keyed to video ID.
The feed remains a feed, not an unsolicited stream of summaries.

## Source-preserving pipeline

1. **Acquire evidence.** Keep the existing timestamped SRT/caption segments,
   not only `plainText`. If captions are missing, Gemini can accept a *public*
   YouTube URL directly; it is not necessary to fail only because captions do
   not exist. Private and unlisted URLs are not supported by this route.
   [Gemini video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)
2. **Do not cut the transcript.** If it fits the selected model context, submit
   the complete timestamped transcript. Gemini documents long-context
   summarization and Q&A as a supported use case. Put the actual question at
   the end of a long prompt, as its guide recommends.
   [Gemini long context](https://ai.google.dev/gemini-api/docs/long-context)
3. **For inputs too large for one request, map then reduce.** Split only at
   caption/time boundaries (for example 5--10 minute sections with modest
   overlap). Ask the model to extract every substantive claim, method, example,
   number, caveat, tool and URL from *that* section, each carrying start/end
   timestamps. Then reduce the section records into chapters and a detailed
   learning brief. Never use a beginning+ending splice: it silently loses the
   material the user most wants.
4. **Require a schema.** Gemini's structured-output support can enforce a JSON
   schema instead of hoping free-form Markdown includes all requested sections.
   [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output?lang=rest)
5. **Render, do not truncate.** Convert the validated result to multiple
   Discord messages/embed fields, split on section boundaries, and include
   timestamp links of the form `https://www.youtube.com/watch?v=<id>&t=<sec>s`.
   A short top card can link to the full multi-message/thread detail.

Suggested final schema:

```text
overview; thesis; chapters[{start,end,title,explanation,evidence[]}];
key_claims[{claim,start,end}]; workflows[{steps[],start,end}];
examples[]; tools[]; websites[{name,url,context,start,end}];
numbers_and_definitions[]; practical_takeaways[]; caveats[];
uncertain_or_not_in_transcript[]
```

Every nontrivial item must have timestamps; absent websites or unsupported
claims must be represented as empty/uncertain, never invented. Prompt the model
to treat transcript/video content as data, not instructions.

## Grounded follow-up Q&A

Persist the transcript segments plus final structured summary by `video_id`.
For an answer, provide either the full cached source when it fits or retrieve
the relevant timestamped sections first, then require:

```text
Answer only from supplied video evidence. If absent, say "not covered".
Return answer plus [{timestamp, supporting excerpt/claim}] citations.
```

Do not answer from the summary alone: summaries omit detail. For repeated Q&A,
cache the transcript/video and stable system instruction by video ID; Gemini's
context caching is intended for reused long inputs and documents lower cost and
latency in that use case.
[Gemini context caching](https://ai.google.dev/gemini-api/docs/generate-content/caching)

For video-only fallback, request visual as well as spoken evidence. Gemini's
video guide supports timestamp-oriented questions and notes video is sampled by
default, so rapid visual changes may be missed; display that limitation when
relevant.
[Gemini video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)

## Discord delivery pattern

Use the button interaction as the explicit trigger. A deferred interaction is
the official loading/long-running response, then edit it or post the completed
learning card in `#summary`; a modal is appropriate for the free-text follow-up
question. Discord documents buttons, modals, deferred responses, and follow-up
edits for exactly this interaction flow.
[Interactions and commands](https://docs.discord.com/developers/platform/interactions)
[Receiving and responding](https://docs.discord.com/developers/interactions/receiving-and-responding)

## Acceptance tests

- A new and an already-stored video card each exposes **Summarize**; neither
  creates a summary until clicked.
- Clicking it produces exactly one detailed learning card in `#summary`, with
  all sections rendered (not silently cut at 1,900 characters) and timestamp
  links.
- A long video retains a claim from its middle section.
- A captionless public video uses the Gemini video fallback; a private/unlisted
  video gives an accurate availability error.
- Asking an in-video question returns evidence timestamps; asking about an
  absent fact says it is not covered.
- Re-clicking uses the cached result or explicitly offers a refresh, without
  duplicate posts.
