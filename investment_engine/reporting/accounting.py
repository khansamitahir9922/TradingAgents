"""Read-only, pinned accounting reports. Stored facts are not trading performance claims."""
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from html import escape
from zoneinfo import ZoneInfo

from investment_engine.ledger.balances import balances, value_balances
from investment_engine.ledger.contracts import AccountingUnavailable, BalanceQuery
from investment_engine.ledger.lots import exact_decimal
from investment_engine.lineage.records import decode
from investment_engine.market.availability import check_provider, check_utc
from investment_engine.portfolio.snapshot import SnapshotSource


def plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [plain(v) for v in value]
    if isinstance(value, float):
        raise TypeError("accounting output cannot contain float values")
    return value


@dataclass(frozen=True)
class AccountingReport:
    account_id: str
    book_id: str
    query_id: str
    effective_at: datetime
    known_at: datetime
    mode: str
    complete: bool
    reasons: tuple[str, ...]
    data_json: str  # immutable presentation data, no mutable dictionaries inside this model

    @property
    def label(self):
        return "LEDGER | SIMULATED | RESEARCH | NOT PROMOTED" if self.mode == "RESEARCH" else "LEDGER | PAPER | TRADING NOT AUTHORIZED BY THIS REPORT"

    def to_json(self):
        value = json.loads(self.data_json)
        value.update(account_id=self.account_id, book_id=self.book_id, query_id=self.query_id,
                     effective_at=self.effective_at.isoformat(), known_at=self.known_at.isoformat(),
                     timezone="UTC", mode=self.mode, label=self.label, complete=self.complete, reasons=list(self.reasons))
        return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True)

    def to_text(self):
        p = json.loads(self.to_json())
        lines = [self.label, "COMPLETE" if self.complete else "INCOMPLETE", f"Account: {self.account_id}",
                 f"Book: {self.book_id}; query: {self.query_id}", f"Effective: {self.effective_at.isoformat()} UTC",
                 f"Known: {self.known_at.isoformat()} UTC", f"Mark provider: {p['mark_provider']}"]
        for key, value in p["metrics"].items():
            lines.append(f"{key}: {'UNAVAILABLE' if value is None else value} USD")
        lines += [f"daily_pnl: {p['daily_pnl'] if p['daily_pnl'] is not None else 'UNAVAILABLE'} USD; {p['daily_reason']}",
                  f"Reconciliation: {p['reconciliation_status']}"]
        lines.extend("Reason: " + r for r in self.reasons)
        # Full source times, quantities, lots and incident histories remain visible
        # in every format, not only a colored headline.
        for name in ("positions", "costs", "receivables", "opening_lots", "lot_matches", "sources", "mark_refs", "incidents"):
            lines.append(name + ": " + json.dumps(p[name], sort_keys=True))
        return "\n".join(lines)

    def to_html(self):
        return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Accounting report</title>'
                '<main><h1>Accounting report</h1><pre>' + escape(self.to_text(), quote=True) + '</pre></main></html>')


def build_report(account_id, *, effective_at, known_at, book_id, ledger, calendar, source, marks, previous=None):
    check_utc(effective_at, "effective_at")
    check_utc(known_at, "known_at")
    check_provider(source)
    head = ledger.get(book_id)
    if head.account_id != account_id or head.posted_at > known_at:
        raise ValueError("book account/knowledge cutoff mismatch")
    account = ledger.db.fetchone("SELECT kind FROM accounts WHERE account_id=:a", {"a": account_id})
    for instrument, (candle, delivered) in marks.items():
        check_utc(delivered, "delivery time")
        if candle.instrument_id != instrument or candle.source != source or max(candle.available_from, delivered) > known_at:
            raise ValueError("mark provider/instrument/future cutoff mismatch")
    value = balances(account_id, effective_at=effective_at, known_at=known_at, book_id=book_id, ledger=ledger)
    if isinstance(value, AccountingUnavailable):
        payload = {"metrics": dict.fromkeys(("cash", "gross_realized", "dividend_income", "fees", "opening_capital",
                                              "market_value", "unrealized", "equity", "net_pnl")),
            "units": {"money": "USD", "quantity": "SHARES"}, "positions": None, "costs": None, "receivables": None,
            "opening_lots": None, "lot_matches": None, "sources": plain(value.sources), "mark_refs": [],
            "mark_provider": source, "daily_pnl": None, "daily_reason": "accounting endpoint unavailable",
            "reconciliation_status": "NOT ASSESSED: ACCOUNTING UNAVAILABLE", "incidents": None}
        return AccountingReport(account_id, book_id, BalanceQuery(account_id, effective_at, known_at, book_id).query_id,
            effective_at, known_at, account[0], False, tuple(value.reasons), json.dumps(payload, sort_keys=True))
    valued = value_balances(value, marks=marks, calendar=calendar, source=source, ledger=ledger)
    reasons = list(valued.reasons)
    history = ledger.ancestry(book_id)
    ever_held = {entry.unit.code for batch in history for tx in batch.transactions
                if tx.effective_at <= effective_at and tx.posted_at <= known_at for entry in tx.entries
                if entry.unit.kind == "SECURITY"}
    coverage_missing = []
    for instrument in sorted(ever_held):
        candidates = [r for r in value.sources if r.kind == "coverage" and r.identity.startswith(f"{account_id}/{instrument}/")]
        if candidates and any(r.provider != source for r in candidates):
            raise ValueError("mark provider differs from the ledger's action coverage provider")
        supported = set()
        for ref in candidates:
            try:
                from investment_engine.quant.adjusted import VerificationEvidence
                _, evidence, _ = json.loads(ref.stored_record_id)
                first = ref.effective_at.astimezone(ZoneInfo(calendar.timezone)).date()
                last = effective_at.astimezone(ZoneInfo(calendar.timezone)).date()
                for text in evidence:
                    ev = VerificationEvidence.parse(text)
                    if (ev.status == "COMPLETE" and ev.provider == source and ev.instrument_id == instrument
                            and ev.first <= first <= last <= ev.last):
                        supported.add(ev.action_type.value)
            except (ValueError, TypeError):
                continue
        if not {"SPLIT", "DIVIDEND"} <= supported:
            coverage_missing.append(f"action coverage unavailable for {instrument} at the pinned book/cutoff")
    reasons.extend(coverage_missing)
    stored = ledger.db.fetchone("SELECT content FROM reconciliation_results WHERE account_id=:a AND at<=:e AND recorded_at<=:k ORDER BY sequence DESC LIMIT 1",
                               {"a": account_id, "e": effective_at, "k": known_at})
    comparison = None if stored is None else decode(json.loads(stored[0]))
    status = "NOT RECORDED"
    if comparison is not None:
        status = comparison.status if comparison.book_id == book_id and comparison.at == effective_at else "NOT COMPARABLE TO THIS PINNED QUERY"
    incidents = []
    unresolved = []
    for (iid,) in ledger.db.fetchall("SELECT incident_id FROM reconciliation_incidents WHERE account_id=:a AND opened_at<=:e ORDER BY opened_at,incident_id",
                                     {"a": account_id, "e": min(effective_at, known_at)}):
        incident_history = tuple(decode(json.loads(row[0])) for row in ledger.db.fetchall(
            "SELECT content FROM reconciliation_transitions WHERE incident_id=:i AND business_at<=:t ORDER BY sequence",
            {"i": iid, "t": min(effective_at, known_at)}))
        incidents.append({"incident_id": iid, "history": plain(incident_history)})
        if incident_history and incident_history[-1].state != "RESOLVED":
            unresolved.append(iid)
    if unresolved:
        reasons.append("unresolved reconciliation incidents: " + ", ".join(unresolved))
    complete = valued.complete and not unresolved and not coverage_missing
    metrics = {"cash": value.cash, "gross_realized": value.gross_realized, "dividend_income": value.dividend_income,
               "fees": value.fees, "opening_capital": valued.opening_capital,
               "market_value": valued.market_value if complete else None, "unrealized": valued.unrealized if complete else None,
               "equity": valued.equity if complete else None, "net_pnl": valued.net_pnl if complete else None}
    daily, daily_reason = None, "comparable complete daily endpoints not recorded"
    if previous is not None:
        if not isinstance(previous, AccountingReport) or previous.account_id != account_id:
            raise ValueError("daily endpoint account/type mismatch")
        old = json.loads(previous.to_json())
        comparable = (previous.complete and complete and previous.book_id == book_id and previous.known_at == known_at
                      and old["mark_provider"] == source and previous.effective_at == calendar.previous_session(effective_at.date()).close
                      and effective_at == calendar.session(effective_at.date()).close)
        if comparable:
            daily = exact_decimal(Fraction(valued.equity) - Fraction(Decimal(old["metrics"]["equity"])))
            daily_reason = "equity change across complete comparable session-close endpoints; fixed declared capital"
    activation = ledger.db.fetchone("SELECT content FROM ledger_activations WHERE account_id=:a", {"a": account_id})
    opening_lots = () if activation is None else decode(json.loads(activation[0]))[1]
    payload = {"metrics": plain(metrics), "units": {"money": "USD", "quantity": "SHARES"},
        "positions": plain(value.positions), "costs": plain(value.costs), "receivables": plain(value.receivables),
        "opening_lots": plain(opening_lots), "lot_matches": plain(tuple(m for b in history for m in b.lot_matches)),
        "lot_scope": "immutable historical allocation audit through the pinned book; costs above are current held basis",
        "sources": plain(value.sources), "mark_refs": plain(valued.mark_refs), "mark_provider": source,
        "policy_version": head.policy_version, "daily_pnl": plain(daily), "daily_reason": daily_reason,
        "reconciliation_status": status, "reconciliation": plain(comparison), "incidents": incidents}
    return AccountingReport(account_id, book_id, value.query.query_id, effective_at, known_at, account[0], complete,
                              tuple(reasons), json.dumps(payload, sort_keys=True))


def legacy_snapshot_report(snapshot):
    if snapshot.source is SnapshotSource.LEDGER:
        raise ValueError("a ledger snapshot requires its pinned accounting report")
    return {"label": snapshot.source.value + " | HISTORICAL PORTFOLIO SNAPSHOT",
            "snapshot_id": snapshot.snapshot_id, "book_id": None, "basis": None,
            "reason": "ledger cost/audit fields were not recorded in this legacy snapshot",
            "as_of": snapshot.as_of.isoformat(), "cash": str(snapshot.cash), "equity": str(snapshot.equity)}
