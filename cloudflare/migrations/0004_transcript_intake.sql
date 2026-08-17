-- Durable message intake for the always-on #youtube-transcripts channel.
CREATE TABLE IF NOT EXISTS transcript_intake_requests (
  message_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
    'queued', 'running', 'retrying', 'completed', 'failed'
  )),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (message_id, video_id)
);

CREATE INDEX IF NOT EXISTS transcript_intake_due
  ON transcript_intake_requests(status, next_attempt_at, created_at);
