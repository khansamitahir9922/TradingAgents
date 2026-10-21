-- Immutable comparisons, account incident episodes and CAS status history (M5-09).
CREATE TABLE reconciliation_results (
    result_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    sequence INTEGER NOT NULL CHECK(sequence>0),
    at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    book_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('MATCH','MISMATCH','INCOMPLETE')),
    content TEXT NOT NULL,
    UNIQUE(account_id,sequence), UNIQUE(result_id,account_id),
    FOREIGN KEY(book_id,account_id) REFERENCES ledger_batches(book_id,account_id),
    FOREIGN KEY(snapshot_id,account_id) REFERENCES broker_snapshots(snapshot_id,account_id)
);
CREATE TABLE reconciliation_incidents (
    incident_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    opened_result_id TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY(opened_result_id,account_id) REFERENCES reconciliation_results(result_id,account_id)
);
CREATE TABLE reconciliation_transitions (
    incident_id TEXT NOT NULL REFERENCES reconciliation_incidents(incident_id),
    sequence INTEGER NOT NULL CHECK(sequence>0),
    state TEXT NOT NULL CHECK(state IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
    result_id TEXT NOT NULL REFERENCES reconciliation_results(result_id),
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL CHECK(length(reason)>0),
    command_at TIMESTAMPTZ NOT NULL,
    business_at TIMESTAMPTZ NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY(incident_id,sequence)
);
CREATE TABLE reconciliation_evidence (
    incident_id TEXT NOT NULL REFERENCES reconciliation_incidents(incident_id),
    result_id TEXT NOT NULL REFERENCES reconciliation_results(result_id),
    recorded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(incident_id,result_id)
);
CREATE FUNCTION ie_reconciliation_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
DECLARE previous RECORD; account TEXT; opened TEXT; result_status TEXT;
BEGIN
    SELECT account_id,opened_result_id INTO STRICT account,opened FROM public.reconciliation_incidents WHERE incident_id=NEW.incident_id;
    SELECT status INTO STRICT result_status FROM public.reconciliation_results WHERE result_id=NEW.result_id AND account_id=account;
    SELECT sequence,state INTO previous FROM public.reconciliation_transitions WHERE incident_id=NEW.incident_id ORDER BY sequence DESC LIMIT 1;
    IF previous.sequence IS NULL THEN
        IF NEW.sequence<>1 OR NEW.state<>'OPEN' OR NEW.result_id<>opened OR result_status='MATCH' THEN
            RAISE EXCEPTION 'incident must open on discrepancy/incomplete evidence';
        END IF;
    ELSIF NEW.sequence<>previous.sequence+1 OR NOT ((previous.state='OPEN' AND NEW.state IN ('ACKNOWLEDGED','RESOLVED')) OR
                                                   (previous.state='ACKNOWLEDGED' AND NEW.state='RESOLVED')) THEN
        RAISE EXCEPTION 'incident CAS sequence/state edge invalid';
    END IF;
    IF NEW.state='RESOLVED' AND (result_status<>'MATCH' OR
       (SELECT sequence FROM public.reconciliation_results WHERE result_id=NEW.result_id)<=
       (SELECT sequence FROM public.reconciliation_results WHERE result_id=opened)) THEN
        RAISE EXCEPTION 'resolution requires a later MATCH in the same account';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER reconciliation_transition BEFORE INSERT ON reconciliation_transitions
FOR EACH ROW EXECUTE FUNCTION ie_reconciliation_transition();
CREATE FUNCTION ie_reconciliation_evidence() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM public.reconciliation_incidents i JOIN public.reconciliation_results r ON r.account_id=i.account_id
                  WHERE i.incident_id=NEW.incident_id AND r.result_id=NEW.result_id) THEN
        RAISE EXCEPTION 'cross-account incident evidence refused';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER reconciliation_evidence_account BEFORE INSERT ON reconciliation_evidence
FOR EACH ROW EXECUTE FUNCTION ie_reconciliation_evidence();
CREATE FUNCTION ie_incident_sealed() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM public.reconciliation_transitions WHERE incident_id=NEW.incident_id AND sequence=1 AND state='OPEN') THEN
        RAISE EXCEPTION 'incident header requires an initial OPEN transition';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER reconciliation_incident_sealed AFTER INSERT ON reconciliation_incidents
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ie_incident_sealed();
DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['reconciliation_results','reconciliation_incidents','reconciliation_transitions','reconciliation_evidence'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION ie_refuse_change(%L)',
                       tbl || '_no_change',tbl,'reconciliation append-only history');
        EXECUTE format('CREATE TRIGGER %I BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change(%L)',
                       tbl || '_no_truncate',tbl,'reconciliation append-only history');
    END LOOP;
END;
$$;
