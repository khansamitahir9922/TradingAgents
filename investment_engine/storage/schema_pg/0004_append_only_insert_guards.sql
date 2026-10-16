-- Append-only insert guards on PostgreSQL (the M2 B1 guards; docs/tasks/M3-01.md).
-- BEFORE INSERT row triggers fire before conflict arbitration, so an insert of
-- an existing id is refused whatever its ON CONFLICT clause: DO UPDATE can't
-- replace the stored row and DO NOTHING can't silently swallow the attempt.
-- New ids still insert; the stores' identical-append no-op never reaches SQL.

CREATE FUNCTION lineage_records_no_replace() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.lineage_records WHERE lineage_id = NEW.lineage_id) THEN
        RAISE EXCEPTION 'lineage records are append-only';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER lineage_records_no_replace BEFORE INSERT ON lineage_records
FOR EACH ROW EXECUTE FUNCTION lineage_records_no_replace();

CREATE FUNCTION evaluation_records_no_replace() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.evaluation_records WHERE record_id = NEW.record_id) THEN
        RAISE EXCEPTION 'evaluation records are append-only';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER evaluation_records_no_replace BEFORE INSERT ON evaluation_records
FOR EACH ROW EXECUTE FUNCTION evaluation_records_no_replace();
