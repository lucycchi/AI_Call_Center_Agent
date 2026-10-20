-- The operations database (docs/ARCHITECTURE.md section 4.2). The nightly reset never touches it.
CREATE TABLE IF NOT EXISTS visitors (
  visitor_id TEXT PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'public', first_seen TEXT NOT NULL, client_address TEXT);
CREATE TABLE IF NOT EXISTS conversations (
  conversation_id TEXT PRIMARY KEY, visitor_id TEXT NOT NULL REFERENCES visitors(visitor_id), customer_id TEXT,
  active_flow TEXT, flow_state TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL,
  last_message_at TEXT NOT NULL, closed_at TEXT);
CREATE TABLE IF NOT EXISTS messages (
  message_id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
  role TEXT NOT NULL CHECK (role IN ('caller', 'agent')), text_masked TEXT NOT NULL, created_at TEXT NOT NULL,
  request_id TEXT, first_sentence_ms INTEGER, full_reply_ms INTEGER, cost_microdollars INTEGER);
CREATE TABLE IF NOT EXISTS sentences (
  sentence_id INTEGER PRIMARY KEY, message_id INTEGER NOT NULL REFERENCES messages(message_id), text_masked TEXT NOT NULL,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS receipts (
  message_id INTEGER PRIMARY KEY REFERENCES messages(message_id), safety_result TEXT, route TEXT, passages TEXT,
  excluded TEXT, db_action TEXT, outcome_label TEXT);
CREATE TABLE IF NOT EXISTS tickets (
  ticket_id INTEGER PRIMARY KEY, conversation_id TEXT REFERENCES conversations(conversation_id), appointment_id INTEGER,
  who TEXT, wants TEXT, tried TEXT, constraints TEXT, mood TEXT, reason_tag TEXT NOT NULL,
  priority INTEGER NOT NULL CHECK (priority IN (0, 1, 2)), status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL,
  closed_at TEXT);
CREATE TABLE IF NOT EXISTS ticket_tags (
  ticket_id INTEGER NOT NULL REFERENCES tickets(ticket_id), tag TEXT NOT NULL, PRIMARY KEY (ticket_id, tag));
CREATE TABLE IF NOT EXISTS ticket_messages (
  ticket_id INTEGER NOT NULL REFERENCES tickets(ticket_id), message_id INTEGER NOT NULL REFERENCES messages(message_id),
  PRIMARY KEY (ticket_id, message_id));
CREATE TABLE IF NOT EXISTS flags (
  flag_id INTEGER PRIMARY KEY, message_id INTEGER NOT NULL REFERENCES messages(message_id), correction TEXT,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS spend (
  spend_id INTEGER PRIMARY KEY, visitor_id TEXT NOT NULL, pool TEXT NOT NULL, day TEXT NOT NULL,
  microdollars INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS alerts (alert_id INTEGER PRIMARY KEY, kind TEXT NOT NULL, detail TEXT, sent_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS job_runs (
  run_id INTEGER PRIMARY KEY, job TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS model_calls (
  call_id INTEGER PRIMARY KEY, message_id INTEGER, purpose TEXT NOT NULL, model_id TEXT NOT NULL, sdk_version TEXT,
  settings TEXT, input_tokens INTEGER, output_tokens INTEGER, ms INTEGER, microdollars INTEGER);
CREATE TABLE IF NOT EXISTS events (
  event_id INTEGER PRIMARY KEY, conversation_id TEXT, kind TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS messages_by_conversation ON messages (conversation_id);
CREATE INDEX IF NOT EXISTS sentences_by_message ON sentences (message_id);
CREATE INDEX IF NOT EXISTS spend_by_day ON spend (day, pool);
