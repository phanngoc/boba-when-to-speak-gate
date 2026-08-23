-- Postgres schema for SqlThreadStore (use with placeholder="%s").
-- Run once before wiring: SqlThreadStore(psycopg.connect(...), placeholder="%s",
--                                        init_schema=False)

CREATE TABLE IF NOT EXISTS threads (
  thread_id        TEXT PRIMARY KEY,
  is_dm            BOOLEAN,
  muted            BOOLEAN,
  opted_out        BOOLEAN,
  group_size       INTEGER,
  theta_low        DOUBLE PRECISION,
  theta_high       DOUBLE PRECISION,
  last_boba_ts     DOUBLE PRECISION,
  turns_since_boba INTEGER,
  recently_ignored INTEGER,
  state_json       JSONB
);

CREATE TABLE IF NOT EXISTS feedback (
  id        BIGSERIAL PRIMARY KEY,
  thread_id TEXT REFERENCES threads(thread_id) ON DELETE CASCADE,
  positive  BOOLEAN,
  ts        DOUBLE PRECISION
);

-- NOTE (PDPL / data localization): host this database in Vietnam, encrypt at
-- rest, log access, and run a retention/deletion job over threads + feedback.
