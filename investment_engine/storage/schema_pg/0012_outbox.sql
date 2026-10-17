-- The outbox, the shared event log and consumer de-duplication (Law 11; ADR-005; docs/tasks/M4-01.md).
--   outbox:            each process's envelopes, added in the transaction of the change they announce. A row's
--                      content never changes; it is marked published once.
--   event_log:         every published event, once (event_id is unique). Append-only.
--   processed_events:  which consumer applied which event, recorded in the same transaction as the effect.
--   consumer_failures: handler failures, each in its own transaction. Append-only.
-- Nothing is pruned in M4.

CREATE TABLE outbox (
    event_id          TEXT NOT NULL PRIMARY KEY,
    event_type        TEXT NOT NULL,
    schema_version    INTEGER NOT NULL,
    aggregate_type    TEXT NOT NULL,
    aggregate_id      TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL CHECK (aggregate_version >= 1),
    occurred_at       TIMESTAMPTZ NOT NULL,
    recorded_at       TIMESTAMPTZ NOT NULL,
    correlation_id    TEXT NOT NULL,
    causation_id      TEXT,
    payload           TEXT NOT NULL,
    writer            TEXT NOT NULL CHECK (writer IN ('core-engine', 'execution-worker')),
    published_at      TIMESTAMPTZ,
    UNIQUE (aggregate_type, aggregate_id, aggregate_version)
);

CREATE INDEX outbox_unpublished ON outbox (writer, aggregate_type, aggregate_id, aggregate_version)
WHERE published_at IS NULL;

CREATE TABLE event_log (
    sequence          BIGSERIAL PRIMARY KEY,
    event_id          TEXT NOT NULL UNIQUE,
    event_type        TEXT NOT NULL,
    schema_version    INTEGER NOT NULL,
    aggregate_type    TEXT NOT NULL,
    aggregate_id      TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL,
    occurred_at       TIMESTAMPTZ NOT NULL,
    recorded_at       TIMESTAMPTZ NOT NULL,
    correlation_id    TEXT NOT NULL,
    causation_id      TEXT,
    payload           TEXT NOT NULL,
    published_at      TIMESTAMPTZ NOT NULL,
    UNIQUE (aggregate_type, aggregate_id, aggregate_version)
);

CREATE TABLE processed_events (
    consumer          TEXT NOT NULL,
    event_id          TEXT NOT NULL REFERENCES event_log (event_id),
    aggregate_type    TEXT NOT NULL,
    aggregate_id      TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL,
    outcome           TEXT NOT NULL CHECK (outcome IN ('applied', 'unhandled')),
    processed_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer, event_id),
    UNIQUE (consumer, aggregate_type, aggregate_id, aggregate_version)
);

CREATE TABLE consumer_failures (
    consumer  TEXT NOT NULL,
    event_id  TEXT NOT NULL,
    error     TEXT NOT NULL,
    failed_at TIMESTAMPTZ NOT NULL
);

CREATE FUNCTION outbox_publish_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF (NEW.event_id, NEW.event_type, NEW.schema_version, NEW.aggregate_type, NEW.aggregate_id,
        NEW.aggregate_version, NEW.occurred_at, NEW.recorded_at, NEW.correlation_id, NEW.causation_id, NEW.payload,
        NEW.writer)
       IS DISTINCT FROM
       (OLD.event_id, OLD.event_type, OLD.schema_version, OLD.aggregate_type, OLD.aggregate_id,
        OLD.aggregate_version, OLD.occurred_at, OLD.recorded_at, OLD.correlation_id, OLD.causation_id, OLD.payload,
        OLD.writer)
       OR OLD.published_at IS NOT NULL OR NEW.published_at IS NULL THEN
        RAISE EXCEPTION 'an outbox row only gets its published mark, once (append-only history)';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER outbox_publish_only BEFORE UPDATE ON outbox FOR EACH ROW EXECUTE FUNCTION outbox_publish_only();
CREATE TRIGGER outbox_no_delete BEFORE DELETE ON outbox FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('outbox');
CREATE TRIGGER outbox_no_truncate BEFORE TRUNCATE ON outbox
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('outbox');
CREATE TRIGGER event_log_no_change BEFORE UPDATE OR DELETE ON event_log
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('event log');
CREATE TRIGGER event_log_no_truncate BEFORE TRUNCATE ON event_log
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('event log');
CREATE TRIGGER processed_events_no_change BEFORE UPDATE OR DELETE ON processed_events
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('processed events');
CREATE TRIGGER processed_events_no_truncate BEFORE TRUNCATE ON processed_events
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('processed events');
CREATE TRIGGER consumer_failures_no_change BEFORE UPDATE OR DELETE ON consumer_failures
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('consumer failures');
CREATE TRIGGER consumer_failures_no_truncate BEFORE TRUNCATE ON consumer_failures
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('consumer failures');
