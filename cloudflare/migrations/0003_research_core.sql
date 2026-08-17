-- Production research core. Additive: preserves every existing route, checkpoint, queue item, and caption.
ALTER TABLE routes ADD COLUMN guild_id TEXT;
ALTER TABLE routes ADD COLUMN label TEXT;
ALTER TABLE routes ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1;
ALTER TABLE routes ADD COLUMN include_shorts INTEGER NOT NULL DEFAULT 1;
ALTER TABLE routes ADD COLUMN include_livestreams INTEGER NOT NULL DEFAULT 1;
ALTER TABLE routes ADD COLUMN include_premieres INTEGER NOT NULL DEFAULT 1;
ALTER TABLE routes ADD COLUMN added_at TEXT;
ALTER TABLE routes ADD COLUMN last_checked_at TEXT;
ALTER TABLE routes ADD COLUMN notification_preferences TEXT;

CREATE INDEX IF NOT EXISTS routes_guild_enabled
  ON routes(guild_id, enabled);

ALTER TABLE pending_posts ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pending_posts ADD COLUMN next_attempt_at TEXT;
ALTER TABLE pending_posts ADD COLUMN last_error TEXT;
ALTER TABLE pending_posts ADD COLUMN dead_at TEXT;

CREATE TABLE IF NOT EXISTS videos (
  video_id TEXT PRIMARY KEY,
  youtube_channel_id TEXT NOT NULL,
  youtube_channel_name TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  published TEXT,
  thumbnail_url TEXT,
  content_type TEXT NOT NULL DEFAULT 'video',
  first_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS videos_published
  ON videos(published DESC);

CREATE TABLE IF NOT EXISTS notifications (
  guild_id TEXT NOT NULL,
  discord_channel_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN (
    'discovered', 'metadata_fetched', 'transcript_pending', 'analysis_pending',
    'sending', 'notification_sent', 'analysis_ready', 'failed',
    'permanently_unavailable'
  )),
  discord_message_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  discovered_at TEXT NOT NULL,
  sent_at TEXT,
  updated_at TEXT NOT NULL,
  last_error TEXT,
  PRIMARY KEY (guild_id, discord_channel_id, video_id),
  FOREIGN KEY (video_id) REFERENCES videos(video_id)
);

CREATE INDEX IF NOT EXISTS notifications_state_updated
  ON notifications(state, updated_at);
CREATE UNIQUE INDEX IF NOT EXISTS notifications_destination_video
  ON notifications(discord_channel_id, video_id);

CREATE TABLE IF NOT EXISTS transcripts (
  video_id TEXT NOT NULL,
  language TEXT NOT NULL,
  provider TEXT NOT NULL,
  source_type TEXT NOT NULL,
  is_auto_generated INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL CHECK (state IN (
    'queued', 'waiting_for_captions', 'retrieving', 'ready', 'unavailable',
    'blocked', 'retrying', 'failed'
  )),
  failure_reason TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  plain_text TEXT,
  srt_text TEXT,
  retrieved_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (video_id, language)
);

CREATE INDEX IF NOT EXISTS transcripts_state_schedule
  ON transcripts(state, next_attempt_at);

CREATE TABLE IF NOT EXISTS transcript_segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  language TEXT NOT NULL,
  segment_index INTEGER NOT NULL,
  start_seconds REAL NOT NULL,
  duration_seconds REAL NOT NULL,
  text TEXT NOT NULL,
  provider TEXT NOT NULL,
  confidence REAL,
  retrieved_at TEXT NOT NULL,
  UNIQUE(video_id, language, segment_index),
  FOREIGN KEY (video_id, language) REFERENCES transcripts(video_id, language)
);

CREATE INDEX IF NOT EXISTS transcript_segments_video_time
  ON transcript_segments(video_id, start_seconds);

CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_key TEXT NOT NULL UNIQUE,
  type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  guild_id TEXT,
  status TEXT NOT NULL CHECK (status IN (
    'queued', 'running', 'retrying', 'completed', 'failed', 'dead'
  )),
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 6,
  scheduled_at TEXT NOT NULL,
  locked_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS jobs_ready
  ON jobs(status, scheduled_at);

CREATE TABLE IF NOT EXISTS health_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO transcripts (
  video_id, language, provider, source_type, is_auto_generated, state,
  plain_text, srt_text, retrieved_at, created_at, updated_at
)
SELECT video_id, language, 'legacy-python', 'youtube_captions', 0, 'ready',
       plain_text, srt_text, fetched_at, fetched_at, fetched_at
FROM captions;
