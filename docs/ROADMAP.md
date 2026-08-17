# Product Roadmap

The release core is upload tracking, durable deduplication, cached transcripts, timestamp search, and diagnostics. Items below are intentionally not exposed as placeholder commands.

## P0 — Always-on authorized transcript worker

**Goal:** Process queued transcript jobs without a personal computer.

**Outline:** Deploy the existing `TranscriptProvider` producer to a lawful always-on container; claim D1 jobs with leases; ingest normalized segments; retry caption-processing/network failures at 5m, 15m, 1h, 6h, and 24h; dead-letter permanent failures.

**Dependencies:** A cloud runtime whose YouTube access is tested, explicit operator authorization, and a separate `CAPTION_INGEST_SECRET`. Official YouTube caption download only supports videos the authenticated user may edit; arbitrary-public caption retrieval remains unofficial and cloud-IP fragile.

**Acceptance:** New upload reaches `ready` or truthful terminal state after restart; exactly one job per video; cloud-runtime fixture passes.

## P1 — Content-type metadata and filters

**Goal:** Reliably apply per-route Shorts, livestream, and premiere settings.

**Outline:** Enrich Atom events with bounded video metadata; classify scheduled/live/short content; retain updates without treating them as new uploads.

**Dependencies:** YouTube metadata source/quota policy.

**Acceptance:** Fixtures for Short/live/premiere/title update/deleted video route correctly without duplicate posts.

## P1 — Grounded analysis and one-video Q&A

**Goal:** Optional structured summaries and `/ask` with timestamp evidence.

**Outline:** Add one configurable AI provider, schema validation, transcript chunking, evidence IDs, cache/version keys, daily limits, and AI-disabled fallback.

**Dependencies:** Operator-selected provider credential; transcript worker.

**Acceptance:** Every material claim cites stored segment IDs/timestamps; unsupported answers say evidence is absent; no-key mode passes.

## P2 — Archive search and cross-video research

**Goal:** Search titles, metadata, segments, tags, tools, and links; answer across videos.

**Outline:** D1 FTS-backed lexical search first; optional embeddings later; `/search`, `/research`, and `/compare` return timestamp links and distinguish evidence from inference.

**Dependencies:** Segment ingestion and retention policy.

**Acceptance:** Ranked fixture queries return expected creators/videos/timestamps with no paid service required.

## P2 — Watchlists and digests

**Goal:** Per-guild keyword alerts plus concise daily/weekly intelligence.

**Outline:** Watchlist tables, exclusions/confidence/cooldowns, timezone-aware scheduled jobs, evidence-linked digest ranking.

**Dependencies:** Search/analysis archive.

**Acceptance:** Admin permissions enforced; cooldown prevents repeat alerts; deterministic digest fixtures.

## P3 — Explainable trends and leads

**Goal:** Cross-creator momentum and public professional opportunity signals.

**Outline:** Canonical topics/aliases, distinct-creator and period-growth components, trend snapshots, evidence-bound lead extraction, Save/Dismiss feedback.

**Dependencies:** Sufficient archive history and grounded analysis.

**Acceptance:** No one-creator “trend”; displayed score components reproduce stored score; every lead has public timestamped evidence.

## P3 — Push ingestion and advanced operations

**Goal:** Reduce detection latency while retaining polling recovery.

**Outline:** Evaluate YouTube-supported push notifications, webhook validation/renewal, polling reconciliation, queue/service split only when load requires it.

**Dependencies:** Stable callback deployment and documented current API support.

**Acceptance:** Push event and missed-event fallback each produce one notification; redeploy/replay tests pass.
