-- Lineage records (architecture Part H; docs/tasks/M2-07.md). Append-only:
-- each row is one immutable LineageRecord, keyed by the SHA-256 of its
-- canonical content, which is stored zlib-compressed. The triggers refuse
-- UPDATE and DELETE (history is never overwritten). Trigger bodies are
-- SQLite syntax; the M3 move to PostgreSQL rewrites them as functions.

CREATE TABLE lineage_records (
    lineage_id    TEXT NOT NULL PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    generated_at  TEXT NOT NULL,
    content       BLOB NOT NULL
);

CREATE INDEX lineage_records_by_instrument ON lineage_records (instrument_id, generated_at);

CREATE TRIGGER lineage_records_no_update BEFORE UPDATE ON lineage_records
BEGIN
    SELECT RAISE(ABORT, 'lineage records are append-only');
END;

CREATE TRIGGER lineage_records_no_delete BEFORE DELETE ON lineage_records
BEGIN
    SELECT RAISE(ABORT, 'lineage records are append-only');
END;
