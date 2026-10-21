"""Read-only accounting output and explicit, current-Admin ledger/incident commands."""
import json
from datetime import timedelta
from pathlib import Path
from typing import Annotated

import typer

from investment_engine.clock import LiveClock, ReplayClock

accounting_app = typer.Typer(no_args_is_help=True, help="Pinned read-only accounting reports; no trading or data downloads.")
ledger_app = typer.Typer(no_args_is_help=True, help="Explicit ledger activation and source synchronization (Admin).")
incidents_app = typer.Typer(no_args_is_help=True, help="Audited incident acknowledgement/resolution (Admin).")


def _with_db(action, *, read_only):
    from investment_engine.cli import _fail, _open_db
    conn = None
    try:
        conn, db = _open_db(read_only=read_only)
        action(db)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc)
    finally:
        if conn is not None:
            conn.close()


def _timestamp(value):
    from investment_engine.cli import _timestamp as timestamp
    return timestamp(value)


def _context(db, account_id, at):
    from investment_engine.audit.events import AuditStore
    from investment_engine.policy.accounts import AccountKind, AccountRegistry
    live = LiveClock()
    audit = AuditStore(db)
    accounts = AccountRegistry(db, audit, live)
    account = accounts.account(account_id)
    if account.kind is AccountKind.RESEARCH:
        if at is None:
            raise ValueError("RESEARCH commands require an explicit replay --at")
        clock = ReplayClock(_timestamp(at))
    else:
        if at is not None:
            raise ValueError("PAPER commands cannot supply a replay time")
        clock = live
    return audit, accounts, live, clock


def _ledger(db, audit, live, clock):
    from investment_engine.events.outbox import Outbox
    from investment_engine.ledger.store import LedgerStore
    from investment_engine.oms.order_states import ProcessRole
    return LedgerStore(db, audit=audit, outbox=Outbox(db, writer=ProcessRole.CORE, clock=clock),
                        clock=clock, command_clock=live)


def _bundle(path, account_id, at):
    from investment_engine.ledger.contracts import SourceBundle
    from investment_engine.lineage.records import decode
    bundle = decode(json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(bundle, SourceBundle) or bundle.account_id != account_id or bundle.cutoff != at:
        raise ValueError("source bundle account/cutoff mismatch")
    return bundle


def read_report(db, account_id, *, book, effective_at, known_at, source="yfinance"):
    from investment_engine.audit.events import AuditStore
    from investment_engine.config import market_store_dir
    from investment_engine.ledger.balances import balances
    from investment_engine.ledger.contracts import AccountingUnavailable
    from investment_engine.market.calendar.us_equities import load_us_equities_calendar
    from investment_engine.market.candles import Timeframe
    from investment_engine.market.store.reader import MarketDataReader
    from investment_engine.portfolio.snapshot import _expected_session
    from investment_engine.reporting.accounting import build_report
    calendar = load_us_equities_calendar()
    clock = ReplayClock(known_at)
    ledger = _ledger(db, AuditStore(db), LiveClock(), clock)
    value = balances(account_id, effective_at=effective_at, known_at=known_at, book_id=book, ledger=ledger)
    marks = {}
    if not isinstance(value, AccountingUnavailable) and value.positions:
        reader = MarketDataReader(market_store_dir())
        session = _expected_session(calendar, effective_at)
        for instrument, _ in value.positions:
            candidates = [c for c in reader.candle_revision_history(source, instrument, Timeframe.D1,
                            session.open, session.open + timedelta(microseconds=1))
                          if max(c.available_from, c.received_at) <= known_at]
            if candidates:
                candle = max(candidates, key=lambda c: c.revision)
                # Store-observed delivery only. A replay report needing a different
                # delivery prefix must use the explicit public builder, never
                # silently substitute availability for receipt.
                marks[instrument] = (candle, candle.received_at)
    return build_report(account_id, effective_at=effective_at, known_at=known_at, book_id=book,
                          ledger=ledger, calendar=calendar, source=source, marks=marks)


@accounting_app.command("report")
def report(account_id: str, book: str = typer.Option(..., "--book"),
           effective_at: str = typer.Option(..., "--effective-at"), known_at: str = typer.Option(..., "--known-at"),
           format: str = typer.Option("text", "--format"), source: str = typer.Option("yfinance", "--source"),
           output: Annotated[Path | None, typer.Option("--output")] = None):
    """Read one explicitly pinned accounting query. No migrations, synchronization or acknowledgements."""
    def action(db):
        from investment_engine.cli import _print
        if format not in ("text", "json", "html"):
            raise ValueError("format must be text, json or html")
        value = read_report(db, account_id, book=book, effective_at=_timestamp(effective_at),
                            known_at=_timestamp(known_at), source=source)
        text = getattr(value, "to_" + format)()
        if output is None:
            _print(text)
        else:
            # Exclusive creation preserves earlier exported evidence.
            with output.open("x", encoding="utf-8") as stream:
                stream.write(text)
    _with_db(action, read_only=True)


@ledger_app.command("activate")
def activate(account_id: str, operator: str = typer.Option(..., "--operator"), reason: str = typer.Option(..., "--reason"),
             at: str | None = typer.Option(None, "--at"), opening_lots: Annotated[Path | None, typer.Option("--opening-lots")] = None):
    """Declare the authoritative ledger from saved starting cash and explicit opening basis; never reprice it."""
    def action(db):
        from investment_engine.admin_cli import _actor
        from investment_engine.cli import _print
        from investment_engine.ledger.sources import opening_bundle
        from investment_engine.lineage.records import decode
        from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
        audit, accounts, live, clock = _context(db, account_id, at)
        states = PortfolioSnapshotStore(db, audit, accounts, live)
        lots = () if opening_lots is None else tuple(decode(json.loads(opening_lots.read_text(encoding="utf-8"))))
        value = _ledger(db, audit, live, clock).activate(account_id, opening_lots=lots,
            source_bundle=opening_bundle(states.starting_state(account_id), at=clock.now()),
            by=_actor(accounts, operator), reason=reason)
        _print("LEDGER activated: " + value.book_id + "; reconciliation and trading are not enabled by activation.")
    _with_db(action, read_only=False)


@ledger_app.command("sync")
def sync(account_id: str, sources: Annotated[Path, typer.Option("--sources")], at: str = typer.Option(..., "--at"),
         operator: str = typer.Option(..., "--operator"), reason: str = typer.Option(..., "--reason")):
    """Synchronize an explicit validated RESEARCH source bundle; no broker discrepancies become postings."""
    def action(db):
        from investment_engine.admin_cli import _actor
        from investment_engine.audit.events import AuditEvent
        from investment_engine.cli import _print
        from investment_engine.ledger.restate import sync_account
        from investment_engine.market.availability import check_name
        from investment_engine.policy.accounts import Role
        check_name(reason, "reason")
        audit, accounts, live, clock = _context(db, account_id, at)
        ledger = _ledger(db, audit, live, clock)
        bundle = _bundle(sources, account_id, clock.now())
        actor = _actor(accounts, operator)
        with db.transaction():
            db.lock(f"account-control|{account_id}")
            db.lock(f"ledger|{account_id}")
            db.lock(f"operator|{operator}")
            now = live.now()
            accounts.authorize(actor, (Role.ADMIN,), now)
            result = sync_account(account_id, through=clock.now(), sources=bundle, ledger=ledger)
            audit.append(AuditEvent(actor, "ledger.sync", "account", account_id, None, {"book_id": result.book_id},
                now, clock.now(), reason, result.book_id, "admin-sync:" + result.book_id + ":" + now.isoformat()))
        _print("LEDGER synchronized: " + result.book_id + "; broker reconciliation is a separate Core step.")
    _with_db(action, read_only=False)


def _incident_command(db, incident_id, *, operator, reason, expected_sequence, at, match_id=None, sources=None):
    from investment_engine.admin_cli import _actor
    from investment_engine.events.outbox import Outbox
    from investment_engine.ledger.service import AccountingService
    from investment_engine.market.calendar.us_equities import load_us_equities_calendar
    from investment_engine.oms.order_states import ProcessRole
    from investment_engine.reconciliation.incidents import IncidentStore
    row = db.fetchone("SELECT account_id FROM reconciliation_incidents WHERE incident_id=:i", {"i": incident_id})
    if row is None:
        raise KeyError(incident_id)
    account_id = row[0]
    audit, accounts, live, clock = _context(db, account_id, at)
    store = IncidentStore(db, audit=audit, accounts=accounts, clock=clock, command_clock=live,
        outbox=Outbox(db, writer=ProcessRole.CORE, clock=clock))
    actor = _actor(accounts, operator)
    if match_id is None:
        return store.acknowledge(incident_id, expected_sequence=expected_sequence, by=actor, reason=reason)
    if sources is None:
        raise ValueError("resolve needs the current source bundle, not merely a stored MATCH id")
    bundle = _bundle(sources, account_id, clock.now())
    class PinnedSources:
        calendar = load_us_equities_calendar()
        def __call__(self, requested, cutoff):
            if requested != account_id or cutoff != bundle.cutoff:
                raise ValueError("source bundle is not current for this account/cutoff")
            return bundle
    service = AccountingService(db, clock=clock, command_clock=live, sources=PinnedSources())
    return service.incidents.resolve(incident_id, expected_sequence=expected_sequence, match_id=match_id,
                                       by=actor, reason=reason)


@incidents_app.command("acknowledge")
def acknowledge(incident_id: str, expected_sequence: int = typer.Option(..., "--expected-sequence"),
                operator: str = typer.Option(..., "--operator"), reason: str = typer.Option(..., "--reason"),
                at: str | None = typer.Option(None, "--at")):
    def action(db):
        from investment_engine.cli import _print
        result = _incident_command(db, incident_id, operator=operator, reason=reason,
                                     expected_sequence=expected_sequence, at=at)
        _print(result.state + ": unresolved; no balances or kill-switch flag changed.")
    _with_db(action, read_only=False)


@incidents_app.command("resolve")
def resolve(incident_id: str, sources: Annotated[Path, typer.Option("--sources")], match: str = typer.Option(..., "--match"),
            expected_sequence: int = typer.Option(..., "--expected-sequence"), operator: str = typer.Option(..., "--operator"),
            reason: str = typer.Option(..., "--reason"), at: str | None = typer.Option(None, "--at")):
    def action(db):
        from investment_engine.cli import _print
        result = _incident_command(db, incident_id, operator=operator, reason=reason,
            expected_sequence=expected_sequence, at=at, match_id=match, sources=sources)
        _print(result.state + ": current matching evidence verified; trading was not resumed.")
    _with_db(action, read_only=False)
