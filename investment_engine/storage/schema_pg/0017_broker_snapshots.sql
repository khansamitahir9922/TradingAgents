-- Public commands/evidence and broker-private independent account facts (M5-07).
CREATE TABLE broker_setup_requests (
    setup_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL UNIQUE REFERENCES accounts(account_id),
    effective_at TIMESTAMPTZ NOT NULL,
    command_at TIMESTAMPTZ NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE broker_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    version INTEGER NOT NULL CHECK(version>0),
    effective_at TIMESTAMPTZ NOT NULL,
    taken_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    content TEXT NOT NULL,
    UNIQUE(account_id,version),
    UNIQUE(snapshot_id,account_id),
    CHECK(effective_at<=taken_at AND taken_at<=received_at AND received_at<=recorded_at)
);
-- A worker's ingestion lag is not a defect in the vendor's cash/position report.
-- Keep that separate proof immutable, including changes at one fixed replay time.
CREATE TABLE broker_ingestion_observations (
    observation_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version>0),
    complete BOOLEAN NOT NULL,
    prefix_ref TEXT NOT NULL CHECK(length(prefix_ref)>0),
    recorded_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY(snapshot_id,account_id) REFERENCES broker_snapshots(snapshot_id,account_id),
    UNIQUE(account_id,version)
);
CREATE TABLE sim_broker.account_seeds (
    account_id TEXT PRIMARY KEY,
    setup_id TEXT NOT NULL UNIQUE REFERENCES broker_setup_requests(setup_id),
    consumed_at TIMESTAMPTZ NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE sim_broker.order_links (
    client_order_id TEXT PRIMARY KEY REFERENCES sim_broker.orders(client_order_id),
    order_id TEXT NOT NULL UNIQUE
);
CREATE TABLE sim_broker.account_executions (
    broker_fill_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES sim_broker.account_seeds(account_id),
    instrument_id TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
    quantity NUMERIC NOT NULL CHECK(quantity>0 AND quantity=trunc(quantity) AND quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
    price NUMERIC NOT NULL CHECK(price>0 AND price NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
    fee NUMERIC NOT NULL CHECK(fee>=0 AND fee NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
    currency TEXT NOT NULL CHECK(currency='USD'),
    executed_at TIMESTAMPTZ NOT NULL,
    known_at TIMESTAMPTZ NOT NULL,
    content TEXT NOT NULL,
    CHECK(executed_at<=known_at)
);
CREATE TABLE sim_broker.account_actions (
    account_id TEXT NOT NULL REFERENCES sim_broker.account_seeds(account_id),
    source_identity TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision>0),
    effective_at TIMESTAMPTZ NOT NULL,
    known_at TIMESTAMPTZ NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY(account_id,source_identity,revision)
);
CREATE TABLE sim_broker.account_captures (
    account_id TEXT NOT NULL REFERENCES sim_broker.account_seeds(account_id),
    taken_at TIMESTAMPTZ NOT NULL,
    raw_hash TEXT NOT NULL,
    PRIMARY KEY(account_id,taken_at,raw_hash)
);
CREATE FUNCTION ie_broker_snapshot_writer() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
BEGIN
    IF current_setting('investment_engine.process_role',true) IS DISTINCT FROM 'execution-worker' THEN
        RAISE EXCEPTION 'only the Execution Worker writes broker snapshots';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER broker_snapshot_writer BEFORE INSERT ON broker_snapshots
FOR EACH ROW EXECUTE FUNCTION ie_broker_snapshot_writer();
CREATE TRIGGER broker_ingestion_writer BEFORE INSERT ON broker_ingestion_observations
FOR EACH ROW EXECUTE FUNCTION ie_broker_snapshot_writer();
CREATE FUNCTION ie_broker_setup_research() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM public.accounts WHERE account_id=NEW.account_id AND kind='RESEARCH') THEN
        RAISE EXCEPTION 'simulator setup requires a RESEARCH account';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER broker_setup_research BEFORE INSERT ON broker_setup_requests
FOR EACH ROW EXECUTE FUNCTION ie_broker_setup_research();
DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['broker_setup_requests','broker_snapshots','broker_ingestion_observations'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION ie_refuse_change(%L)',
                       tbl || '_no_change',tbl,'broker account append-only evidence');
        EXECUTE format('CREATE TRIGGER %I BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change(%L)',
                       tbl || '_no_truncate',tbl,'broker account append-only evidence');
    END LOOP;
    FOREACH tbl IN ARRAY ARRAY['account_seeds','order_links','account_executions','account_actions','account_captures'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON sim_broker.%I FOR EACH ROW EXECUTE FUNCTION ie_refuse_change(%L)',
                       tbl || '_no_change',tbl,'simulator account append-only evidence');
        EXECUTE format('CREATE TRIGGER %I BEFORE TRUNCATE ON sim_broker.%I FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change(%L)',
                       tbl || '_no_truncate',tbl,'simulator account append-only evidence');
    END LOOP;
END;
$$;
