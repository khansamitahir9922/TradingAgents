-- Codex M6 review B11: a run's record and context belong to exactly its job and its live claim.
-- Additive: 0021 is unchanged. Checked at insert, so a child added later cannot outlive the rule:
--   a record needs the job's current CLAIMED version for its run, the matching attempt and the job's settings;
--   a context needs its run's SUCCEEDED record, the still-current claim, the job's instrument and the run's
--   finish time as its generation time (a context after a terminal version is refused).

CREATE FUNCTION research_record_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE latest public.research_job_versions%ROWTYPE; job public.research_jobs%ROWTYPE; claims INTEGER;
BEGIN
    SELECT * INTO latest FROM public.research_job_versions WHERE job_id = NEW.job_id ORDER BY version DESC LIMIT 1;
    SELECT * INTO job FROM public.research_jobs WHERE job_id = NEW.job_id;
    SELECT count(*) INTO claims FROM public.research_job_versions WHERE job_id = NEW.job_id AND state = 'CLAIMED';
    IF latest.state IS DISTINCT FROM 'CLAIMED' OR latest.run_id IS DISTINCT FROM NEW.run_id
       OR claims IS DISTINCT FROM NEW.attempt
       OR (NEW.content::jsonb #> '{fields,settings}') IS DISTINCT FROM (job.content::jsonb #> '{fields,settings}')
       OR (NEW.content::jsonb #>> '{fields,job_id}') IS DISTINCT FROM NEW.job_id THEN
        RAISE EXCEPTION 'research record must be its job''s current claimed run, with the job''s settings';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER research_record_guard BEFORE INSERT ON research_records
FOR EACH ROW EXECUTE FUNCTION research_record_guard();

CREATE FUNCTION research_context_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE rec public.research_records%ROWTYPE; latest public.research_job_versions%ROWTYPE;
        job public.research_jobs%ROWTYPE;
BEGIN
    SELECT * INTO rec FROM public.research_records WHERE run_id = NEW.run_id;
    SELECT * INTO latest FROM public.research_job_versions WHERE job_id = rec.job_id ORDER BY version DESC LIMIT 1;
    SELECT * INTO job FROM public.research_jobs WHERE job_id = rec.job_id;
    IF rec.run_id IS NULL OR rec.outcome <> 'SUCCEEDED' OR latest.state IS DISTINCT FROM 'CLAIMED'
       OR latest.run_id IS DISTINCT FROM NEW.run_id OR NEW.instrument_id IS DISTINCT FROM job.instrument_id
       OR (NEW.content::jsonb #>> '{fields,instrument_id}') IS DISTINCT FROM NEW.instrument_id
       OR (NEW.content::jsonb #>> '{fields,run_id}') IS DISTINCT FROM NEW.run_id
       OR NEW.generated_at IS DISTINCT FROM rec.finished_at THEN
        RAISE EXCEPTION 'research context must belong to its job''s succeeded, still-claimed run and instrument';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER research_context_guard BEFORE INSERT ON research_contexts
FOR EACH ROW EXECUTE FUNCTION research_context_guard();
