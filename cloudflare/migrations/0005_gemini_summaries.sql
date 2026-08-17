-- Cached Gemini summaries keep button clicks fast and avoid repeat API charges.
CREATE TABLE IF NOT EXISTS video_summaries (
  video_id TEXT NOT NULL,
  model TEXT NOT NULL,
  summary TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (video_id, model),
  FOREIGN KEY (video_id) REFERENCES videos(video_id)
);

CREATE INDEX IF NOT EXISTS video_summaries_updated
  ON video_summaries(updated_at DESC);
