-- Evaluation run records (docs/tasks/M2-11.md rule 5; M2-11b). Append-only:
-- each row is one immutable walk-forward EvaluationRecord, keyed by the
-- SHA-256 of its canonical content, which is stored zlib-compressed. The
-- triggers refuse UPDATE and DELETE. Trigger bodies are SQLite syntax; the
-- M3 move to PostgreSQL rewrites them as functions.

CREATE TABLE evaluation_records (
    record_id     TEXT NOT NULL PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    as_of         TEXT NOT NULL,
    content       BLOB NOT NULL
);

CREATE INDEX evaluation_records_by_instrument ON evaluation_records (instrument_id, as_of);

CREATE TRIGGER evaluation_records_no_update BEFORE UPDATE ON evaluation_records
BEGIN
    SELECT RAISE(ABORT, 'evaluation records are append-only');
END;

CREATE TRIGGER evaluation_records_no_delete BEFORE DELETE ON evaluation_records
BEGIN
    SELECT RAISE(ABORT, 'evaluation records are append-only');
END;
