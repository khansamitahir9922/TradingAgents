-- Intent lineage and proposal records (docs/tasks/M3-12.md). PostgreSQL only
-- (M3 README; M3-01 rule 1). Both are append-only: UPDATE, DELETE and TRUNCATE
-- are refused and a stored id can't be inserted again. One proposal record per
-- (account, view): proposing the same view again returns the stored record.

CREATE TABLE intent_lineage_records (
    lineage_id TEXT NOT NULL PRIMARY KEY,
    intent_id  TEXT NOT NULL REFERENCES intents (intent_id),
    version    INTEGER NOT NULL,
    content    BYTEA NOT NULL
);

CREATE INDEX intent_lineage_by_intent ON intent_lineage_records (intent_id, version);

CREATE TABLE proposal_records (
    record_id       TEXT NOT NULL PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts (account_id),
    view_lineage_id TEXT NOT NULL,
    at              TIMESTAMPTZ NOT NULL,
    outcome         TEXT NOT NULL CHECK (outcome IN ('PREREQUISITE_MISSING', 'NO_INTENT', 'POLICY_REJECTED',
                                                     'RISK_REJECTED', 'AWAITING_APPROVAL', 'APPROVED',
                                                     'EXPIRED_ON_ARRIVAL')),
    content         BYTEA NOT NULL,
    UNIQUE (account_id, view_lineage_id)
);

CREATE INDEX proposal_records_by_account ON proposal_records (account_id, at);

CREATE TRIGGER intent_lineage_records_no_change BEFORE UPDATE OR DELETE ON intent_lineage_records
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('intent lineage records');
CREATE TRIGGER intent_lineage_records_no_truncate BEFORE TRUNCATE ON intent_lineage_records
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('intent lineage records');
CREATE TRIGGER proposal_records_no_change BEFORE UPDATE OR DELETE ON proposal_records
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('proposal records');
CREATE TRIGGER proposal_records_no_truncate BEFORE TRUNCATE ON proposal_records
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('proposal records');
