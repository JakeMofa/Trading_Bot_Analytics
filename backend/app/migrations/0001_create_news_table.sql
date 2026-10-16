BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS news (
  id INTEGER PRIMARY KEY,
  source TEXT,
  headline TEXT,
  link TEXT,
  publication_time TEXT,
  first_seen_time TEXT,
  delay_seconds REAL,
  freshness_category TEXT
);
CREATE INDEX IF NOT EXISTS news_by_first_seen ON news(first_seen_time);
COMMIT;
