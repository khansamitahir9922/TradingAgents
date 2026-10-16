-- Lineage records on PostgreSQL (docs/tasks/M2-07.md, M3-01.md). Append-only:
-- UPDATE and DELETE are refused per row, TRUNCATE per statement. The content
-- is the same zlib-compressed canonical JSON as on SQLite.

CREATE FUNCTION ie_refuse_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    RAISE EXCEPTION '% are append-only', TG_ARGV[0];
END;
$$;

CREATE TABLE lineage_records (
    lineage_id    TEXT NOT NULL PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    generated_at  TIMESTAMPTZ NOT NULL,
    content       BYTEA NOT NULL
);

CREATE INDEX lineage_records_by_instrument ON lineage_records (instrument_id, generated_at);

CREATE TRIGGER lineage_records_no_change BEFORE UPDATE OR DELETE ON lineage_records
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('lineage records');

CREATE TRIGGER lineage_records_no_truncate BEFORE TRUNCATE ON lineage_records
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('lineage records');
