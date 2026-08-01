# Discord YouTuber Tracker

A Discord bot that watches YouTube creators, routes new uploads into organized Discord channels, and optionally fetches Reddit memes.

## Features

- Watches public YouTube Atom feeds without a YouTube API key.
- Creates an `AI Video Feeds` category, an `everything` channel, and a channel for each creator.
- Routes every upload to both `everything` and the matching creator channel.
- Polls each creator once every five minutes, even with multiple Discord destinations.
- Posts linked embeds with the creator, publish time, thumbnail, and YouTube button.
- Persists checkpoints in a local `subscriptions.json` file to catch up after restarts.
- Keeps Reddit meme commands available when Reddit credentials are configured.

## Requirements

- Python 3.11+
- A Discord application and bot token
- Bot permissions: View Channels, Send Messages, Embed Links, Read Message History, Manage Channels, and Use Application Commands
- Reddit API credentials only if meme commands are needed

## Setup

```bash
git clone https://github.com/wasely/discord-youtuber-tracker.git
cd discord-youtuber-tracker
python -m venv .venv
```

Activate the environment, then install dependencies:

```bash
python -m pip install -r requirements.txt
```

Copy `env_example.txt` to `.env` and fill in the required token:

```env
DISCORD_TOKEN=your_discord_bot_token_here
SUBSCRIPTIONS_FILE=./subscriptions.json
SUBSCRIPTIONS_SEED_B64=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
```

Never commit `.env`. If a token is exposed, rotate it in the Discord Developer Portal.

Run the bot:

```bash
python run.py
```

Docker files are included for containerized operation:

```bash
docker compose up --build -d
```

## Free cloud deployment

Northflank's free Developer Sandbox can run this bot continuously from the public
GitHub repository. Create a combined service from the Dockerfile with no public
ports, then:

1. Add `DISCORD_TOKEN` as a secret runtime variable.
2. Attach a persistent volume at `/app/data`.
3. Set `SUBSCRIPTIONS_SEED_B64` once to migrate an existing local
   `subscriptions.json`; it is used only when the volume is empty.
4. Keep one service instance. Pause or resume it from the service header.

The image writes checkpoints to `/app/data/subscriptions.json`. Never commit the
token, seed, or runtime data.

## Commands

YouTube management commands require Manage Server permission.

| Command | Purpose |
| --- | --- |
| `/addchannel <YouTube URL, handle, or channel ID>` | Create destinations and watch a creator |
| `/removechannel <YouTube URL, handle, or channel ID>` | Stop routing a creator to the current Discord channel |
| `/channels` | List creators watched in the current Discord channel |
| `/checkchannels` | Run an immediate check for the current Discord channel |
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
```

The offline suite covers configuration, Reddit behavior, Discord commands, YouTube feed parsing, subscription persistence, embeds, and deduplicated polling.

## Project layout

- `discord_bot.py` — Discord commands, feed routing, embeds, and polling
- `youtube_client.py` — YouTube channel resolution, Atom parsing, and subscription storage
- `reddit_client.py` — optional Reddit meme client
- `config.py` — environment and bot settings
- `run.py` — application entry point
- `docs/` — implementation research notes
