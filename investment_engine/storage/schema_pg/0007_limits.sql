-- Versioned risk limits, policy rules and drawdown halts (docs/tasks/M3-06.md).
-- PostgreSQL only (M3 README; M3-01 rule 1). Versions and halt events are
-- append-only rows; UPDATE, DELETE and TRUNCATE are refused. Content is the
-- zlib-compressed canonical JSON of the RiskLimits or PolicyRules value.

CREATE TABLE risk_limit_versions (
    account_id   TEXT NOT NULL REFERENCES accounts (account_id),
    number       INTEGER NOT NULL CHECK (number >= 1),
    effective_at TIMESTAMPTZ NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL,
    published_by TEXT NOT NULL,
    reason       TEXT NOT NULL,
    content      BYTEA NOT NULL,
    PRIMARY KEY (account_id, number)
);

CREATE TABLE policy_rule_versions (
    account_id   TEXT NOT NULL REFERENCES accounts (account_id),
    number       INTEGER NOT NULL CHECK (number >= 1),
    effective_at TIMESTAMPTZ NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL,
    published_by TEXT NOT NULL,
    reason       TEXT NOT NULL,
    content      BYTEA NOT NULL,
    PRIMARY KEY (account_id, number)
);

CREATE TABLE halts (
    account_id      TEXT NOT NULL REFERENCES accounts (account_id),
    sequence        INTEGER NOT NULL CHECK (sequence >= 1),
    halted          BOOLEAN NOT NULL,
    at              TIMESTAMPTZ NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL,
    actor_id        TEXT NOT NULL,
    reason          TEXT NOT NULL,
    limits_version  TEXT NOT NULL,
    baseline_equity NUMERIC,
    PRIMARY KEY (account_id, sequence)
);

CREATE TRIGGER risk_limit_versions_no_change BEFORE UPDATE OR DELETE ON risk_limit_versions
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('risk limit versions');
CREATE TRIGGER risk_limit_versions_no_truncate BEFORE TRUNCATE ON risk_limit_versions
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('risk limit versions');
CREATE TRIGGER policy_rule_versions_no_change BEFORE UPDATE OR DELETE ON policy_rule_versions
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('policy rule versions');
CREATE TRIGGER policy_rule_versions_no_truncate BEFORE TRUNCATE ON policy_rule_versions
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('policy rule versions');
CREATE TRIGGER halts_no_change BEFORE UPDATE OR DELETE ON halts
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('halts');
CREATE TRIGGER halts_no_truncate BEFORE TRUNCATE ON halts
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('halts');
