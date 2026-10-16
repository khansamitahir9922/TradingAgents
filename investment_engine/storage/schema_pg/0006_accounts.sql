-- Accounts, autonomy settings and operators (docs/tasks/M3-05.md). PostgreSQL
-- only (M3 README; M3-01 rule 1). Every table is append-only: a change is a
-- new row (autonomy and operator history), and UPDATE, DELETE and TRUNCATE are
-- refused. Ids are never reused.

CREATE TABLE accounts (
    account_id   TEXT NOT NULL PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('RESEARCH', 'PAPER')),
    currency     TEXT NOT NULL CHECK (currency = 'USD'),
    effective_at TIMESTAMPTZ NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE autonomy_settings (
    account_id   TEXT NOT NULL REFERENCES accounts (account_id),
    sequence     INTEGER NOT NULL CHECK (sequence >= 1),
    level        INTEGER NOT NULL CHECK (level IN (0, 1, 2)),
    effective_at TIMESTAMPTZ NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL,
    set_by       TEXT NOT NULL,
    reason       TEXT NOT NULL,
    setting_id   TEXT NOT NULL UNIQUE,
    PRIMARY KEY (account_id, sequence)
);

CREATE TABLE operators (
    operator_id TEXT NOT NULL,
    sequence    INTEGER NOT NULL CHECK (sequence >= 1),
    role        TEXT NOT NULL CHECK (role IN ('ADMIN', 'TRADER', 'VIEWER')),
    active      BOOLEAN NOT NULL,
    changed_at  TIMESTAMPTZ NOT NULL,
    changed_by  TEXT NOT NULL,
    reason      TEXT NOT NULL,
    PRIMARY KEY (operator_id, sequence)
);

CREATE TRIGGER accounts_no_change BEFORE UPDATE OR DELETE ON accounts
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('accounts');
CREATE TRIGGER accounts_no_truncate BEFORE TRUNCATE ON accounts
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('accounts');
CREATE TRIGGER autonomy_settings_no_change BEFORE UPDATE OR DELETE ON autonomy_settings
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('autonomy settings');
CREATE TRIGGER autonomy_settings_no_truncate BEFORE TRUNCATE ON autonomy_settings
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('autonomy settings');
CREATE TRIGGER operators_no_change BEFORE UPDATE OR DELETE ON operators
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('operators');
CREATE TRIGGER operators_no_truncate BEFORE TRUNCATE ON operators
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('operators');
