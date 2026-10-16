-- Evaluation run records on PostgreSQL (docs/tasks/M2-11b.md, M3-01.md).
-- Append-only, like lineage records.

CREATE TABLE evaluation_records (
    record_id     TEXT NOT NULL PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    as_of         TIMESTAMPTZ NOT NULL,
    content       BYTEA NOT NULL
);

CREATE INDEX evaluation_records_by_instrument ON evaluation_records (instrument_id, as_of);

CREATE TRIGGER evaluation_records_no_change BEFORE UPDATE OR DELETE ON evaluation_records
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('evaluation records');

CREATE TRIGGER evaluation_records_no_truncate BEFORE TRUNCATE ON evaluation_records
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('evaluation records');
