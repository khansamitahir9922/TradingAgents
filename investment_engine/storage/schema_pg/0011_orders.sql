-- Orders (architecture G3; Laws 8, 10, 14; ADR-004; docs/tasks/M4-00.md). PostgreSQL only.
--   order_edges:      G3 exactly, with each edge's only writer (mirrors oms/order_states.py; a test compares them).
--   orders:           one row per order. Its terms never change; state, version, filled quantity, average
--                     price and broker order id change only by compare-and-set (version + 1).
--   order_versions:   the append-only log of every version: create, each state edge, each fill-accounting write.
--   fills, broker_anomalies, gate_decisions, cancel_requests, cancel_progress: append-only.
-- Every write transaction sets investment_engine.process_role with SET LOCAL; the triggers below refuse a row
-- written by any other role, and an unset or unknown role fails closed. This is a consistency check, not
-- authentication: any client can set the variable (ADR-002 section 5; enforced by OS users from M7).

CREATE TABLE order_edges (
    from_state TEXT,
    to_state   TEXT NOT NULL,
    owner      TEXT NOT NULL CHECK (owner IN ('core-engine', 'execution-worker')),
    UNIQUE (from_state, to_state)
);

INSERT INTO order_edges VALUES
    (NULL, 'NEW', 'core-engine'),
    ('NEW', 'GATE_REJECTED', 'execution-worker'), ('NEW', 'SUBMITTING', 'execution-worker'),
    ('SUBMITTING', 'SUBMITTED', 'execution-worker'), ('SUBMITTING', 'REJECTED', 'execution-worker'),
    ('SUBMITTING', 'EXPIRED', 'execution-worker'), ('SUBMITTING', 'UNKNOWN', 'execution-worker'),
    ('SUBMITTED', 'PARTIALLY_FILLED', 'execution-worker'), ('SUBMITTED', 'FILLED', 'execution-worker'),
    ('SUBMITTED', 'CANCEL_PENDING', 'execution-worker'), ('SUBMITTED', 'REJECTED', 'execution-worker'),
    ('SUBMITTED', 'EXPIRED', 'execution-worker'),
    ('PARTIALLY_FILLED', 'FILLED', 'execution-worker'), ('PARTIALLY_FILLED', 'CANCEL_PENDING', 'execution-worker'),
    ('CANCEL_PENDING', 'CANCELLED', 'execution-worker'), ('CANCEL_PENDING', 'PARTIALLY_FILLED', 'execution-worker'),
    ('CANCEL_PENDING', 'FILLED', 'execution-worker'),
    ('UNKNOWN', 'SUBMITTED', 'execution-worker'), ('UNKNOWN', 'PARTIALLY_FILLED', 'execution-worker'),
    ('UNKNOWN', 'FILLED', 'execution-worker'), ('UNKNOWN', 'CANCELLED', 'execution-worker'),
    ('UNKNOWN', 'REJECTED', 'execution-worker'), ('UNKNOWN', 'EXPIRED', 'execution-worker');

CREATE TABLE orders (
    order_id             TEXT NOT NULL PRIMARY KEY,
    client_order_id      TEXT NOT NULL UNIQUE,
    intent_id            TEXT NOT NULL REFERENCES intents (intent_id),
    intent_version       INTEGER NOT NULL,
    intent_content_id    TEXT NOT NULL,
    position_fingerprint TEXT NOT NULL,
    account_id           TEXT NOT NULL REFERENCES accounts (account_id),
    account_kind         TEXT NOT NULL CHECK (account_kind IN ('RESEARCH', 'PAPER')),
    instrument_id        TEXT NOT NULL,
    side                 TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity             NUMERIC NOT NULL CHECK (quantity > 0),
    order_type           TEXT NOT NULL,
    limit_price          NUMERIC NOT NULL CHECK (limit_price > 0),
    time_in_force        TEXT NOT NULL,
    target_session       DATE NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL,
    recorded_at          TIMESTAMPTZ NOT NULL,
    content              BYTEA NOT NULL,
    state                TEXT NOT NULL,
    aggregate_version    INTEGER NOT NULL CHECK (aggregate_version >= 1),
    filled_qty           NUMERIC NOT NULL CHECK (filled_qty >= 0),
    avg_price            NUMERIC,
    broker_order_id      TEXT,
    UNIQUE (intent_id, intent_version),
    FOREIGN KEY (intent_id, intent_version) REFERENCES intent_versions (intent_id, version),
    CHECK (filled_qty <= quantity)
);

CREATE INDEX orders_by_account ON orders (account_id, state);
CREATE INDEX orders_by_state ON orders (state);

CREATE TABLE order_versions (
    order_id          TEXT NOT NULL REFERENCES orders (order_id),
    aggregate_version INTEGER NOT NULL CHECK (aggregate_version >= 1),
    from_state        TEXT,
    to_state          TEXT NOT NULL,
    filled_qty        NUMERIC NOT NULL,
    at                TIMESTAMPTZ NOT NULL,
    recorded_at       TIMESTAMPTZ NOT NULL,
    by_role           TEXT NOT NULL,
    reason            TEXT NOT NULL,
    broker_ref        TEXT,
    PRIMARY KEY (order_id, aggregate_version)
);

CREATE TABLE fills (
    fill_id        TEXT NOT NULL PRIMARY KEY,
    order_id       TEXT NOT NULL REFERENCES orders (order_id),
    broker_fill_id TEXT NOT NULL UNIQUE,
    quantity       NUMERIC NOT NULL CHECK (quantity > 0),
    price          NUMERIC NOT NULL CHECK (price > 0),
    fee            NUMERIC NOT NULL CHECK (fee >= 0),
    currency       TEXT NOT NULL,
    executed_at    TIMESTAMPTZ NOT NULL,
    delivered_at   TIMESTAMPTZ NOT NULL,
    recorded_at    TIMESTAMPTZ NOT NULL,
    provenance     TEXT NOT NULL,
    at_version     INTEGER NOT NULL
);

CREATE INDEX fills_by_order ON fills (order_id, recorded_at);

CREATE TABLE broker_anomalies (
    order_id    TEXT NOT NULL REFERENCES orders (order_id),
    sequence    INTEGER NOT NULL CHECK (sequence >= 1),
    kind        TEXT NOT NULL,
    detail      TEXT NOT NULL,
    at          TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    broker_ref  TEXT NOT NULL,
    at_version  INTEGER NOT NULL,
    PRIMARY KEY (order_id, sequence)
);

CREATE TABLE gate_decisions (
    order_id   TEXT NOT NULL REFERENCES orders (order_id),
    attempt    INTEGER NOT NULL CHECK (attempt >= 1),
    passed     BOOLEAN NOT NULL,
    checks     BYTEA NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL,
    inputs     TEXT NOT NULL,
    at_version INTEGER NOT NULL,
    PRIMARY KEY (order_id, attempt)
);

CREATE TABLE cancel_requests (
    cancel_id    TEXT NOT NULL PRIMARY KEY,
    order_id     TEXT NOT NULL REFERENCES orders (order_id),
    content      BYTEA NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE cancel_progress (
    cancel_id   TEXT NOT NULL REFERENCES cancel_requests (cancel_id),
    version     INTEGER NOT NULL CHECK (version >= 1),
    progress    TEXT NOT NULL CHECK (progress IN ('REQUESTED', 'SENDING', 'SENT', 'CLOSED')),
    attempt     INTEGER NOT NULL CHECK (attempt >= 0),
    outcome     TEXT CHECK (outcome IN ('CANCELLED', 'TOO_LATE', 'NOTHING_TO_CANCEL')),
    received_at TIMESTAMPTZ,
    at          TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (cancel_id, version),
    CHECK ((progress = 'CLOSED') = (outcome IS NOT NULL))
);

CREATE FUNCTION ie_require_role(expected TEXT, what TEXT) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE
    role TEXT := current_setting('investment_engine.process_role', true);
BEGIN
    IF role IS NULL OR role = '' OR role NOT IN ('core-engine', 'execution-worker') THEN
        RAISE EXCEPTION 'order store: no valid process role is set for % (fails closed)', what;
    END IF;
    IF role <> expected THEN
        RAISE EXCEPTION 'order store: % is written only by the %, not the %', what, expected, role;
    END IF;
END;
$$;

CREATE FUNCTION orders_insert_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    PERFORM ie_require_role('core-engine', 'order creation');
    IF NEW.state <> 'NEW' OR NEW.aggregate_version <> 1 OR NEW.filled_qty <> 0 OR NEW.avg_price IS NOT NULL
       OR NEW.broker_order_id IS NOT NULL THEN
        RAISE EXCEPTION 'order store: an order is created NEW at version 1 with nothing filled';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION orders_update_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    PERFORM ie_require_role('execution-worker', 'an order update');
    IF (NEW.order_id, NEW.client_order_id, NEW.intent_id, NEW.intent_version, NEW.intent_content_id,
        NEW.position_fingerprint, NEW.account_id, NEW.account_kind, NEW.instrument_id, NEW.side, NEW.quantity,
        NEW.order_type, NEW.limit_price, NEW.time_in_force, NEW.target_session, NEW.created_at, NEW.recorded_at,
        NEW.content)
       IS DISTINCT FROM
       (OLD.order_id, OLD.client_order_id, OLD.intent_id, OLD.intent_version, OLD.intent_content_id,
        OLD.position_fingerprint, OLD.account_id, OLD.account_kind, OLD.instrument_id, OLD.side, OLD.quantity,
        OLD.order_type, OLD.limit_price, OLD.time_in_force, OLD.target_session, OLD.created_at, OLD.recorded_at,
        OLD.content) THEN
        RAISE EXCEPTION 'order store: an order''s terms are immutable (append-only history)';
    END IF;
    IF NEW.aggregate_version <> OLD.aggregate_version + 1 THEN
        RAISE EXCEPTION 'order store: an order moves forward by exactly one version (compare-and-set)';
    END IF;
    IF NEW.filled_qty < OLD.filled_qty THEN
        RAISE EXCEPTION 'order store: filled quantity never decreases';
    END IF;
    IF OLD.broker_order_id IS NOT NULL AND NEW.broker_order_id IS DISTINCT FROM OLD.broker_order_id THEN
        RAISE EXCEPTION 'order store: the broker order id is set once';
    END IF;
    IF NEW.state = OLD.state THEN
        IF NEW.filled_qty <= OLD.filled_qty THEN
            RAISE EXCEPTION 'order store: a write without a state edge must record a fill';
        END IF;
    ELSIF NOT EXISTS (SELECT 1 FROM order_edges WHERE from_state = OLD.state AND to_state = NEW.state) THEN
        RAISE EXCEPTION 'order store: % -> % is not an order transition (G3)', OLD.state, NEW.state;
    END IF;
    IF NEW.state = 'FILLED' AND NEW.filled_qty <> NEW.quantity THEN
        RAISE EXCEPTION 'order store: FILLED means the whole quantity is filled';
    END IF;
    IF NEW.state = 'PARTIALLY_FILLED' AND NOT (NEW.filled_qty > 0 AND NEW.filled_qty < NEW.quantity) THEN
        RAISE EXCEPTION 'order store: PARTIALLY_FILLED means part of the quantity is filled';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION order_versions_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE
    owner TEXT;
BEGIN
    IF NEW.from_state IS NOT DISTINCT FROM NEW.to_state THEN
        owner := 'execution-worker';  -- a fill-accounting write
    ELSE
        SELECT e.owner INTO owner FROM order_edges e
        WHERE e.from_state IS NOT DISTINCT FROM NEW.from_state AND e.to_state = NEW.to_state;
        IF owner IS NULL THEN
            RAISE EXCEPTION 'order store: % -> % is not an order transition (G3)', NEW.from_state, NEW.to_state;
        END IF;
    END IF;
    PERFORM ie_require_role(owner, 'this order version');
    RETURN NEW;
END;
$$;

CREATE FUNCTION ie_execution_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    PERFORM ie_require_role('execution-worker', TG_TABLE_NAME);
    RETURN NEW;
END;
$$;

CREATE FUNCTION cancel_requests_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    PERFORM ie_require_role('core-engine', 'a cancel request');
    RETURN NEW;
END;
$$;

CREATE FUNCTION cancel_progress_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF NEW.progress = 'REQUESTED' THEN
        IF NEW.version <> 1 THEN
            RAISE EXCEPTION 'order store: REQUESTED is a cancel request''s first version only';
        END IF;
        PERFORM ie_require_role('core-engine', 'a cancel request');
    ELSE
        PERFORM ie_require_role('execution-worker', 'cancel progress');
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER orders_insert_guard BEFORE INSERT ON orders FOR EACH ROW EXECUTE FUNCTION orders_insert_guard();
CREATE TRIGGER orders_update_guard BEFORE UPDATE ON orders FOR EACH ROW EXECUTE FUNCTION orders_update_guard();
CREATE TRIGGER orders_no_delete BEFORE DELETE ON orders FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('orders');
CREATE TRIGGER orders_no_truncate BEFORE TRUNCATE ON orders
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('orders');

CREATE TRIGGER order_versions_guard BEFORE INSERT ON order_versions
FOR EACH ROW EXECUTE FUNCTION order_versions_guard();
CREATE TRIGGER fills_role BEFORE INSERT ON fills FOR EACH ROW EXECUTE FUNCTION ie_execution_only();
CREATE TRIGGER broker_anomalies_role BEFORE INSERT ON broker_anomalies
FOR EACH ROW EXECUTE FUNCTION ie_execution_only();
CREATE TRIGGER gate_decisions_role BEFORE INSERT ON gate_decisions FOR EACH ROW EXECUTE FUNCTION ie_execution_only();
CREATE TRIGGER cancel_requests_role BEFORE INSERT ON cancel_requests
FOR EACH ROW EXECUTE FUNCTION cancel_requests_guard();
CREATE TRIGGER cancel_progress_role BEFORE INSERT ON cancel_progress
FOR EACH ROW EXECUTE FUNCTION cancel_progress_guard();

CREATE TRIGGER order_edges_no_change BEFORE INSERT OR UPDATE OR DELETE ON order_edges
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('order edges');
CREATE TRIGGER order_edges_no_truncate BEFORE TRUNCATE ON order_edges
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('order edges');
CREATE TRIGGER order_versions_no_change BEFORE UPDATE OR DELETE ON order_versions
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('order versions');
CREATE TRIGGER order_versions_no_truncate BEFORE TRUNCATE ON order_versions
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('order versions');
CREATE TRIGGER fills_no_change BEFORE UPDATE OR DELETE ON fills
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('fills');
CREATE TRIGGER fills_no_truncate BEFORE TRUNCATE ON fills FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('fills');
CREATE TRIGGER broker_anomalies_no_change BEFORE UPDATE OR DELETE ON broker_anomalies
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('broker anomalies');
CREATE TRIGGER broker_anomalies_no_truncate BEFORE TRUNCATE ON broker_anomalies
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('broker anomalies');
CREATE TRIGGER gate_decisions_no_change BEFORE UPDATE OR DELETE ON gate_decisions
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('gate decisions');
CREATE TRIGGER gate_decisions_no_truncate BEFORE TRUNCATE ON gate_decisions
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('gate decisions');
CREATE TRIGGER cancel_requests_no_change BEFORE UPDATE OR DELETE ON cancel_requests
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('cancel requests');
CREATE TRIGGER cancel_requests_no_truncate BEFORE TRUNCATE ON cancel_requests
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('cancel requests');
CREATE TRIGGER cancel_progress_no_change BEFORE UPDATE OR DELETE ON cancel_progress
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('cancel progress');
CREATE TRIGGER cancel_progress_no_truncate BEFORE TRUNCATE ON cancel_progress
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('cancel progress');
