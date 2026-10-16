-- Reference data on PostgreSQL: the instrument master and provider symbol
-- mappings (ADR-003; docs/tasks/M1-05.md, M3-01.md). Same tables, columns,
-- keys and checks as SQLite version 1, with native DATE columns.

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
    active_from   DATE NOT NULL,
    active_to     DATE,
    CHECK (active_to IS NULL OR active_to > active_from),
    CHECK (status <> 'ACTIVE' OR active_to IS NULL),
    CHECK (status <> 'DELISTED' OR active_to IS NOT NULL)
);

-- Half-open validity [valid_from, valid_to); NULL valid_to is open-ended.
-- Overlap rules stay in application code, inside the inserting transaction,
-- serialized by advisory locks on both conflict dimensions (M3-01 rule 4).
CREATE TABLE symbol_mappings (
    instrument_id TEXT NOT NULL REFERENCES instruments (instrument_id),
    provider      TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    valid_from    DATE NOT NULL,
    valid_to      DATE,
    PRIMARY KEY (provider, symbol, valid_from),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX symbol_mappings_by_instrument ON symbol_mappings (instrument_id, provider);
