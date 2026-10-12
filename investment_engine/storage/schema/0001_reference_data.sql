-- Reference data: the instrument master and provider symbol mappings
-- (ADR-003; docs/tasks/M1-05.md). Portable SQL only, so the M3 move to
-- PostgreSQL is mechanical (ADR-008). Dates are ISO-8601 text (YYYY-MM-DD),
-- which compares correctly as text.

CREATE TABLE schema_version (
    version INTEGER NOT NULL PRIMARY KEY
);

-- No row is ever deleted: an instrument ID is never reused (ADR-003).
CREATE TABLE instruments (
    instrument_id TEXT NOT NULL PRIMARY KEY,
    asset_class   TEXT NOT NULL CHECK (asset_class IN ('EQUITY', 'ETF')),
    currency      TEXT NOT NULL CHECK (length(currency) = 3),
    exchange      TEXT NOT NULL CHECK (length(exchange) = 4),
    timezone      TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('ACTIVE', 'DELISTED', 'SUSPENDED')),
    active_from   TEXT NOT NULL,
    active_to     TEXT,
    CHECK (active_to IS NULL OR active_to > active_from),
    CHECK (status <> 'ACTIVE' OR active_to IS NULL),
    CHECK (status <> 'DELISTED' OR active_to IS NOT NULL)
);

-- Half-open validity [valid_from, valid_to); NULL valid_to is open-ended.
-- Overlap rules can't be expressed as portable constraints; the application
-- checks them in the same transaction as the insert (M1-04's rules).
CREATE TABLE symbol_mappings (
    instrument_id TEXT NOT NULL REFERENCES instruments (instrument_id),
    provider      TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    valid_from    TEXT NOT NULL,
    valid_to      TEXT,
    PRIMARY KEY (provider, symbol, valid_from),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX symbol_mappings_by_instrument ON symbol_mappings (instrument_id, provider);
