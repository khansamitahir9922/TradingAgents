-- Promotion thresholds and assessments (Law 19; D21, D22; docs/tasks/M4-10.md). Append-only: a new threshold
-- version or a new assessment is a new row; nothing is updated or deleted.

CREATE TABLE promotion_thresholds (
    version      TEXT NOT NULL PRIMARY KEY,
    sequence     INTEGER NOT NULL UNIQUE CHECK (sequence >= 1),
    content      TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    published_by TEXT NOT NULL,
    reason       TEXT NOT NULL
);

CREATE TABLE promotion_assessments (
    assessment_id      TEXT NOT NULL PRIMARY KEY,
    record_id          TEXT NOT NULL,
    recipe_id          TEXT,
    source             TEXT NOT NULL,
    instrument_id      TEXT NOT NULL,
    thresholds_version TEXT NOT NULL REFERENCES promotion_thresholds (version),
    status             TEXT NOT NULL CHECK (status IN ('PASSED', 'FAILED', 'REFUSED')),
    content            TEXT NOT NULL,
    assessed_at        TIMESTAMPTZ NOT NULL
);

CREATE INDEX promotion_assessments_by_recipe ON promotion_assessments (recipe_id, source, instrument_id, assessed_at);

CREATE TRIGGER promotion_thresholds_no_change BEFORE UPDATE OR DELETE ON promotion_thresholds
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('promotion thresholds');
CREATE TRIGGER promotion_thresholds_no_truncate BEFORE TRUNCATE ON promotion_thresholds
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('promotion thresholds');
CREATE TRIGGER promotion_assessments_no_change BEFORE UPDATE OR DELETE ON promotion_assessments
FOR EACH ROW EXECUTE FUNCTION ie_refuse_change('promotion assessments');
CREATE TRIGGER promotion_assessments_no_truncate BEFORE TRUNCATE ON promotion_assessments
FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change('promotion assessments');
