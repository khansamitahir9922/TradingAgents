"""Offline replay reports and explicit research imports; partial M1 daily delivery.

This entry point constructs Clocks. It never submits orders or controls trading.
Optional storage/vendor imports are delayed until their commands need them.
"""

import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from zoneinfo import ZoneInfo

import typer
from rich.console import Console

from investment_engine.clock import LiveClock, ReplayClock
from investment_engine.config import market_store_dir, operational_db_path
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import Timeframe
from investment_engine.market.data_health import SourceKey, evaluate_health
from investment_engine.market.instruments import Instrument
from investment_engine.market.replay import ReplayFeed
from investment_engine.market.symbols import SymbolMapping
from investment_engine.storage.database import SqliteDatabase
from investment_engine.storage.sqlite import (
    SqliteInstrumentRepository,
    SqliteSymbolResolver,
    apply_schema,
    open_operational_db,
)

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False,
                  help="Research-data tools. Daily support only; hourly verification is blocked.")
console = Console(highlight=False, markup=False, soft_wrap=True)
HOURLY_REASON = "independent hourly price and volume verification pending"


def _print(text: str) -> None:
    # Provider strings and records are data, never Rich markup.
    console.print(text)


def _load_store():
    from investment_engine.market.store.reader import MarketDataReader
    from investment_engine.market.store.writer import MarketDataWriter
    return MarketDataReader, MarketDataWriter


def _import_actions(instrument_id, **kwargs):
    from investment_engine.market.importers import yfinance_actions
    return yfinance_actions.import_actions(
        instrument_id, fetch_split_history=yfinance_actions.fetch_full_splits,
        fetch_dividends=yfinance_actions.fetch_full_dividends, **kwargs)


def _import_bars(instrument_id, timeframe, start, end, **kwargs):
    from investment_engine.market.importers import yfinance_bars
    return yfinance_bars.import_bars(
        instrument_id, timeframe, start, end, fetch_bars=yfinance_bars.fetch_daily_bars,
        fetch_split_history=yfinance_bars.fetch_full_splits, **kwargs)


def _fail(exc: Exception) -> None:
    if isinstance(exc, ModuleNotFoundError) and exc.name in {"pyarrow", "duckdb"}:
        _print('Storage engines unavailable. Install: pip install -e ".[engine]"')
    elif isinstance(exc, (ValueError, KeyError, FileNotFoundError, sqlite3.Error)):
        _print(f"Cannot complete command: {exc}")
    else:
        # Vendor exceptions can include URLs or credentials; do not echo their text.
        _print(f"Cannot complete command ({type(exc).__name__}); no successful result established.")
    raise typer.Exit(1)


def _read_db():
    path = operational_db_path().resolve()
    if not path.is_file():
        raise FileNotFoundError("Reference database unavailable; run 'python -m investment_engine init' first")
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, isolation_level=None)


def _timestamp(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone (for example 2024-06-03T00:00:00Z)")
    return value.astimezone(UTC)


def _latency(text: str) -> timedelta:
    try:
        seconds = Decimal(text)
        if not seconds.is_finite() or seconds < 0:
            raise ValueError("latency must be finite and nonnegative")
        micros = seconds * 1_000_000
        if micros != micros.to_integral_value():
            raise ValueError("latency must have at most microsecond precision")
        return timedelta(microseconds=int(micros))
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError("invalid latency") from exc


@app.command("init")
def initialize() -> None:
    """Initialize the schema and cited NVDA reference identity; no network."""
    conn = None
    try:
        seed = json.loads(files("investment_engine").joinpath("reference/us_equities_seed.json").read_text("utf-8"))
        fields = seed["instrument"]
        instrument = Instrument(**{**fields, "active_from": date.fromisoformat(fields["active_from"])})
        mapping_fields = seed["mapping"]
        mapping = SymbolMapping(**{**mapping_fields, "valid_from": date.fromisoformat(mapping_fields["valid_from"])})
        conn = open_operational_db(operational_db_path())
        version = apply_schema(conn)
        db = SqliteDatabase(conn)  # transitional until M3-03 moves the CLI to PostgreSQL
        instruments, resolver = SqliteInstrumentRepository(db), SqliteSymbolResolver(db)
        try:
            existing = instruments.get(instrument.instrument_id)
        except KeyError:
            instruments.add(instrument)
        else:
            # Never reset lifecycle history on an idempotent init.
            for name in ("asset_class", "currency", "exchange", "timezone", "active_from"):
                if getattr(existing, name) != getattr(instrument, name):
                    raise ValueError(f"stored reference identity conflicts with seed: {name}")
        rows = conn.execute(
            "SELECT instrument_id, provider, symbol, valid_from, valid_to FROM symbol_mappings "
            "WHERE instrument_id = ? AND provider = ?", (mapping.instrument_id, mapping.provider)).fetchall()
        exact = (mapping.instrument_id, mapping.provider, mapping.symbol, mapping.valid_from.isoformat(), None)
        if exact not in rows:
            # The repository refuses overlapping/conflicting mappings; never overwrite.
            resolver.add(mapping)
        _print(f"Reference schema={version}; {instrument.instrument_id} XNAS yfinance:NVDA initialized. No market data downloaded.")
    except Exception as exc:
        _fail(exc)
    finally:
        if conn is not None:
            conn.close()


def _times(value: datetime, timezone: ZoneInfo) -> str:
    return f"ET={value.astimezone(timezone).isoformat()} UTC={value.astimezone(UTC).isoformat()}"


def _basis_note(payload) -> None:
    if payload.availability_basis.value == "BACKFILL_ASSUMED":
        _print("BACKFILL: availability assumed at displayed available_from; original publication time unknown")


def _render_event(event, reader, timezone: ZoneInfo) -> None:
    p = event.payload
    _print(f"{event.kind} provider={p.source} revision={p.revision} arrival={event.received_at.isoformat()} "
           f"event_time={event.event_time.isoformat()} processed_at={event.processed_at.isoformat()}")
    _print(f"availability={p.availability_basis} available_from={p.available_from.isoformat()} "
           f"stored received_at={p.received_at.isoformat()} stored processed_at={p.processed_at.isoformat()} "
           f"source_version={p.source_version} import_id={p.import_id}")
    if event.kind == "CORPORATE_ACTION":
        amount = f"{p.amount.amount} {p.amount.currency}" if p.amount is not None else "UNAVAILABLE: not a dividend"
        basis = p.amount_basis if p.amount_basis is not None else "UNAVAILABLE: not a dividend"
        _print(f"{p.action_type} ex_date={p.ex_date} amount={amount} amount_basis={basis} "
               f"ratio={p.ratio if p.ratio is not None else 'UNAVAILABLE: not a split'}")
    else:
        _print(f"start {_times(p.start_time, timezone)}; end {_times(p.end_time, timezone)}")
        _print(f"O={p.open} {p.currency} H={p.high} {p.currency} L={p.low} {p.currency} C={p.close} {p.currency}; "
               f"volume={p.volume} shares; state={p.state}; price_basis={p.price_basis}; volume_basis={p.volume_basis}")
        if event.kind == "CANDLE_REVISED":
            history = reader.candle_revision_history(p.source, p.instrument_id, p.timeframe,
                                                     p.start_time, p.start_time + timedelta(microseconds=1))
            previous = next((c for c in history if c.revision == p.revision - 1), None)
            if previous is None:
                _print("previous stored revision UNAVAILABLE: predecessor not in store")
            else:
                _print(f"Comparison with previous stored revision (not preloaded replay state): previous revision={previous.revision}")
                _print(f"previous price_basis={previous.price_basis}; previous volume_basis={previous.volume_basis}")
                for name in ("open", "high", "low", "close", "volume"):
                    unit = "shares" if name == "volume" else p.currency
                    prior_unit = "shares" if name == "volume" else previous.currency
                    if prior_unit == unit:
                        _print(f"{name}: {getattr(previous, name)} -> {getattr(p, name)} {unit}")
                    else:
                        _print(f"{name}: {getattr(previous, name)} {prior_unit} -> {getattr(p, name)} {unit}; units differ")
    _basis_note(p)


@app.command()
def report(instrument: str = "EQ_US_NVDA", provider: str = "yfinance", timeframe: str = "D1",
           from_time: str = typer.Option(..., "--from"), to_time: str = typer.Option(..., "--to"),
           as_of: str | None = typer.Option(None, "--as-of"), latency: str = "0") -> None:
    """Replay one provider's stored daily observations, corrections and actions; offline."""
    conn = None
    try:
        if Timeframe(timeframe) is Timeframe.H1:
            raise ValueError(f"H1 BLOCKED: {HOURLY_REASON}")
        start, end = _timestamp(from_time), _timestamp(to_time)
        cutoff = _timestamp(as_of) if as_of is not None else LiveClock().now()
        delay = _latency(latency)
        if not start < end <= cutoff:
            raise ValueError("require --from < --to <= --as-of; replay end is excluded")
        if not provider.strip():
            raise ValueError("provider must not be empty")
        reader_type, _ = _load_store()
        conn = _read_db()
        db = SqliteDatabase(conn)  # transitional until M3-03 moves the CLI to PostgreSQL
        instruments, resolver = SqliteInstrumentRepository(db), SqliteSymbolResolver(db)
        identity = instruments.get(instrument)
        timezone = ZoneInfo(identity.timezone)
        reader = reader_type(market_store_dir())
        _print(f"{identity.instrument_id} exchange={identity.exchange} provider={provider}")
        _print(f"PAPER-ONLY PLATFORM | RESEARCH DATA ({provider}) | REPLAY | PARTIAL M1: daily support only")
        _print("TRADING STATUS CANNOT BE VERIFIED: no execution gate or kill-switch observation exists in M1. Autonomy UNCONFIGURED.")
        _print(f"Delivery window [{start.isoformat()}, {end.isoformat()}); latency={delay}; as-of {_times(cutoff, timezone)}")
        _print("RAW_AS_REPORTED: provider values; RAW_RECONSTRUCTED: reconstructed from split-adjusted research data.")
        _print("Precision: recorded quantum 0.0001 USD does not create original source precision; see docs/data-provenance/yfinance.md.")
        feed = ReplayFeed(reader, ReplayClock(start), sources=[provider], instrument_ids=[instrument],
                          timeframes=[Timeframe.D1], start=start, end=end, latency=delay)
        bars = 0
        for event in feed:
            _render_event(event, reader, timezone)
            if event.kind == "BAR_CLOSED":
                bars += 1
        if not bars:
            _print("no bars delivered in this window (BAR_CLOSED); any corrections/actions are listed separately")
        _print(f"DataHealth: stored visible_at({cutoff.isoformat()}); separate from latency-delayed replay state")
        health = evaluate_health(instrument, [SourceKey(provider, Timeframe.D1)], clock=ReplayClock(cutoff),
                                 reader=reader, instruments=instruments, resolver=resolver,
                                 calendar=load_us_equities_calendar())
        if not health.applicability.applicable:
            _print(f"Health checks not applicable: {health.applicability.reason}")
        for h in health.sources:
            latest = _times(h.latest_bar_end, timezone) if h.latest_bar_end else "UNAVAILABLE"
            age = str(h.age) if h.age is not None else "UNAVAILABLE"
            behind = str(h.bars_behind) if h.bars_behind is not None else "UNAVAILABLE"
            holes = ", ".join(_times(t, timezone) for t in h.missing_in_window) or "none"
            _print(f"{h.source.provider} {h.source.timeframe} {h.status} latest_bar_end={latest} age={age} "
                   f"bars_behind={behind} missing_bars={holes} detail={h.detail or 'none'}")
        _print(f"required_sources_ok={health.required_sources_ok} (chosen provider's D1 only)")
        _print(f"H1 UNAVAILABLE: {HOURLY_REASON}")
        _print("vendor-vs-hourly comparison UNAVAILABLE: hourly verification pending")
    except Exception as exc:
        _fail(exc)
    finally:
        if conn is not None:
            conn.close()


def _write_result(label, result) -> None:
    _print(f"{label}: new_records={result.new_records} new_revisions={result.new_revisions} "
           f"unchanged={result.unchanged} import_id={result.import_id}")


@app.command("import-yfinance")
def import_yfinance(instrument: str = "EQ_US_NVDA", daily_from: str = "2019-01-01",
                    daily_to: str | None = None, daily_only: bool = False) -> None:
    """Explicit online research import. No broker keys. Full hourly support remains blocked."""
    conn = None
    try:
        clock = LiveClock()
        start = date.fromisoformat(daily_from)
        end = date.fromisoformat(daily_to) if daily_to else clock.now().astimezone(ZoneInfo("America/New_York")).date() + timedelta(days=1)
        if start < date(2019, 1, 1) or end <= start:
            raise ValueError("daily range requires 2019-01-01 <= start < end (excluded)")
        reader_type, writer_type = _load_store()
        conn = _read_db()
        # Importers read reference data only; market writes go through their writer.
        db = SqliteDatabase(conn)  # transitional until M3-03 moves the CLI to PostgreSQL
        instruments, resolver = SqliteInstrumentRepository(db), SqliteSymbolResolver(db)
        instruments.get(instrument)
        calendar = load_us_equities_calendar()
        calendar.sessions_between(start, end - timedelta(days=1))
        reader, writer = reader_type(market_store_dir()), writer_type(market_store_dir())
        _print("PAPER-ONLY PLATFORM | RESEARCH DATA (yfinance) | PARTIAL M1")
        actions = _import_actions(instrument, clock=clock, resolver=resolver, instruments=instruments, writer=writer)
        _write_result("actions", actions.write)
        _print(f"skipped_before_verified_from={actions.skipped_before_verified_from}")
        bars = _import_bars(instrument, Timeframe.D1, start, end, clock=clock, resolver=resolver,
                            instruments=instruments, calendar=calendar, reader=reader, writer=writer)
        _write_result("D1", bars.write)
        _print(f"dropped_forming={bars.dropped_forming}; covered_bounds={bars.covered}; "
               f"max_split_factor_applied={bars.max_split_factor_applied}; gaps checked separately by DataHealth")
        for timestamp, reason in bars.rejected:
            _print(f"rejected {timestamp.isoformat()}: {reason}")
        _print(f"H1 BLOCKED: {HOURLY_REASON}; no hourly request was made. M1 is not complete.")
        if not daily_only or bars.rejected:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc)
    finally:
        if conn is not None:
            conn.close()
