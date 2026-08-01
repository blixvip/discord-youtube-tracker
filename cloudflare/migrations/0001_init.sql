CREATE TABLE IF NOT EXISTS routes (
  youtube_channel_id TEXT NOT NULL,
  youtube_channel_name TEXT NOT NULL,
  discord_channel_id TEXT NOT NULL,
  last_video_id TEXT,
  PRIMARY KEY (youtube_channel_id, discord_channel_id)
);

CREATE INDEX IF NOT EXISTS routes_discord_channel
  ON routes(discord_channel_id);

CREATE TABLE IF NOT EXISTS poll_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  cursor INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO poll_state (id, cursor) VALUES (1, 0);

CREATE TABLE IF NOT EXISTS pending_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  discord_channel_id TEXT NOT NULL,
  youtube_channel_id TEXT NOT NULL,
  youtube_channel_name TEXT NOT NULL,
  video_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  published TEXT,
  thumbnail_url TEXT,
  UNIQUE(discord_channel_id, video_id)
);
