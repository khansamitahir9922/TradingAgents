-- R1: preserve payload seals without rechecking the entire book for every child.
-- Additive upgrade; migrations 0016-0019 and stored evidence remain unchanged.
CREATE OR REPLACE FUNCTION ledger_canonical_json(value jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT SET search_path=pg_catalog,public AS $$
DECLARE result text; ch text; code integer; i integer;
BEGIN
    CASE jsonb_typeof(value)
    WHEN 'object' THEN
        SELECT '{' || coalesce(string_agg(public.ledger_canonical_json(to_jsonb(key)) || ':' ||
               public.ledger_canonical_json(val), ',' ORDER BY key COLLATE "C"), '') || '}' INTO result
          FROM jsonb_each(value) AS pairs(key,val);
    WHEN 'array' THEN
        SELECT '[' || coalesce(string_agg(public.ledger_canonical_json(val), ',' ORDER BY n), '') || ']'
          INTO result FROM jsonb_array_elements(value) WITH ORDINALITY AS items(val,n);
    WHEN 'string' THEN
        -- JSONB already escapes ASCII controls, quotes and backslashes exactly as the codec.
        -- DEL/non-ASCII still take the original ensure_ascii-compatible path below.
        IF (value::text COLLATE "C") ~ '^[ -~]*$' THEN
            RETURN value::text;
        END IF;
        result := '';
        -- PostgreSQL already escapes JSON controls/quotes/backslashes; add Python's ASCII escapes.
        FOR ch IN SELECT regexp_split_to_table(value::text, '') LOOP
            code := ascii(ch);
            IF code > 65535 THEN
                i := code - 65536;
                result := result || E'\\u' || lpad(to_hex(55296 + (i / 1024)),4,'0') ||
                                    E'\\u' || lpad(to_hex(56320 + (i % 1024)),4,'0');
            ELSIF code >= 127 THEN
                result := result || E'\\u' || lpad(to_hex(code),4,'0');
            ELSE
                result := result || ch;
            END IF;
        END LOOP;
    ELSE result := value::text;
    END CASE;
    RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION ledger_check_batch() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
DECLARE b public.ledger_batches%ROWTYPE; payload jsonb; fields jsonb; tx jsonb; ref jsonb; lot jsonb;
        t public.ledger_transactions%ROWTYPE; receipt public.ledger_source_receipts%ROWTYPE;
        match_row public.ledger_lot_matches%ROWTYPE; entries jsonb; seen text[]; rid text;
BEGIN
    SELECT * INTO STRICT b FROM public.ledger_batches WHERE book_id=NEW.book_id;
    IF b.parent_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.ledger_batches p WHERE
       p.book_id=b.parent_id AND p.account_id=b.account_id AND p.version=b.version-1 AND p.posted_at<=b.posted_at) THEN
        RAISE EXCEPTION 'ledger parent/version/time mismatch';
    END IF;
    IF (SELECT count(*) FROM public.ledger_transactions WHERE book_id=b.book_id)<>b.transaction_count OR
       (SELECT count(*) FROM public.ledger_source_receipts WHERE book_id=b.book_id)<>b.source_count OR
       (SELECT count(*) FROM public.ledger_lot_matches WHERE book_id=b.book_id)<>b.lot_count OR
       EXISTS(SELECT 1 FROM public.ledger_transactions WHERE book_id=b.book_id AND posted_at<>b.posted_at) THEN
        RAISE EXCEPTION 'sealed ledger batch manifest/count mismatch';
    END IF;
    -- Every child insertion must retain the immutable manifest counts, including
    -- later transactions and SET CONSTRAINTS IMMEDIATE. Only the batch-row firing
    -- needs the full payload comparison: saved rows cannot be updated or replaced.
    IF TG_TABLE_NAME <> 'ledger_batches' THEN
        RETURN NULL;
    END IF;
    payload := b.content::jsonb;
    fields := payload->'fields';
    IF payload->>'$type' IS DISTINCT FROM 'BookBatch' OR
       fields->>'account_id' IS DISTINCT FROM b.account_id OR
       fields->>'parent_id' IS DISTINCT FROM b.parent_id OR
       (fields->>'version')::integer IS DISTINCT FROM b.version OR
       (fields#>>'{posted_at,$datetime}')::timestamptz IS DISTINCT FROM b.posted_at OR
       jsonb_typeof(fields->'transactions') IS DISTINCT FROM 'array' OR
       jsonb_typeof(fields->'sources') IS DISTINCT FROM 'array' OR
       jsonb_typeof(fields->'lot_matches') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'ledger batch payload/header mismatch';
    END IF;
    IF jsonb_array_length(fields->'transactions')<>b.transaction_count OR
       jsonb_array_length(fields->'sources')<>b.source_count OR
       jsonb_array_length(fields->'lot_matches')<>b.lot_count OR
       public.ledger_payload_hash(fields->'sources') IS DISTINCT FROM b.source_set_hash THEN
        RAISE EXCEPTION 'ledger batch source/manifest mismatch';
    END IF;
    seen := ARRAY[]::text[];
    FOR tx IN SELECT value FROM jsonb_array_elements(fields->'transactions') LOOP
        rid := tx#>>'{fields,transaction_id}';
        SELECT * INTO t FROM public.ledger_transactions WHERE transaction_id=rid AND book_id=b.book_id;
        SELECT coalesce(jsonb_agg(e.content::jsonb ORDER BY e.ordinal),'[]'::jsonb) INTO entries
          FROM public.ledger_entries e WHERE e.transaction_id=rid AND e.book_id=b.book_id;
        IF t.transaction_id IS NULL OR rid=ANY(seen) OR tx->>'$type' IS DISTINCT FROM 'JournalTransaction' OR
           tx#>>'{fields,investment_account_id}' IS DISTINCT FROM t.account_id OR
           (tx#>>'{fields,effective_at,$datetime}')::timestamptz IS DISTINCT FROM t.effective_at OR
           (tx#>>'{fields,posted_at,$datetime}')::timestamptz IS DISTINCT FROM t.posted_at OR
           tx#>>'{fields,reverses}' IS DISTINCT FROM t.reverses OR
           tx#>'{fields,entries}' IS DISTINCT FROM entries OR
           jsonb_array_length(entries) IS DISTINCT FROM t.entry_count OR
           public.ledger_payload_hash(entries) IS DISTINCT FROM t.manifest_hash THEN
            RAISE EXCEPTION 'ledger transaction payload/manifest mismatch';
        END IF;
        IF jsonb_typeof(tx#>'{fields,sources}') IS DISTINCT FROM 'array' OR
           EXISTS(SELECT 1 FROM jsonb_array_elements(tx#>'{fields,sources}') s
                  WHERE NOT EXISTS(SELECT 1 FROM jsonb_array_elements(fields->'sources') bsrc WHERE bsrc.value = s.value)) OR
           EXISTS(SELECT 1 FROM jsonb_array_elements(entries) e
                  WHERE e#>'{fields,sources}' IS DISTINCT FROM tx#>'{fields,sources}') THEN
            RAISE EXCEPTION 'ledger transaction source payload mismatch';
        END IF;
        seen := array_append(seen,rid);
    END LOOP;
    seen := ARRAY[]::text[];
    FOR ref IN SELECT value FROM jsonb_array_elements(fields->'sources') LOOP
        rid := public.ledger_payload_hash(public.ledger_content_map(ref->'fields'));
        SELECT * INTO receipt FROM public.ledger_source_receipts WHERE book_id=b.book_id AND source_id=rid;
        IF receipt.source_id IS NULL OR rid=ANY(seen) OR ref->>'$type' IS DISTINCT FROM 'SourceRef' OR
           receipt.content::jsonb IS DISTINCT FROM ref OR
           receipt.content_hash IS DISTINCT FROM ref#>>'{fields,content_hash}' OR
           receipt.source_key IS DISTINCT FROM public.ledger_payload_hash(jsonb_build_array(b.account_id,
              ref#>'{fields,kind}',ref#>'{fields,identity}',ref#>'{fields,revision}',ref#>'{fields,provider}')) THEN
            RAISE EXCEPTION 'ledger source receipt payload/hash mismatch';
        END IF;
        seen := array_append(seen,rid);
    END LOOP;
    seen := ARRAY[]::text[];
    FOR lot IN SELECT value FROM jsonb_array_elements(fields->'lot_matches') LOOP
        rid := lot#>>'{fields,match_id}';
        SELECT * INTO match_row FROM public.ledger_lot_matches WHERE book_id=b.book_id AND match_id=rid;
        IF match_row.match_id IS NULL OR rid=ANY(seen) OR lot->>'$type' IS DISTINCT FROM 'LotMatch' OR
           lot#>>'{fields,book_id}' IS DISTINCT FROM b.book_id OR match_row.content::jsonb IS DISTINCT FROM lot THEN
            RAISE EXCEPTION 'ledger lot match payload mismatch';
        END IF;
        seen := array_append(seen,rid);
    END LOOP;
    RETURN NULL;
END;
$$;
