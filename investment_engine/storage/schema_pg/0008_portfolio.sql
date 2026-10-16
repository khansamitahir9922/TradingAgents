-- Declared starting states and portfolio snapshots (docs/tasks/M3-07.md).
-- PostgreSQL only (M3 README; M3-01 rule 1). Append-only: UPDATE, DELETE and
-- TRUNCATE are refused, and a stored snapshot id can't be inserted again.
-- One starting state per account in M3 (the ledger replaces it in M5).

CREATE TABLE starting_states (
    account_id   TEXT NOT NULL PRIMARY KEY REFERENCES accounts (account_id),
    state_id     TEXT NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL,
    declared_by  TEXT NOT NULL,
    reason       TEXT NOT NULL,
    content      BYTEA NOT NULL
);

CREATE TABLE portfolio_snapshots (
    snapshot_id TEXT NOT NULL PRIMARY KEY,
    account_id  TEXT NOT NULL REFERENCES accounts (account_id),
    as_of       TIMESTAMPTZ NOT NULL,
    equity      NUMERIC NOT NULL,  -- for the drawdown peak query, without decoding every snapshot
    content     BYTEA NOT NULL
);

CREATE INDEX portfolio_snapshots_by_account ON portfolio_snapshots (account_id, as_of);

CREATE TRIGGER starting_states_no_change BEFORE UPDATE OR DELETE ON starting_states
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('starting states');
CREATE TRIGGER starting_states_no_truncate BEFORE TRUNCATE ON starting_states
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('starting states');
CREATE TRIGGER portfolio_snapshots_no_change BEFORE UPDATE OR DELETE ON portfolio_snapshots
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('portfolio snapshots');
CREATE TRIGGER portfolio_snapshots_no_truncate BEFORE TRUNCATE ON portfolio_snapshots
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('portfolio snapshots');
