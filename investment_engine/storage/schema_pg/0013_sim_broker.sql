-- The simulated broker's own state (architecture Part K M4; Law 20; docs/tasks/M4-06.md). Written only by
-- investment_engine/execution/simulated_broker.py; the Core Engine and the reporter never read it, exactly as with a
-- real broker. Messages are append-only.

CREATE SCHEMA sim_broker;

CREATE TABLE sim_broker.orders (
    client_order_id    TEXT NOT NULL PRIMARY KEY,
    broker_order_id    TEXT NOT NULL UNIQUE,
    instrument_id      TEXT NOT NULL,
    side               TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity           NUMERIC NOT NULL,
    limit_price        NUMERIC NOT NULL,
    time_in_force      TEXT NOT NULL,
    order_type         TEXT NOT NULL,
    target_session     DATE NOT NULL,
    submitted_at       TIMESTAMPTZ NOT NULL,
    status             TEXT NOT NULL CHECK (status IN ('OPEN', 'FILLED', 'CANCELLED', 'EXPIRED', 'REJECTED')),
    filled_qty         NUMERIC NOT NULL,
    cancel_received_at TIMESTAMPTZ,
    decided_at         TIMESTAMPTZ
);

CREATE TABLE sim_broker.messages (
    message_id      TEXT NOT NULL PRIMARY KEY,
    client_order_id TEXT NOT NULL REFERENCES sim_broker.orders (client_order_id),
    kind            TEXT NOT NULL CHECK (kind IN ('ACK', 'FILL', 'EXPIRED', 'CANCELLED', 'REJECTED')),
    delivered_at    TIMESTAMPTZ NOT NULL,
    fill            TEXT,
    reason          TEXT NOT NULL
);

CREATE INDEX sim_broker_messages_delivery ON sim_broker.messages (delivered_at, message_id);

CREATE TRIGGER sim_broker_messages_no_change BEFORE UPDATE OR DELETE ON sim_broker.messages
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('simulated broker messages');
CREATE TRIGGER sim_broker_messages_no_truncate BEFORE TRUNCATE ON sim_broker.messages
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('simulated broker messages');
CREATE TRIGGER sim_broker_orders_no_delete BEFORE DELETE ON sim_broker.orders
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('simulated broker orders');
