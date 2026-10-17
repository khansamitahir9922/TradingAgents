"""The intents report: M3's visible result (architecture Part K; PRD 8; docs/tasks/M3-14.md).

`views replay` runs M2's view pipeline over the local market-data store into
the lineage store, offline. `intents propose` proposes those views for one
account: a RESEARCH account over a replay range (`--from`/`--to`) or at one
replay time (`--at`); a PAPER account only at the live time. `intents list`
and `intents show` print what happened and why: every version, every policy
and risk check with its reason, reductions, deadlines and expiries in UTC and
exchange time, approvers and lineage ids, and for views without an intent the
proposal's reason. Unavailable values say why, never 0.

Every output starts with the safety state (PRD principle 2): the account and
its kind, its autonomy level, PAPER or RESEARCH mode, that no orders exist
yet, that the kill switch isn't built, that the portfolio is the declared
start, and the limit versions in force. Output is plain ASCII, deterministic
for the same database state, and never shows connection details. Nothing here
downloads data; missing local data is reported with the import command the
owner would run.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import typer

from investment_engine.admin_cli import intents_app
from investment_engine.clock import LiveClock, ReplayClock

views_app = typer.Typer(no_args_is_help=True, help="MarketViews replayed into the lineage store (offline).")
NVDA = "EQ_US_NVDA"
SOURCE = "yfinance"


def _say(text: str) -> None:
    from investment_engine.cli import _print

    _print(text)


def _day(text: str) -> date:
    return date.fromisoformat(text)


def _stores(conn_db, clock):
    from investment_engine.oms.pipeline import ControlStores
    from investment_engine.storage.sqlite import SqliteInstrumentRepository

    return ControlStores.open(conn_db, clock, instruments=SqliteInstrumentRepository(conn_db))


def _run(command, *, read_only: bool = False) -> None:
    """Open the Operational Database (read-only for list and show, M3-14 rule 5), run `command(db)`, close."""
    from investment_engine.cli import _fail, _open_db

    conn = None
    try:
        conn, db = _open_db(read_only=read_only)
        command(db)
    except typer.Exit:
        raise
    except LookupError as exc:  # unknown ids, missing limits: plain domain text
        _say(f"Cannot complete command: {exc}")
        raise typer.Exit(1) from None
    except Exception as exc:
        _fail(exc)
    finally:
        if conn is not None:
            conn.close()


def _coverage(at: datetime):
    from investment_engine.market.corporate_actions import ActionType
    from investment_engine.market.importers.yahoo_semantics import YAHOO_VERIFICATION
    from investment_engine.quant.adjusted import VerificationEvidence

    first, last = YAHOO_VERIFICATION.verified_from, YAHOO_VERIFICATION.verified_on
    note = f"YAHOO_VERIFICATION verified_on={last} yfinance={YAHOO_VERIFICATION.yfinance_version}"
    evidence = tuple(VerificationEvidence(SOURCE, NVDA, t, first, last, date(1999, 1, 22), last, note, "COMPLETE")
                     for t in (ActionType.SPLIT, ActionType.DIVIDEND))
    reason = ("research assumption from the verified Yahoo import (docs/data-provenance/yfinance.md); "
              "not a historical observation")
    return evidence, first, last, reason


def _versions():
    import investment_engine
    from investment_engine.cli import shipped_calendars

    (calendar_version,) = shipped_calendars()
    return calendar_version, f"investment_engine {investment_engine.__version__}"


def _market():
    from investment_engine.cli import _load_store
    from investment_engine.config import market_store_dir

    reader_type, _ = _load_store()
    root = market_store_dir()
    if not root.exists():
        raise FileNotFoundError(f"no local market data at {root}; run 'python -m investment_engine import-yfinance' "
                                "first (that is an explicit online import; nothing is downloaded here)")
    return reader_type(root)


# ---------------------------------------------------------------- views replay


@views_app.command("replay")
def views_replay(instrument: str = NVDA, from_day: str = typer.Option(..., "--from"),
                 to_day: str = typer.Option(..., "--to")) -> None:
    """Replay the local daily bars into MarketViews with lineage (M2's pipeline); offline."""
    def go(db):
        from datetime import UTC

        from investment_engine.decision.pipeline import run_views
        from investment_engine.lineage.records import LineageStore
        from investment_engine.market.calendar.us_equities import load_us_equities_calendar
        from investment_engine.market.candles import Timeframe
        from investment_engine.market.replay import ReplayFeed
        from investment_engine.quant.strategies.pullback import PullbackStrategy
        from investment_engine.quant.strategies.trend import TrendStrategy
        from investment_engine.storage.sqlite import (
            SqliteInstrumentRepository,
            SqliteSymbolResolver,
        )

        reader, calendar = _market(), load_us_equities_calendar()
        start = datetime.combine(_day(from_day), datetime.min.time(), tzinfo=UTC)
        end = datetime.combine(_day(to_day) + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        feed = ReplayFeed(reader, ReplayClock(start), sources=[SOURCE], instrument_ids=[instrument],
                          timeframes=[Timeframe.D1], start=start, end=end)
        evidence, first, last, reason = _coverage(end)
        calendar_version, code_version = _versions()
        views = list(run_views(feed, instrument_id=instrument, source=SOURCE,
                               strategies=(TrendStrategy(), PullbackStrategy()), policy_version="0.1.0",
                               calendar=calendar, instruments=SqliteInstrumentRepository(db),
                               resolver=SqliteSymbolResolver(db), lineage_store=LineageStore(db),
                               coverage_evidence=evidence, coverage_first=first, coverage_last=last,
                               coverage_reason=reason, calendar_version=calendar_version,
                               code_version=code_version))
        if not views:
            _say(f"no daily bars for {instrument} from {from_day} to {to_day} in the local store; run "
                 "'python -m investment_engine import-yfinance' first. Nothing was written.")
            raise typer.Exit(1)
        counts = {}
        for v in views:
            counts[v.direction.value] = counts.get(v.direction.value, 0) + 1
        _say(f"{len(views)} views replayed with lineage: "
             + ", ".join(f"{k} {counts[k]}" for k in sorted(counts)) + ". RESEARCH DATA (yfinance), offline.")
    _run(go)


# ---------------------------------------------------------------- propose


def _views_between(db, instrument: str, first: datetime, last: datetime):
    from dataclasses import replace

    from investment_engine.lineage.records import LineageStore

    store = LineageStore(db)
    out = []
    for lineage_id in store.ids(instrument):
        record = store.get(lineage_id)
        if first <= record.generated_at <= last:
            out.append(replace(record.decision, evidence_refs=(lineage_id,)))
    return out


@intents_app.command("propose")
def propose_intents(account: str = typer.Option(..., "--account"), at: str | None = typer.Option(None, "--at"),
                    from_day: str | None = typer.Option(None, "--from"),
                    to_day: str | None = typer.Option(None, "--to"), instrument: str = NVDA) -> None:
    """Propose stored views for an account: a replay range or time (RESEARCH), or now (PAPER)."""
    def go(db):
        from datetime import UTC

        from investment_engine.cli import _timestamp
        from investment_engine.decision.pipeline import ReplayKnowledgeReader
        from investment_engine.market.calendar.us_equities import load_us_equities_calendar
        from investment_engine.market.candles import Timeframe
        from investment_engine.market.replay import ReplayFeed
        from investment_engine.oms.pipeline import propose, propose_over_replay
        from investment_engine.policy.accounts import AccountKind
        from investment_engine.portfolio.reference import StoreKnowledge

        clock, calendar = LiveClock(), load_us_equities_calendar()
        stores = _stores(db, clock)
        kind = stores.accounts.account(account).kind
        reader = _market()
        calendar_version, code_version = _versions()
        if kind is AccountKind.PAPER:
            if at or from_day or to_day:
                raise ValueError("a PAPER account proposes at the live time only; --at/--from/--to are refused")
            now = clock.now()
            views = _views_between(db, instrument, now - timedelta(days=4), now)
            if not views:
                raise ValueError("no stored view of the last few days to propose")
            record = propose(account, views[-1], at=None, stores=stores, knowledge=StoreKnowledge(reader, calendar),
                             calendar=calendar, coverage=None, calendar_version=calendar_version,
                             code_version=code_version, correlation_id=f"cli:{account}:{now.isoformat()}")
            records = [record]  # PAPER acts at the live clock's time; no time is supplied
        else:
            if at:
                first = last = _timestamp(at)
            elif from_day and to_day:
                first = datetime.combine(_day(from_day), datetime.min.time(), tzinfo=UTC)
                last = datetime.combine(_day(to_day) + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
            else:
                raise ValueError("a RESEARCH account needs --at T or --from DATE --to DATE (replay time)")
            views = _views_between(db, instrument, first - timedelta(days=4) if at else first, last)
            if at:
                views = [v for v in views if v.generated_at <= first][-1:]
            if not views:
                raise ValueError("no stored views in that range; run 'views replay' first")
            start = views[0].generated_at - timedelta(days=60)
            end = max(v.generated_at for v in views) + timedelta(microseconds=1)
            feed = ReplayFeed(reader, ReplayClock(start), sources=[SOURCE], instrument_ids=[instrument],
                              timeframes=[Timeframe.D1], start=start, end=end)
            records = propose_over_replay(account, views, events=feed, stores=stores,
                                          knowledge_reader=ReplayKnowledgeReader(), calendar=calendar,
                                          coverage=None, calendar_version=calendar_version,
                                          code_version=code_version)
        _header(stores, account, records[-1].at if records else clock.now())
        for record in records:
            _proposal_line(record, stores)
    _run(go)


# ---------------------------------------------------------------- list and show


LEVEL = {0: "Advisory", 1: "Approved paper", 2: "Automatic paper"}


def _header(stores, account_id: str, at: datetime) -> None:
    from investment_engine.policy.accounts import AccountKind
    from investment_engine.risk.limits import NoLimits

    account = stores.accounts.account(account_id)
    try:
        setting = stores.accounts.autonomy_at(account_id, at)
        level = f"Level {setting.level} ({LEVEL[setting.level]})"
    except LookupError:
        level = "autonomy not set at this time"
    mode = "PAPER MODE" if account.kind is AccountKind.PAPER else "RESEARCH ACCOUNT: SIMULATED / REPLAY"
    try:
        versions = f"{stores.limits.risk_at(account_id, at).version}, {stores.limits.policy_at(account_id, at).version}"
    except NoLimits:
        versions = "no limits effective (every proposal is a missing prerequisite)"
    _say(f"ACCOUNT {account.account_id} {account.kind} | {level} | {mode}")
    _say("NO ORDERS: order management arrives in M4 | KILL SWITCH: NOT BUILT (M4) | "
         "PORTFOLIO: DECLARED STARTING STATE (no ledger until M5)")
    _say(f"limits in force at {at.isoformat()}: {versions}")


def _times(value: datetime | None) -> str:
    if value is None:
        return "not set"
    return f"{value.isoformat()} ({value.astimezone(ZoneInfo('America/New_York')).isoformat()} exchange)"


def _proposal_line(record, stores) -> None:
    """One proposal: its outcome when proposed and, for an intent, the state it is in now."""
    if record.intent_id:
        now = stores.intents.get(record.intent_id).state
        detail = f"intent {record.intent_id} v{','.join(map(str, record.versions))}; now {now}"
    else:
        detail = f"missing: {', '.join(record.missing)}" if record.missing else "no intent"
    _say(f"{record.at.isoformat()} view {record.view_lineage_id[:16]}...: {record.outcome} ({detail}): "
         f"{record.reason}")


def _show(stores, intent_id: str, version: int | None) -> None:
    versions = stores.intents.versions(intent_id)
    if version is not None:
        versions = [v for v in versions if v.intent.version == version]
        if not versions:
            raise LookupError(f"{intent_id} has no version {version}")
    every = {v.intent.version: v for v in stores.intents.versions(intent_id)}
    for stored in versions:
        i = stored.intent
        _say(f"intent {i.intent_id} v{i.version} {stored.state}: {i.side} {i.quantity} {i.instrument_id} "
             f"{i.time_in_force} {i.order_type} limit {i.limit_price} USD; reference {i.reference_price} USD "
             f"(raw close of {i.reference_bar.start_time.date()} rev {i.reference_bar.revision}); target session "
             f"{i.target_session}" + (f"; supersedes v{i.supersedes}" if i.supersedes else ""))
        for label, decision in (("policy", stored.policy_decision), ("risk", stored.risk_decision)):
            if decision is None:
                _say(f"  {label}: not reached")
            elif hasattr(decision, "stage"):
                _say(f"  {label}: NOT RUN ({decision.reason})")
            else:
                outcome = getattr(decision, "outcome", None)
                head = outcome.value if outcome is not None else ("PASSED" if decision.passed else "FAILED")
                extra = f" -> {decision.reduced_quantity}" if getattr(decision, "reduced_quantity", None) else ""
                _say(f"  {label}: {head}{extra}")
                for c in decision.checks:
                    _say(f"    {'ok  ' if c.passed else 'FAIL'} {c.name}: {c.reason}")
        if i.supersedes and i.supersedes in every:
            before = every[i.supersedes]
            why = "; ".join(c.reason for c in before.risk_decision.checks if not c.passed)
            _say(f"  reduction: v{i.supersedes} {before.intent.quantity} -> v{i.version} {i.quantity}: {why} "
                 f"({before.intent.risk_version})")
        _say(f"  approval deadline: {_times(stored.approval_deadline)}")
        _say(f"  approved: {stored.approved_by or 'no'}"
             + (f" at {_times(stored.approved_at)} (recorded {_times(stored.approval_recorded_at)}); expires "
                f"{_times(stored.approval_expires_at)}" if stored.approved_by else ""))
        _say(f"  lineage: {stored.lineage_id or 'not recorded yet'}")


@intents_app.command("list")
def list_intents(account: str = typer.Option(..., "--account"), state: str | None = typer.Option(None, "--state"),
                 session: str | None = typer.Option(None, "--session")) -> None:
    """List an account's proposals and intents, with outcomes and reasons."""
    def go(db):
        stores = _stores(db, LiveClock())
        records = stores.proposals.for_account(account)
        _header(stores, account, records[-1].at if records else LiveClock().now())
        if not records:
            _say("no proposals yet")
        for record in records:
            if state and record.outcome.value != state and not (
                    record.intent_id and stores.intents.get(record.intent_id).state.value == state):
                continue  # --state matches a proposal outcome or the intent's current state
            if session and record.intent_id and stores.intents.get(record.intent_id).intent.target_session != \
                    _day(session):
                continue
            _proposal_line(record, stores)
    _run(go, read_only=True)


@intents_app.command("show")
def show_intent(intent_id: str, version: int | None = typer.Option(None, "--version")) -> None:
    """Show every version of an intent with its checks, reasons, deadlines and lineage."""
    def go(db):
        stores = _stores(db, LiveClock())
        latest = stores.intents.get(intent_id)
        _header(stores, latest.intent.account_id, latest.intent.created_at)
        _show(stores, intent_id, version)
    _run(go, read_only=True)
