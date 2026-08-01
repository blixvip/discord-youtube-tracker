CREATE TABLE IF NOT EXISTS captions (
  video_id TEXT PRIMARY KEY,
  language TEXT NOT NULL,
  plain_text TEXT NOT NULL,
  srt_text TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);
