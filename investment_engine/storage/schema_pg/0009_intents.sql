-- Order intents (architecture G2; ADR-004; docs/tasks/M3-09.md). PostgreSQL
-- only (M3 README; M3-01 rule 1).
--   intents:            one aggregate per intent id: the compare-and-set counter
--                       (it only ever moves up by one) and the latest version.
--   intent_versions:    one row per immutable version. Its material and
--                       reference columns and its content never change (Law 12);
--                       state, decisions, approval fields and lineage id change
--                       only through the store's compare-and-set transitions.
--   intent_transitions: the append-only log of every move.
-- Nothing is deleted or truncated.

CREATE TABLE intents (
    intent_id         TEXT NOT NULL PRIMARY KEY,
    account_id        TEXT NOT NULL REFERENCES accounts (account_id),
    instrument_id     TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL CHECK (aggregate_version >= 1),
    latest_version    INTEGER NOT NULL CHECK (latest_version >= 1)
);

CREATE TABLE intent_versions (
    intent_id            TEXT NOT NULL REFERENCES intents (intent_id),
    version              INTEGER NOT NULL CHECK (version >= 1),
    side                 TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity             NUMERIC NOT NULL CHECK (quantity > 0),
    order_type           TEXT NOT NULL,
    limit_price          NUMERIC NOT NULL CHECK (limit_price > 0),
    time_in_force        TEXT NOT NULL,
    instrument_id        TEXT NOT NULL,
    account_id           TEXT NOT NULL,
    target_session       DATE NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL,
    content              BYTEA NOT NULL,
    state                TEXT NOT NULL CHECK (state IN ('PROPOSED', 'POLICY_REJECTED', 'RISK_REJECTED', 'SUPERSEDED',
                                                        'AWAITING_APPROVAL', 'APPROVED', 'DECLINED', 'EXPIRED',
                                                        'CONVERTED')),
    policy_decision      BYTEA,
    risk_decision        BYTEA,
    approval_deadline    TIMESTAMPTZ,
    approved_by          TEXT,
    approved_at          TIMESTAMPTZ,
    approval_expires_at  TIMESTAMPTZ,
    approval_recorded_at TIMESTAMPTZ,
    lineage_id           TEXT,
    PRIMARY KEY (intent_id, version)
);

CREATE INDEX intent_versions_by_account ON intent_versions (account_id, target_session);

CREATE TABLE intent_transitions (
    intent_id   TEXT NOT NULL REFERENCES intents (intent_id),
    version     INTEGER NOT NULL,
    sequence    INTEGER NOT NULL CHECK (sequence >= 1),
    from_state  TEXT,
    to_state    TEXT NOT NULL,
    at          TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    actor_id    TEXT NOT NULL,
    reason      TEXT NOT NULL,
    PRIMARY KEY (intent_id, sequence)
);

CREATE FUNCTION intent_versions_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF (NEW.intent_id, NEW.version, NEW.side, NEW.quantity, NEW.order_type, NEW.limit_price, NEW.time_in_force,
        NEW.instrument_id, NEW.account_id, NEW.target_session, NEW.created_at, NEW.content)
       IS DISTINCT FROM
       (OLD.intent_id, OLD.version, OLD.side, OLD.quantity, OLD.order_type, OLD.limit_price, OLD.time_in_force,
        OLD.instrument_id, OLD.account_id, OLD.target_session, OLD.created_at, OLD.content) THEN
        RAISE EXCEPTION 'intent material fields are immutable (append-only history)';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION intents_counter_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF (NEW.intent_id, NEW.account_id, NEW.instrument_id) IS DISTINCT FROM
       (OLD.intent_id, OLD.account_id, OLD.instrument_id)
       OR NEW.aggregate_version <> OLD.aggregate_version + 1
       OR NEW.latest_version < OLD.latest_version THEN
        RAISE EXCEPTION 'an intent aggregate only moves forward by compare-and-set (append-only history)';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER intent_versions_immutable BEFORE UPDATE ON intent_versions
FOR EACH ROW EXECUTE FUNCTION intent_versions_immutable();
CREATE TRIGGER intent_versions_no_delete BEFORE DELETE ON intent_versions
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('intent versions');
CREATE TRIGGER intent_versions_no_truncate BEFORE TRUNCATE ON intent_versions
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('intent versions');

CREATE TRIGGER intents_counter_only BEFORE UPDATE ON intents
FOR EACH ROW EXECUTE FUNCTION intents_counter_only();
CREATE TRIGGER intents_no_delete BEFORE DELETE ON intents
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('intents');
CREATE TRIGGER intents_no_truncate BEFORE TRUNCATE ON intents
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('intents');

CREATE TRIGGER intent_transitions_no_change BEFORE UPDATE OR DELETE ON intent_transitions
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('intent transitions');
CREATE TRIGGER intent_transitions_no_truncate BEFORE TRUNCATE ON intent_transitions
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('intent transitions');
