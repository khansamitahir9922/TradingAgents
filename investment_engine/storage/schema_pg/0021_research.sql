-- M6-02: research jobs, run records, contexts and budget evidence (ADR-001; docs/tasks/M6-README.md C2).
-- Append-only. Writers are fixed by process role:
--   core-engine (Core/CLI/Admin): job requests, unclaimed expiry, budget policies;
--   research-worker: claims, finishes, run records, contexts and budget usage.
-- Additive: migrations 0001-0020 are unchanged; the outbox gains the research writer.

ALTER TABLE outbox DROP CONSTRAINT outbox_writer_check;
ALTER TABLE outbox ADD CONSTRAINT outbox_writer_check
    CHECK (writer IN ('core-engine', 'execution-worker', 'research-worker'));

CREATE TABLE research_jobs (
    job_id        TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    research_date DATE NOT NULL,
    requested_by  TEXT NOT NULL,
    requested_at  TIMESTAMPTZ NOT NULL,
    content       TEXT NOT NULL
);
CREATE TABLE research_records (
    run_id      TEXT PRIMARY KEY,
    job_id      TEXT NOT NULL REFERENCES research_jobs(job_id),
    attempt     INTEGER NOT NULL CHECK (attempt BETWEEN 1 AND 2),
    outcome     TEXT NOT NULL CHECK (outcome IN ('SUCCEEDED', 'FAILED')),
    started_at  TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL CHECK (finished_at >= started_at),
    content     TEXT NOT NULL,
    UNIQUE (job_id, attempt)
);
CREATE TABLE research_contexts (
    run_id        TEXT PRIMARY KEY REFERENCES research_records(run_id),
    instrument_id TEXT NOT NULL,
    generated_at  TIMESTAMPTZ NOT NULL,
    valid_until   TIMESTAMPTZ NOT NULL CHECK (valid_until > generated_at),
    content       TEXT NOT NULL
);
CREATE INDEX research_contexts_latest ON research_contexts (instrument_id, generated_at);
CREATE TABLE research_job_versions (
    job_id      TEXT NOT NULL REFERENCES research_jobs(job_id),
    version     INTEGER NOT NULL CHECK (version >= 1),
    state       TEXT NOT NULL CHECK (state IN ('REQUESTED', 'CLAIMED', 'SUCCEEDED', 'FAILED', 'BUDGET_REFUSED',
                                               'EXPIRED_UNCLAIMED')),
    at          TIMESTAMPTZ NOT NULL,
    actor       TEXT NOT NULL,
    lease_until TIMESTAMPTZ,
    run_id      TEXT,
    content     TEXT NOT NULL,
    PRIMARY KEY (job_id, version),  -- compare-and-set: one successor per version
    CHECK ((state = 'CLAIMED') = (lease_until IS NOT NULL)),
    CHECK (lease_until IS NULL OR lease_until > at)
);
CREATE TABLE research_budget_policies (
    version INTEGER PRIMARY KEY CHECK (version >= 1),
    set_by  TEXT NOT NULL,
    set_at  TIMESTAMPTZ NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE research_budget_usage (
    day      DATE NOT NULL,
    run_id   TEXT NOT NULL,
    kind     TEXT NOT NULL CHECK (kind IN ('RESERVED', 'ACTUAL')),
    requests INTEGER NOT NULL CHECK (requests >= 0),
    tokens   BIGINT NOT NULL CHECK (tokens >= 0),
    at       TIMESTAMPTZ NOT NULL,
    content  TEXT NOT NULL,
    PRIMARY KEY (run_id, kind)
);
CREATE INDEX research_budget_usage_day ON research_budget_usage (day);

CREATE FUNCTION research_require_role(expected TEXT) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF current_setting('investment_engine.process_role', true) IS DISTINCT FROM expected THEN
        RAISE EXCEPTION 'research evidence: only the % writes this', expected;
    END IF;
END;
$$;

CREATE FUNCTION research_core_writer() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    PERFORM public.research_require_role('core-engine');
    RETURN NEW;
END;
$$;
CREATE FUNCTION research_worker_writer() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    PERFORM public.research_require_role('research-worker');
    RETURN NEW;
END;
$$;
CREATE TRIGGER research_jobs_writer BEFORE INSERT ON research_jobs
FOR EACH ROW EXECUTE FUNCTION research_core_writer();
CREATE TRIGGER research_budget_policies_writer BEFORE INSERT ON research_budget_policies
FOR EACH ROW EXECUTE FUNCTION research_core_writer();
CREATE TRIGGER research_records_writer BEFORE INSERT ON research_records
FOR EACH ROW EXECUTE FUNCTION research_worker_writer();
CREATE TRIGGER research_contexts_writer BEFORE INSERT ON research_contexts
FOR EACH ROW EXECUTE FUNCTION research_worker_writer();
CREATE TRIGGER research_budget_usage_writer BEFORE INSERT ON research_budget_usage
FOR EACH ROW EXECUTE FUNCTION research_worker_writer();

-- Job state edges and lease rules (mirrors investment_engine.research.contracts.JOB_EDGES).
CREATE FUNCTION research_job_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE prev public.research_job_versions%ROWTYPE; claims INTEGER; rec public.research_records%ROWTYPE;
BEGIN
    IF NEW.state IN ('REQUESTED', 'EXPIRED_UNCLAIMED') THEN
        PERFORM public.research_require_role('core-engine');
    ELSE
        PERFORM public.research_require_role('research-worker');
    END IF;
    SELECT * INTO prev FROM public.research_job_versions WHERE job_id = NEW.job_id AND version = NEW.version - 1;
    IF NEW.version = 1 THEN
        IF NEW.state <> 'REQUESTED' THEN
            RAISE EXCEPTION 'research job must start REQUESTED';
        END IF;
        RETURN NEW;
    END IF;
    IF prev.job_id IS NULL OR NEW.at < prev.at OR NOT (
        (prev.state = 'REQUESTED' AND NEW.state IN ('CLAIMED', 'EXPIRED_UNCLAIMED')) OR
        (prev.state = 'CLAIMED' AND NEW.state IN ('CLAIMED', 'SUCCEEDED', 'FAILED', 'BUDGET_REFUSED'))) THEN
        RAISE EXCEPTION 'research job edge/sequence invalid';
    END IF;
    IF NEW.state = 'CLAIMED' THEN
        SELECT count(*) INTO claims FROM public.research_job_versions WHERE job_id = NEW.job_id AND state = 'CLAIMED';
        IF NEW.run_id IS NULL OR claims >= 2 OR (prev.state = 'CLAIMED' AND (NEW.at < prev.lease_until
                                                   OR NEW.run_id = prev.run_id)) THEN
            RAISE EXCEPTION 'research claim needs a new run, an expired previous lease and at most one re-claim';
        END IF;
    ELSIF prev.state = 'CLAIMED' THEN
        IF NEW.actor IS DISTINCT FROM prev.actor OR NEW.run_id IS DISTINCT FROM prev.run_id THEN
            RAISE EXCEPTION 'only the current claim holder finishes its own run';
        END IF;
        IF NEW.state IN ('SUCCEEDED', 'FAILED') THEN
            SELECT * INTO rec FROM public.research_records WHERE run_id = NEW.run_id AND job_id = NEW.job_id;
            IF rec.run_id IS NULL OR rec.outcome <> NEW.state OR
               (NEW.state = 'SUCCEEDED') <> EXISTS(SELECT 1 FROM public.research_contexts WHERE run_id = NEW.run_id) THEN
                RAISE EXCEPTION 'a finished run needs its record (and, when it succeeded, exactly its context)';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER research_job_transition BEFORE INSERT ON research_job_versions
FOR EACH ROW EXECUTE FUNCTION research_job_transition();

DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['research_jobs', 'research_records', 'research_contexts', 'research_job_versions',
                              'research_budget_policies', 'research_budget_usage'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION ie_refuse_change(%L)',
                       tbl || '_no_change', tbl, 'research append-only history');
        EXECUTE format('CREATE TRIGGER %I BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change(%L)',
                       tbl || '_no_truncate', tbl, 'research append-only history');
    END LOOP;
END;
$$;
