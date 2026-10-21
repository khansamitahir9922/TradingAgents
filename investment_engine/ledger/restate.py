"""Source-proven complete economic replay; append only the affected dependency closure.

The planning replay never deletes/rebuilds database history. It compares the full
validated prefix with current active transactions, then appends complete reversals
and replacements in one transaction. A discrepancy from a broker is not an input.
"""
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

from investment_engine.config import market_store_dir
from investment_engine.ledger.actions import plan_action
from investment_engine.ledger.contracts import (
    AccountingUnavailable,
    BookBatch,
    SourceBundle,
    SourceConflict,
    SourceRef,
    identity,
    reverse_transaction,
)
from investment_engine.ledger.lots import FifoBook, exact_decimal
from investment_engine.ledger.postings import plan_fifo_fill
from investment_engine.ledger.sources import (
    opening_bundle,
    validate_action,
    validate_fill,
)
from investment_engine.lineage.records import decode
from investment_engine.market.availability import check_utc
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.corporate_actions import ActionType, CorporateAction
from investment_engine.oms.order_states import ProcessRole
from investment_engine.oms.order_store import OrderStore
from investment_engine.oms.orders import Fill, Order
from investment_engine.policy.accounts import AccountRegistry
from investment_engine.portfolio.snapshot import PortfolioSnapshotStore, StartingState
from investment_engine.quant.adjusted import ActionCoverage, AdjustmentUnavailable, require_coverage


@dataclass(frozen=True)
class SyncReport:
    book_id: str
    changed: bool
    reversed_transactions: tuple[str, ...]
    replacement_transactions: tuple[str, ...]


def _key(ref):
    return ref.kind, ref.identity, ref.provider


def _economic(tx):
    return identity((tx.investment_account_id, tx.effective_at, tx.sources,
                     tuple((e.account, e.unit, e.debit, e.credit) for e in tx.entries)))


def _active(ledger, head):
    txs = tuple(t for b in ledger.ancestry(head.book_id) for t in b.transactions)
    reversed_ids = {t.reverses for t in txs if t.reverses}
    result = {}
    for tx in txs:
        if tx.reverses is None and tx.transaction_id not in reversed_ids:
            refs = [r for r in tx.sources if r.kind in ("fill", "action")]
            if refs:
                if len(refs) != 1 or _key(refs[0]) in result:
                    raise SourceConflict("multiple active economic transactions for one source")
                result[_key(refs[0])] = tx
    return result


def _validate_sources(account_id, through, sources, ledger, head, calendar):
    accounts = AccountRegistry(ledger.db, ledger._audit, ledger._command_clock)
    snapshots = PortfolioSnapshotStore(ledger.db, ledger._audit, accounts, ledger._command_clock)
    start = snapshots.starting_state(account_id)
    if tuple(r for r in sources.records if isinstance(r, StartingState)) != (start,):
        raise SourceConflict("source bundle does not contain the stored starting state")
    expected_opening = opening_bundle(start, at=through).references[0]
    if expected_opening not in sources.references:
        raise SourceConflict("opening source receipt mismatch")
    orders = OrderStore(ledger.db, role=ProcessRole.CORE, audit=ledger._audit, outbox=ledger._outbox, clock=ledger._clock)
    pairs = [r for r in sources.records if isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], Order) and isinstance(r[1], Fill)]
    actual = [(o, f) for o, _ in orders.for_account(account_id) for f in orders.fills(o.order_id)
              if max(f.executed_at, f.delivered_at, f.recorded_at) <= through]
    if {f.fill_id for _, f in pairs} != {f.fill_id for _, f in actual}:
        raise AccountingUnavailable(account_id, through, ("source prefix omits or adds accepted OMS fills",), sources.references)
    selected = {expected_opening.source_id: expected_opening}
    events = []
    ever_held = {i for i, _ in start.positions}
    for order, fill in pairs:
        ref = validate_fill(order, fill, account_id=account_id, at=through, orders=orders)
        if ref not in sources.references:
            raise SourceConflict("fill receipt mismatch")
        if fill.executed_at < start.effective_at:
            raise AccountingUnavailable(account_id, through, ("accepted fill predates the declared initial condition",), (ref,))
        selected[ref.source_id] = ref
        ever_held.add(order.instrument_id)
        events.append((fill.executed_at, 1, fill.fill_id, ref, (order, fill)))
    coverages = [r for r in sources.records if isinstance(r, ActionCoverage)]
    first = start.effective_at.astimezone(ZoneInfo(calendar.timezone)).date()
    last = through.astimezone(ZoneInfo(calendar.timezone)).date()
    by_instrument = {}
    for instrument in ever_held:
        matching = [c for c in coverages if c.source == sources.provider and c.instrument_id == instrument]
        if len(matching) != 1:
            raise AccountingUnavailable(account_id, through, (f"missing unambiguous action coverage for {instrument}",))
        cov = matching[0]
        try:
            for kind in (ActionType.SPLIT, ActionType.DIVIDEND):
                require_coverage(cov, source=sources.provider, instrument_id=instrument, action_type=kind, first=first, last=last, at=through)
        except AdjustmentUnavailable as exc:
            raise AccountingUnavailable(account_id, through, (str(exc),)) from None
        by_instrument[instrument] = cov
        proof = (sources.coverage_ref, tuple(sorted(cov.evidence_refs)), sources.model_version)
        proof_hash = identity(proof)
        prior = next((r for r in head.sources if r.kind == "coverage" and r.identity == f"{account_id}/{instrument}/{proof_hash}"), None)
        ref = prior or SourceRef("coverage", f"{account_id}/{instrument}/{proof_hash}", 1,
                                 json.dumps(proof, separators=(",", ":")), proof_hash, start.effective_at, through, through, sources.provider)
        selected[ref.source_id] = ref
    action_records = [r for r in sources.records if isinstance(r, CorporateAction)]
    if action_records or ever_held:
        # Optional extra remains lazy: plain installation can import accounting contracts.
        from investment_engine.market.store.reader import MarketDataReader

        contexts = [r for r in sources.records if isinstance(r, Mapping) and "market_root" in r]
        if len(contexts) > 1:
            raise ValueError("ambiguous market store root")
        reader = MarketDataReader(Path(contexts[0]["market_root"]) if contexts else market_store_dir())
        grouped = defaultdict(list)
        for action in action_records:
            if action.exchange_timezone != calendar.timezone or action.instrument_id not in by_instrument:
                raise AccountingUnavailable(account_id, through, ("unsupported action context or missing instrument coverage",))
            candidates = [r for r in sources.references if r.kind == "action" and r.content_hash == identity(action)]
            if len(candidates) != 1:
                raise SourceConflict("action revision needs one exact receipt")
            ref = validate_action(action, account_id=account_id, reader=reader, provider=sources.provider,
                                  instrument_id=action.instrument_id, delivered_at=candidates[0].delivered_at,
                                  at=through, calendar=calendar, coverage=by_instrument[action.instrument_id])
            if ref != candidates[0]:
                raise SourceConflict("action receipt differs from validated content")
            if start.effective_at < ref.effective_at <= through:
                grouped[_key(ref)].append((ref, action))
        for instrument in ever_held:
            # A physically available revision not yet delivered is a visible gap,
            # never permission to silently claim complete current accounting.
            stored = reader.actions_visible_at(sources.provider, instrument, first, last + timedelta(days=1), through)
            supplied = {(a.source, a.instrument_id, a.action_type, a.ex_date, a.revision) for a in action_records}
            if any(start.effective_at < calendar.session(a.ex_date).open <= through and
                   (a.source,a.instrument_id,a.action_type,a.ex_date,a.revision) not in supplied for a in stored):
                raise AccountingUnavailable(account_id, through, ("available action revision missing from delivered source prefix",))
        for rows in grouped.values():
            ref, action = max(rows, key=lambda pair: pair[0].revision)
            selected[ref.source_id] = ref
            events.append((ref.effective_at, 0, ref.identity, ref, action))
    expected_refs = {r.source_id for r in sources.references if r.kind in ("fill", "opening") or (r.kind == "action" and r.effective_at <= through)}
    consumed_refs = {r.source_id for _, _, _, r, _ in events} | {expected_opening.source_id}
    # Earlier action revisions may accompany the newest delivered one as evidence.
    earlier = {r.source_id for r in sources.references if r.kind == "action" and any(_key(r)==_key(x) and r.revision < x.revision for x in selected.values())}
    if not expected_refs <= consumed_refs | earlier:
        raise SourceConflict("unmatched source receipt")
    return start, orders, tuple(sorted(events)), tuple(selected.values())


def sync_account(account_id, *, through, sources, ledger):
    check_utc(through, "through")
    if not isinstance(sources, SourceBundle) or sources.account_id != account_id or sources.cutoff != through:
        raise ValueError("account and cutoff must match the source bundle")
    if through != ledger._clock.now():
        raise ValueError("posting knowledge time must be the injected processing clock")
    if not sources.complete:
        raise AccountingUnavailable(account_id, through, sources.omissions, sources.references)
    with ledger.db.transaction():
        ledger.db.lock(f"account-control|{account_id}")
        ledger.db.lock(f"ledger|{account_id}")
        activation = ledger.activation(account_id)
        if activation is None:
            raise AccountingUnavailable(account_id, through, ("explicit ledger activation required",))
        head = ledger.read_head(account_id, known_at=through)
        calendar = load_us_equities_calendar()
        start, orders, events, desired = _validate_sources(account_id, through, sources, ledger, head, calendar)
        desired_economic = {_key(r): r for r in desired if r.kind in ("opening", "fill", "action")}
        previous = {}
        for ref in head.sources:
            if ref.kind in ("opening", "fill", "action") and (_key(ref) not in previous or ref.revision > previous[_key(ref)].revision):
                previous[_key(ref)] = ref
        if not previous.keys() <= desired_economic.keys():
            raise AccountingUnavailable(account_id, through, ("source prefix loses previously recorded facts",), tuple(previous.values()))
        for key, old in previous.items():
            new = desired_economic[key]
            if new.revision < old.revision or (new.revision == old.revision and new != old):
                raise SourceConflict("immutable source revision changed or went backwards")
        desired_ids = {r.source_id for r in desired}
        if desired_ids <= {r.source_id for r in head.sources}:
            return SyncReport(head.book_id, False, (), ())
        fifo = FifoBook(account_id, at=through)
        row = ledger.db.fetchone("SELECT content FROM ledger_activations WHERE account_id=:a", {"a": account_id})
        _, opening_lots, _ = decode(json.loads(row[0]))
        for lot in opening_lots:
            fifo.acquire(lot.instrument_id, lot.quantity, lot.total_cost, lot.declaration_id, at=lot.effective_at, opening=True)
        ownership = [(start.effective_at, dict(start.positions))]
        plans = {}
        matches = {}
        for effective, kind, _stable, ref, record in events:
            if kind == 1:
                order, fill = record
                plan = plan_fifo_fill(order, fill, ref=ref, posted_at=through, fifo=fifo)
                plans[_key(ref)] = plan.transaction
                matches[_key(ref)] = plan.lot_matches
            else:
                prior_close = calendar.previous_session(record.ex_date).close
                held = next((positions for at, positions in reversed(ownership) if at <= prior_close), {})
                plans[_key(ref)] = plan_action(record, ref=ref, posted_at=through, fifo=fifo, calendar=calendar,
                                               prior_close_quantity=held.get(record.instrument_id, Decimal(0)), orders=orders)
            quantities = defaultdict(Fraction)
            for lot in fifo.lots():
                quantities[lot.instrument_id] += Fraction(lot.remaining_quantity)
            ownership.append((effective, {i:exact_decimal(q) for i,q in quantities.items()}))
        active = _active(ledger, head)
        reversals, replacements, new_matches = [], [], []
        for key in sorted(active.keys() | plans.keys()):
            old, new = active.get(key), plans.get(key)
            if old is not None and new is not None and _economic(old) == _economic(new):
                row = ledger.db.fetchone("SELECT book_id FROM ledger_transactions WHERE transaction_id=:id", {"id": old.transaction_id})
                old_matches = tuple(m for m in ledger.get(row[0]).lot_matches
                                    if any(m.disposal == ref.stored_record_id for ref in old.sources))
                def evidence(values):
                    return tuple((m.match_id, m.acquisition, m.disposal, m.quantity, m.cost, m.unit, m.policy_version)
                                 for m in sorted(values, key=lambda m: m.match_id))
                if evidence(old_matches) == evidence(matches.get(key, ())):
                    continue
            if old is not None:
                reversals.append(reverse_transaction(old, posted_at=through))
            if new is not None:
                replacements.append(new)
                new_matches.extend(matches.get(key, ()))
        refs = {r.source_id:r for r in (*head.sources,*desired)}
        batch = BookBatch(account_id, head.book_id, head.version+1, head.policy_version, tuple(refs.values()),
                          tuple(reversals+replacements), tuple(new_matches), through)
        batch = replace(batch, lot_matches=tuple(replace(m,book_id=batch.book_id) for m in new_matches))
        ledger.append_batch(batch)
        return SyncReport(batch.book_id, True, tuple(tx.reverses for tx in reversals), tuple(tx.transaction_id for tx in replacements))
