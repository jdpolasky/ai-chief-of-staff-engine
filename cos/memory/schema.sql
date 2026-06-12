-- cos/memory/schema.sql
-- Core schema: facts, episodes, fact_history + FTS5 over facts.content and episodes.
-- Idempotent: safe to re-run on an existing DB (uses IF NOT EXISTS throughout).
--
-- The model is bitemporal: every fact carries a transaction-time window
-- (tx_from / tx_to) so you can ask "what did the system believe on date X."

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- facts: current beliefs. One row per current fact; superseded/retracted facts
-- stay in this table but get tx_to set and retracted flagged accordingly.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS facts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  content         TEXT    NOT NULL,
  category        TEXT    NOT NULL,
  subject_type    TEXT,
  subject_id      TEXT,
  source          TEXT    NOT NULL,
  source_session  INTEGER,
  confidence      REAL    NOT NULL DEFAULT 1.0
                  CHECK (confidence BETWEEN 0.0 AND 1.0),
  valid_from      TEXT    NOT NULL,
  valid_to        TEXT,
  tx_from         TEXT    NOT NULL,
  tx_to           TEXT,
  supersedes_id   INTEGER REFERENCES facts(id),
  retracted       INTEGER NOT NULL DEFAULT 0
                  CHECK (retracted IN (0, 1)),
  tags            TEXT,
  created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
  updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_facts_subject  ON facts(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_valid    ON facts(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_facts_tx       ON facts(tx_from, tx_to);
CREATE INDEX IF NOT EXISTS idx_facts_session  ON facts(source_session)
  WHERE source_session IS NOT NULL;

-- ---------------------------------------------------------------------------
-- episodes: narrative units. Behavior-relevant context, not bare facts.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS episodes (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        TEXT    NOT NULL,
  content      TEXT    NOT NULL,
  occurred_at  TEXT    NOT NULL,
  recorded_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
  session      INTEGER,
  valence      TEXT    CHECK (valence IN ('negative', 'neutral', 'positive')
                              OR valence IS NULL),
  fact_refs    TEXT,
  tags         TEXT
);

CREATE INDEX IF NOT EXISTS idx_episodes_occurred ON episodes(occurred_at);
CREATE INDEX IF NOT EXISTS idx_episodes_session  ON episodes(session)
  WHERE session IS NOT NULL;

-- ---------------------------------------------------------------------------
-- fact_history: append-only bitemporal log of every fact state transition.
-- One row per insert / update / retract / supersede operation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_history (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  fact_id     INTEGER NOT NULL REFERENCES facts(id),
  operation   TEXT    NOT NULL
              CHECK (operation IN ('insert', 'update', 'retract', 'supersede')),
  prev_state  TEXT,
  new_state   TEXT,
  tx_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
  session     INTEGER,
  reason      TEXT
);

CREATE INDEX IF NOT EXISTS idx_fact_history_fact_tx
  ON fact_history(fact_id, tx_at DESC);
CREATE INDEX IF NOT EXISTS idx_fact_history_tx
  ON fact_history(tx_at);

-- ---------------------------------------------------------------------------
-- FTS5: search over facts.content and episodes (title + content).
-- Triggers keep FTS5 in sync with the base tables.
-- ---------------------------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
  content,
  content='facts',
  content_rowid='id',
  tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
  INSERT INTO facts_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
  INSERT INTO facts_fts(facts_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
  INSERT INTO facts_fts(facts_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
  INSERT INTO facts_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
  title, content,
  content='episodes',
  content_rowid='id',
  tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS episodes_ai AFTER INSERT ON episodes BEGIN
  INSERT INTO episodes_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS episodes_ad AFTER DELETE ON episodes BEGIN
  INSERT INTO episodes_fts(episodes_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS episodes_au AFTER UPDATE ON episodes BEGIN
  INSERT INTO episodes_fts(episodes_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
  INSERT INTO episodes_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;
