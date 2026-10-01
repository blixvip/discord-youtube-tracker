# Discord YouTube Tracker

[![Discord](https://img.shields.io/badge/Discord-Join%20the%20community-5865F2?logo=discord&logoColor=white)](https://discord.gg/zEB4VjmfSb)

**Never miss an upload: every new video from your creators lands in Discord with its transcript and an AI summary one click away.**

A Discord bot that watches YouTube creators, routes new uploads into organized Discord channels, and optionally fetches Reddit memes.

## Features

- Watches public YouTube Atom feeds without a YouTube API key.
- Creates an `AI Video Feeds` category, an `everything` channel, and a channel for each creator.
- Routes every upload to both `everything` and the matching creator channel.
- Polls creators in rotating batches every minute, even with multiple Discord destinations.
- Posts linked embeds with the creator, publish time, thumbnail, and YouTube button.
- Queues transcript processing independently so caption failures never block uploads.
- Puts the same five actions under every video: watch, copy link, summarize, transcript in chat, copy transcript.
- Repairs older cards in the background so they gain the current actions too.
- Summarizes with Gemini 3.6 Flash from the cached transcript, with transcript-grounded follow-up questions.
- Caches successful transcripts in D1 and supports timestamped `/transcript` search.
- Classifies creator versus automatic captions and truthful retryable/permanent failures.
- Creates `youtube-transcripts` and `summary` channels; paste a link for a copyable transcript or complete summary, even when the home computer is off.
- Persists cloud routes, checkpoints, notification idempotency records, retry schedules, and dead jobs in D1.
- Keeps Reddit meme commands available when Reddit credentials are configured.

## Requirements

- Python 3.11+
- A Discord application and bot token
- Bot permissions: View Channels, Send Messages, Embed Links, Attach Files, Read Message History, Manage Channels, and Use Application Commands
- **Message Content Intent** enabled under Discord Developer Portal -> Bot -> Privileged Gateway Intents
- Reddit API credentials only if meme commands are needed

## Setup

```bash
git clone https://github.com/blixvip/discord-youtube-tracker.git
cd discord-youtube-tracker
python -m venv .venv
```

Activate the environment, then install dependencies:

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the required token:

```env
DISCORD_TOKEN=your_discord_bot_token_here
CAPTION_INGEST_SECRET=replace_with_a_long_random_secret
GEMINI_API_KEY=your_gemini_api_key_here
SUBSCRIPTIONS_FILE=./subscriptions.json
SUBSCRIPTIONS_SEED_B64=
LOCAL_FEED_POLLING=false
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
```

Never commit `.env`. If a token is exposed, rotate it in the Discord Developer Portal.

Run the bot:

```bash
python run.py
```

The local bot creates or repairs `#youtube-transcripts` and replies immediately while running. The Cloudflare Worker polls both `#youtube-transcripts` and `#summary` every minute, so pasted links still work when the home computer is off. Set `LOCAL_FEED_POLLING=true` only when Python should also poll creator feeds.

Docker files are included for containerized operation:

```bash
docker compose up --build -d
```

## Free 24/7 cloud deployment

The `cloudflare/` app is the always-on deployment. It uses a Cloudflare Worker,
one-minute Cron Trigger, and D1 for persistent routes, checkpoints, cached
captions, and a restart-safe pending-post queue. It needs no open browser or
home computer.

One Worker owns everything: feed polling, Discord interactions, transcript
intake, transcript and copy pages, and summaries.

```bash
cd cloudflare
npm ci
npx wrangler login
npx wrangler d1 create discord-youtube-transcripts
# Copy the returned database_id into wrangler.jsonc.
npx wrangler d1 migrations apply discord-youtube-transcripts --remote
npx wrangler secret put DISCORD_TOKEN
npx wrangler secret put DISCORD_APPLICATION_ID
npx wrangler secret put DISCORD_PUBLIC_KEY
npx wrangler secret put CAPTION_INGEST_SECRET
npx wrangler secret put GEMINI_API_KEY
npm run deploy
# In a shell with DISCORD_TOKEN and DISCORD_APPLICATION_ID set locally:
npm run register-commands
```

Apply migrations **before** deploying code that uses them. Verify the public, non-sensitive probe at `https://<worker>/health`; administrators can use `/health` for queue and failure counts.

Set the deployed Worker URL as the Discord application's Interactions Endpoint
URL. To move existing routes into D1 without committing private Discord IDs:

```bash
DISCORD_TOKEN=... node scripts/seed_routes.mjs > scripts/seed_routes.sql
npx wrangler d1 execute discord-youtube-transcripts --remote --file scripts/seed_routes.sql
```

`seed_routes.mjs` re-reads every creator's live feed, so each route starts from
the newest upload and taking over a feed never replays a backlog. Regenerate the
file immediately before applying it. The current deployment tracks 50 creators
through 100 routes. Cloudflare secrets, generated seeds, and local Worker state
are excluded from Git.

## Video actions

Every video the bot posts or replies with carries the same five buttons:

| Button | Behavior |
| --- | --- |
| **Watch** | Opens the video on YouTube |
| **Copy link** | Private message with the raw URL plus a one-tap `/copy/<id>` clipboard page |
| **Summarize** | Gemini 3.6 Flash brief from the cached transcript, posted in `#summary` with a follow-up question action |
| **Transcript** | Posts the full transcript into a thread on the card, or privately when threads are unavailable |
| **Copy transcript** | Mobile `/transcript/<id>` page with one-tap copy and a raw-text fallback |

Cards posted before these actions existed are repaired in rotating background
passes. Discord permits only a few edits per hour to messages older than an hour
(error 30046), so historical repair is deliberately slow; newly posted cards
always carry the current row.

Upload cards post immediately and transcript work never blocks them. `/transcript` provides timestamp search. YouTube's official API does not permit downloading captions for arbitrary public videos, so this uses YouTube's public signed caption tracks; videos with captions disabled, private videos, and regional restrictions remain unavailable.


## Commands

YouTube management commands require Manage Server permission.

| Command | Purpose |
| --- | --- |
| `/addchannel <YouTube URL, handle, or channel ID>` | Create destinations and watch a creator |
| `/removechannel <YouTube URL, handle, or channel ID>` | Stop routing a creator to the current Discord channel |
| `/channels` | List creators watched in the current Discord channel |
| `/checkchannels` | Run an immediate check for the current Discord channel |
| `/transcript video:<YouTube URL or ID> query:<optional>` | Search cached captions and return timestamp links |
| `/health` | Admin-only database, route, queue, and failure diagnostics |
| `/help` | Show bot help |
| `!meme [keyword]` | Find Reddit memes, when Reddit is configured |
| `!random [count]` | Fetch random Reddit memes |
| `!search <keyword> [subreddit] [count]` | Search Reddit memes |

Hybrid commands can also use the configured `!` prefix.

## Runtime data

YouTube subscriptions and latest-video checkpoints are stored in `subscriptions.json`. The file is intentionally excluded from Git because it contains server/channel IDs and deployment state. Back it up separately if those routes must survive moving the bot to another machine.

On first add, the latest upload becomes the checkpoint and is not reposted. Subsequent checks inspect the five newest feed entries, so very high-volume creators can exceed the catch-up window during a long outage.

## Tests

```bash
python -m pytest -q
cd cloudflare
npm ci
npm run check
npm test
```

The offline suites cover configuration, Reddit behavior, Discord commands, YouTube feed parsing, caption parsing, subscription persistence, embeds, deduplicated polling, and Worker interactions.

## Project layout

- `discord_bot.py` — Discord commands, transcript intake, feed routing, embeds, and polling
- `youtube_transcript.py` — direct YouTube caption retrieval and `.txt`/`.srt` rendering
- `youtube_client.py` — YouTube channel resolution, Atom parsing, and subscription storage
- `reddit_client.py` — optional Reddit meme client
- `config.py` — environment and bot settings
- `run.py` — application entry point
- `docs/` — implementation research notes

## Community

💬 [Join the Discord](https://discord.gg/zEB4VjmfSb) for questions, help, feedback, and updates.

## License

MIT. See [LICENSE](LICENSE).
