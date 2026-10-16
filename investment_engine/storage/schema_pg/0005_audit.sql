-- Audit events (architecture Part F/H; docs/tasks/M3-04.md). PostgreSQL only:
-- new M3 stores have no SQLite track (M3 README; M3-01 rule 1). Append-only:
-- UPDATE, DELETE and TRUNCATE are refused, and so is inserting an existing id
-- (whatever the ON CONFLICT clause). The content is the zlib-compressed
-- canonical JSON whose SHA-256 is the event id.

CREATE TABLE audit_events (
    event_id       TEXT NOT NULL PRIMARY KEY,
    at             TIMESTAMPTZ NOT NULL,
    business_at    TIMESTAMPTZ,
    actor_kind     TEXT NOT NULL CHECK (actor_kind IN ('OPERATOR', 'PROCESS')),
    actor_id       TEXT NOT NULL,
    action         TEXT NOT NULL,
    target_type    TEXT NOT NULL,
    target_id      TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    content        BYTEA NOT NULL
);

CREATE INDEX audit_events_by_target ON audit_events (target_type, target_id, at);
CREATE INDEX audit_events_by_time ON audit_events (at);

CREATE TRIGGER audit_events_no_change BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('audit events');

CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('audit events');

CREATE FUNCTION audit_events_no_replace() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.audit_events WHERE event_id = NEW.event_id) THEN
        RAISE EXCEPTION 'audit events are append-only';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER audit_events_no_replace BEFORE INSERT ON audit_events
FOR EACH ROW EXECUTE FUNCTION audit_events_no_replace();
