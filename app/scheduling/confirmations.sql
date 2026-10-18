-- Added to the scheduling database by the agent; the provided tables are untouched (architecture refinements (D36)).
-- The nightly reset recreates it empty.
CREATE TABLE IF NOT EXISTS agent_confirmations (
  confirmation_id TEXT PRIMARY KEY,
  result TEXT NOT NULL,       -- JSON of the first result for this confirmation
  created_at TEXT NOT NULL
);
