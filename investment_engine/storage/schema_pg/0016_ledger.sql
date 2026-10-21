-- Accepted ADR-010. Additive, sealed and append-only, including SQL bypass guards.
CREATE TABLE ledger_batches (
    book_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    parent_id TEXT,
    version INTEGER NOT NULL CHECK(version > 0),
    posted_at TIMESTAMPTZ NOT NULL,
    source_set_hash TEXT NOT NULL CHECK(length(source_set_hash)=64),
    source_count INTEGER NOT NULL CHECK(source_count >= 0),
    transaction_count INTEGER NOT NULL CHECK(transaction_count >= 0),
    lot_count INTEGER NOT NULL CHECK(lot_count >= 0),
    content TEXT NOT NULL,
    UNIQUE(account_id, version), UNIQUE(book_id, account_id),
    FOREIGN KEY(parent_id,account_id) REFERENCES ledger_batches(book_id,account_id),
    CHECK((version=1) = (parent_id IS NULL))
);
CREATE TABLE ledger_transactions (
    transaction_id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    posted_at TIMESTAMPTZ NOT NULL,
    entry_count INTEGER NOT NULL CHECK(entry_count >= 2),
    manifest_hash TEXT NOT NULL CHECK(length(manifest_hash)=64),
    reverses TEXT UNIQUE REFERENCES ledger_transactions(transaction_id),
    FOREIGN KEY(book_id,account_id) REFERENCES ledger_batches(book_id,account_id),
    UNIQUE(transaction_id, book_id, account_id)
);
CREATE TABLE ledger_entries (
    entry_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    book_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    chart_account TEXT NOT NULL CHECK(length(chart_account)>0),
    unit TEXT NOT NULL CHECK(unit='CURRENCY:USD' OR unit ~ '^SECURITY:(EQ|ETF)_[A-Z]{2}_[A-Z0-9]+(_[0-9]+)?$'),
    debit NUMERIC NOT NULL CHECK(debit>=0 AND debit NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
    credit NUMERIC NOT NULL CHECK(credit>=0 AND credit NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
    effective_at TIMESTAMPTZ NOT NULL,
    posted_at TIMESTAMPTZ NOT NULL,
    reverses TEXT UNIQUE REFERENCES ledger_entries(entry_id),
    content TEXT NOT NULL,
    CHECK((debit>0 AND credit=0) OR (credit>0 AND debit=0)),
    CHECK(unit='CURRENCY:USD' OR (debit=trunc(debit) AND credit=trunc(credit))),
    FOREIGN KEY(transaction_id,book_id,account_id) REFERENCES ledger_transactions(transaction_id,book_id,account_id),
    UNIQUE(transaction_id,ordinal)
);
CREATE TABLE ledger_source_receipts (
    book_id TEXT NOT NULL REFERENCES ledger_batches(book_id),
    source_id TEXT NOT NULL,
    source_key TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY(book_id,source_id)
);
CREATE TABLE ledger_lot_matches (
    book_id TEXT NOT NULL REFERENCES ledger_batches(book_id),
    match_id TEXT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY(book_id,match_id)
);
CREATE TABLE ledger_activations (
    account_id TEXT PRIMARY KEY REFERENCES accounts(account_id),
    book_id TEXT NOT NULL,
    command_at TIMESTAMPTZ NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY(book_id,account_id) REFERENCES ledger_batches(book_id,account_id)
);

CREATE FUNCTION ledger_check_transaction() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
DECLARE t public.ledger_transactions%ROWTYPE; n BIGINT; actual_hash TEXT;
BEGIN
    SELECT * INTO STRICT t FROM public.ledger_transactions WHERE transaction_id=NEW.transaction_id;
    SELECT count(*), encode(sha256(convert_to('[' || string_agg(content,',' ORDER BY ordinal) || ']','UTF8')),'hex')
      INTO n,actual_hash FROM public.ledger_entries WHERE transaction_id=t.transaction_id;
    IF n <> t.entry_count OR actual_hash IS DISTINCT FROM t.manifest_hash THEN
        RAISE EXCEPTION 'sealed ledger entry manifest/count mismatch';
    END IF;
    IF EXISTS(SELECT 1 FROM public.ledger_entries WHERE transaction_id=t.transaction_id
              GROUP BY unit HAVING sum(debit)<>sum(credit) OR count(*)<2) THEN
        RAISE EXCEPTION 'ledger transaction must balance independently in every unit';
    END IF;
    IF EXISTS(SELECT 1 FROM public.ledger_entries e WHERE e.transaction_id=t.transaction_id AND
              (e.effective_at<>t.effective_at OR e.posted_at<>t.posted_at OR
               (e.content::jsonb #>> '{fields,entry_id}') IS DISTINCT FROM e.entry_id OR
               (e.content::jsonb #>> '{fields,transaction_id}') IS DISTINCT FROM e.transaction_id OR
               (e.content::jsonb #>> '{fields,investment_account_id}') IS DISTINCT FROM e.account_id OR
               (e.content::jsonb #>> '{fields,account}') IS DISTINCT FROM e.chart_account OR
               (e.content::jsonb #>> '{fields,debit,$decimal}')::numeric IS DISTINCT FROM e.debit OR
               (e.content::jsonb #>> '{fields,credit,$decimal}')::numeric IS DISTINCT FROM e.credit OR
               (e.content::jsonb #>> '{fields,unit,fields,kind}') || ':' ||
               (e.content::jsonb #>> '{fields,unit,fields,code}') IS DISTINCT FROM e.unit OR
               (e.content::jsonb #>> '{fields,effective_at,$datetime}')::timestamptz IS DISTINCT FROM e.effective_at OR
               (e.content::jsonb #>> '{fields,posted_at,$datetime}')::timestamptz IS DISTINCT FROM e.posted_at OR
               (e.content::jsonb #>> '{fields,reverses}') IS DISTINCT FROM e.reverses)) THEN
        RAISE EXCEPTION 'ledger entry payload/column mismatch';
    END IF;
    IF t.reverses IS NOT NULL THEN
        IF NOT EXISTS(SELECT 1 FROM public.ledger_transactions original WHERE original.transaction_id=t.reverses
                      AND original.account_id=t.account_id AND original.effective_at=t.effective_at
                      AND original.entry_count=t.entry_count AND original.posted_at<=t.posted_at) OR
           EXISTS(SELECT 1 FROM public.ledger_entries e LEFT JOIN public.ledger_entries prior ON prior.entry_id=e.reverses
                  WHERE e.transaction_id=t.transaction_id AND (prior.transaction_id IS DISTINCT FROM t.reverses OR
                        prior.unit IS DISTINCT FROM e.unit OR prior.chart_account IS DISTINCT FROM e.chart_account OR
                        prior.debit IS DISTINCT FROM e.credit OR prior.credit IS DISTINCT FROM e.debit)) THEN
            RAISE EXCEPTION 'ledger reversal must fully negate the same account and units';
        END IF;
    ELSIF EXISTS(SELECT 1 FROM public.ledger_entries WHERE transaction_id=t.transaction_id AND reverses IS NOT NULL) THEN
        RAISE EXCEPTION 'entry reversal requires transaction reversal';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER ledger_transaction_sealed AFTER INSERT ON ledger_transactions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ledger_check_transaction();
CREATE CONSTRAINT TRIGGER ledger_entry_sealed AFTER INSERT ON ledger_entries
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ledger_check_transaction();

CREATE FUNCTION ledger_check_batch() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
DECLARE b public.ledger_batches%ROWTYPE; id TEXT;
BEGIN
    id := NEW.book_id;
    SELECT * INTO STRICT b FROM public.ledger_batches WHERE book_id=id;
    IF b.parent_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.ledger_batches p WHERE
       p.book_id=b.parent_id AND p.account_id=b.account_id AND p.version=b.version-1 AND p.posted_at<=b.posted_at) THEN
        RAISE EXCEPTION 'ledger parent/version/time mismatch';
    END IF;
    IF (SELECT count(*) FROM public.ledger_transactions WHERE book_id=id)<>b.transaction_count OR
       (SELECT count(*) FROM public.ledger_source_receipts WHERE book_id=id)<>b.source_count OR
       (SELECT count(*) FROM public.ledger_lot_matches WHERE book_id=id)<>b.lot_count OR
       EXISTS(SELECT 1 FROM public.ledger_transactions WHERE book_id=id AND posted_at<>b.posted_at) THEN
        RAISE EXCEPTION 'sealed ledger batch manifest/count mismatch';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER ledger_batch_sealed AFTER INSERT ON ledger_batches
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ledger_check_batch();
CREATE CONSTRAINT TRIGGER ledger_batch_tx_sealed AFTER INSERT ON ledger_transactions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ledger_check_batch();
CREATE CONSTRAINT TRIGGER ledger_batch_source_sealed AFTER INSERT ON ledger_source_receipts
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ledger_check_batch();
CREATE CONSTRAINT TRIGGER ledger_batch_lot_sealed AFTER INSERT ON ledger_lot_matches
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ledger_check_batch();

DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['ledger_batches','ledger_transactions','ledger_entries','ledger_source_receipts',
                              'ledger_lot_matches','ledger_activations'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION ie_refuse_change(%L)',
                       tbl || '_no_change',tbl,'ledger append-only history');
        EXECUTE format('CREATE TRIGGER %I BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION ie_refuse_change(%L)',
                       tbl || '_no_truncate',tbl,'ledger append-only history');
    END LOOP;
END;
$$;
