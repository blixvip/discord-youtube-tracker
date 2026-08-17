# Implementation Plan

## Current architecture

- **Always-on production path:** TypeScript Cloudflare Worker, Discord HTTP interactions, 5-minute Cron Trigger, and D1 (`cloudflare/src/index.ts`). YouTube uploads come from public Atom feeds; D1 stores routes, checkpoints, queued posts, and caption blobs.
- **Optional local path:** Python 3.11/`discord.py` gateway bot. It can poll feeds, run legacy Reddit commands, and retrieve public YouTube captions through an undocumented player endpoint. Local JSON persists its routes.
- **Current commands:** `/addchannel`, `/removechannel`, `/channels`, `/checkchannels`; Python also defines `/transcript` and prefix commands.

## Working features

- Channel ID/URL/handle resolution, creator + aggregate Discord destinations, periodic cloud polling, restart-safe checkpoints, safe mentions, and a D1 pending-post queue.
- Optional timestamped caption retrieval, TXT/SRT rendering, upload to D1, and private caption-download interaction.
- Python and Worker unit suites plus Cloudflare deployment configuration.

## Major problems

- Sent notifications have no permanent ledger: deleting a queue row weakens durable duplicate prevention.
- Routes omit guild/configuration metadata; queued failures have no attempt schedule or dead-job visibility.
- Worker channel normalization fails for some bare handles/URLs; outbound retries/rate limits and health diagnostics are weak.
- Transcript code lacks a provider interface, explicit failure/state model, timestamped D1 segments, durable retries, and cloud-worker ownership. The official YouTube Data API cannot download captions for arbitrary public videos, so the existing fallback is unofficial and cloud-IP fragile.
- Production command registration and migration/deployment validation are under-documented.

## Deadline release scope

1. Add backward-compatible D1 migrations for guild-scoped routes, videos, persistent notification states, jobs, transcript metadata/segments, and health state.
2. Make upload discovery and queueing transactionally idempotent; retain sent records; add bounded retry/backoff and dead-job diagnostics.
3. Harden channel input normalization, Discord rate-limit handling, safe research cards, `/transcript` timestamp search, and admin `/health`.
4. Refactor Python captions behind a provider abstraction with normalized timestamped segments and truthful classified failures; cache status/segments through the Worker without blocking upload posts.
5. Add focused tests, command-registration tooling, deployment/migration docs, and a roadmap.

## Expected changes

- `cloudflare/src/index.ts`, `cloudflare/migrations/*`, `cloudflare/test/*`, `cloudflare/scripts/*`
- `youtube_transcript.py`, `caption_cache.py`, `discord_bot.py`, focused Python tests
- `README.md`, `env_example.txt`, `docs/ROADMAP.md`, deployment docs

## Test strategy

- Offline unit/integration tests for normalization, routing/idempotency, retry schedules, transcript normalization/failures/search, permissions, mentions, and no-key startup.
- TypeScript typecheck/Vitest, Python pytest, Docker build/config validation.
- Apply migrations and exercise health/poll/transcript behavior against the deployed Worker when credentials and network access permit; report anything not live-tested.

## Deployment strategy

Preserve the free Cloudflare Worker + Cron + D1 architecture. Apply additive migrations, register commands, deploy the Worker, then verify its public health endpoint and remote D1 state. Keep the Python transcript producer optional and separately deployable; never imply that a home-only process is always-on.

## Deferred

AI summaries/QA, embeddings, semantic search, trends, leads, watchlists, digests, research threads, push ingestion, Shorts/live/premiere metadata classification, and authorized speech-to-text. These belong in `docs/ROADMAP.md`; no placeholder commands will ship.
