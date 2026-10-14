-- Append-only insert guards (Codex M2 review B1; owner-approved scope for M2-11b).
-- With recursive triggers off (the connection default), SQLite's
-- replace-on-conflict resolution removes a conflicting row without firing the
-- DELETE triggers of 0002/0003, so a stored record could be overwritten. These
-- guards refuse any insert whose id already exists, before conflict resolution
-- runs, whatever conflict clause the statement uses (replace, ignore or an
-- upsert). New ids still insert; the stores' identical-append no-op never
-- reaches SQL.
-- Trigger bodies are SQLite syntax; the M3 move to PostgreSQL rewrites them.

CREATE TRIGGER lineage_records_no_replace BEFORE INSERT ON lineage_records
WHEN EXISTS (SELECT 1 FROM lineage_records WHERE lineage_id = NEW.lineage_id)
BEGIN
    SELECT RAISE(ABORT, 'lineage records are append-only');
END;

CREATE TRIGGER evaluation_records_no_replace BEFORE INSERT ON evaluation_records
WHEN EXISTS (SELECT 1 FROM evaluation_records WHERE record_id = NEW.record_id)
BEGIN
    SELECT RAISE(ABORT, 'evaluation records are append-only');
END;
