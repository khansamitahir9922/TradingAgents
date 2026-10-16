"""Offline acceptance checks for the daily part of M1-17; H1 remains blocked.

The Operational Database is PostgreSQL from M3 (docs/tasks/M3-03.md), so these tests use a fresh test
database each; the market-data store stays under the test's data directory.
"""

import hashlib
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from investment_engine.clock import ReplayClock
from investment_engine.config import ENV_PG_DSN, operational_db_dsn
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType, AmountBasis, ex_date_start
from investment_engine.market.store.writer import (
    ActionObservation,
    CandleObservation,
    MarketDataWriter,
    WriteResult,
)
from investment_engine.market.symbols import SymbolMapping
from investment_engine.money import Money
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import open_operational_pg
from investment_engine.storage.sqlite import SqliteSymbolResolver

CAL = load_us_equities_calendar()
NVDA = "EQ_US_NVDA"
FRIDAY = datetime(2024, 6, 7, 21, tzinfo=UTC)
SATURDAY = datetime(2024, 6, 8, tzinfo=UTC)
RUNNER = CliRunner()
pytestmark = pytest.mark.postgres


def operational():
    """A port onto the test's Operational Database (the CLI's own DSN)."""
    return PostgresDatabase(open_operational_pg(operational_db_dsn()))


@pytest.fixture
def app(tmp_path, monkeypatch, pg_database):
    from investment_engine import cli

    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(ENV_PG_DSN, pg_database)
    monkeypatch.setattr(cli, "LiveClock", lambda: ReplayClock(SATURDAY))
    result = RUNNER.invoke(cli.app, ["init"])
    assert result.exit_code == 0, result.output
    return cli, tmp_path


def candle(d, source="yfinance", close="100.0000", received=None):
    session = CAL.session(d)
    observed = received or session.close + timedelta(minutes=5)
    return CandleObservation(
        source=source, instrument_id=NVDA, timeframe=Timeframe.D1,
        start_time=session.open, end_time=session.close,
        open=Decimal("100"), high=Decimal("102"), low=Decimal("99"), close=Decimal(close),
        volume=Decimal("1000"), currency="USD", state=BarState.CLOSED,
        source_version="1.7.0", price_basis=PriceBasis.RAW_AS_REPORTED,
        volume_basis=VolumeBasis.RAW_AS_REPORTED, event_time=session.close,
        received_at=observed, processed_at=observed, backfill_available_from=session.close,
    )


def history(app, source="yfinance", missing=()):
    _, root = app
    writer = MarketDataWriter(root / "market")
    days = [s.date for s in CAL.sessions_between(date(2024, 5, 1), date(2024, 6, 7))]
    writer.write_candles([candle(d, source) for d in days if d not in missing], import_id=source + "-original")
    if source != "yfinance":
        db = operational()
        try:
            SqliteSymbolResolver(db).add(SymbolMapping(NVDA, source, "NVDA.TEST", date(1999, 1, 22), None))
        finally:
            db.connection.close()
    return writer


def report(app, *, end=SATURDAY, as_of=None, provider="yfinance", start="2024-06-03T00:00:00Z", extra=()):
    cli, _ = app
    return RUNNER.invoke(cli.app, ["report", "--instrument", NVDA, "--provider", provider,
                                  "--timeframe", "D1", "--from", start, "--to", end.isoformat(),
                                  "--as-of", (as_of or end).isoformat(), *extra])


@pytest.mark.unit
def test_init_is_idempotent_and_seed_dates_are_cited(app):
    cli, root = app
    assert RUNNER.invoke(cli.app, ["init"]).exit_code == 0
    db = operational()
    try:
        assert db.fetchone("SELECT COUNT(*) FROM instruments")[0] == 1
        assert db.fetchone("SELECT COUNT(*) FROM symbol_mappings")[0] == 1
        assert db.fetchone("SELECT active_from FROM instruments")[0] == date(1999, 1, 22)
    finally:
        db.connection.close()
    import json
    from importlib.resources import files
    seed = json.loads(files("investment_engine").joinpath("reference/us_equities_seed.json").read_text())
    assert "investor.nvidia.com" in seed["sources"][0]["url"]


@pytest.mark.unit
def test_report_has_exact_values_sources_bases_and_times_and_is_read_only(app):
    history(app)
    _, root = app
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    before_db = database_rows()
    result = report(app)
    assert result.exit_code == 0, result.output
    for text in (NVDA, "XNAS", "provider=yfinance", "REPLAY", "PAPER-ONLY PLATFORM", "PARTIAL M1",
                 "100.0000 USD", "1000 shares", "RAW_AS_REPORTED", "BACKFILL_ASSUMED", "revision=1",
                 "2024-06-03T16:00:00-04:00", "2024-06-03T20:00:00+00:00",
                 "original publication time unknown", "recorded quantum", "TRADING STATUS CANNOT BE VERIFIED"):
        assert text in result.output
    assert "D1 OK" in result.output and "required_sources_ok=True" in result.output
    assert "RESEARCH DATA (yfinance)" in result.output
    assert "H1 UNAVAILABLE" in result.output and "comparison UNAVAILABLE" in result.output
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert database_rows() == before_db  # the Operational Database too (it no longer lives under root)


def database_rows():
    db = operational()
    try:
        return [db.fetchall(f"SELECT * FROM {t} ORDER BY 1") for t in ("instruments", "symbol_mappings")]
    finally:
        db.connection.close()


@pytest.mark.unit
def test_friday_correction_is_never_shown_before_its_arrival(app):
    writer = history(app)
    writer.write_candles([candle(date(2024, 6, 3), close="101.0000", received=FRIDAY)], import_id="correction")
    early = report(app, end=datetime(2024, 6, 7, tzinfo=UTC))
    late = report(app)
    assert early.exit_code == late.exit_code == 0
    assert "CANDLE_REVISED" not in early.output and "101.0000" not in early.output
    assert "CANDLE_REVISED" in late.output and "previous revision=1" in late.output
    assert "100.0000 -> 101.0000 USD" in late.output and FRIDAY.isoformat() in late.output


@pytest.mark.unit
def test_correction_only_window_identifies_previous_stored_revision(app):
    writer = history(app)
    writer.write_candles([candle(date(2024, 6, 3), close="101.0000", received=FRIDAY)], import_id="correction")
    result = report(app, start="2024-06-07T20:30:00Z")
    assert result.exit_code == 0
    assert "previous stored revision" in result.output and "100.0000 -> 101.0000 USD" in result.output


@pytest.mark.unit
def test_correction_never_labels_a_previous_value_with_the_new_currency(app):
    writer = history(app)
    correction = replace(candle(date(2024, 6, 3), close="101.0000", received=FRIDAY), currency="EUR")
    writer.write_candles([correction], import_id="changed-unit")
    result = report(app, start="2024-06-07T20:30:00Z")
    assert result.exit_code == 0, result.output
    assert "100.0000 USD -> 101.0000 EUR" in result.output
    assert "previous price_basis=" in result.output and "previous volume_basis=" in result.output


@pytest.mark.unit
def test_latency_window_does_not_show_a_correction_delivered_after_the_end(app):
    writer = history(app)
    writer.write_candles([candle(date(2024, 6, 3), close="101.0000", received=FRIDAY)], import_id="correction")
    result = report(app, end=FRIDAY + timedelta(seconds=3), extra=("--latency", "5"))
    assert result.exit_code == 0 and "CANDLE_REVISED" not in result.output
    assert "stored visible_at" in result.output  # health is a separate labelled cutoff view


@pytest.mark.unit
def test_missing_session_is_degraded_and_identified(app):
    history(app, missing=(date(2024, 6, 5),))
    result = report(app)
    assert result.exit_code == 0 and "D1 DEGRADED" in result.output
    assert "2024-06-05" in result.output and "required_sources_ok=False" in result.output


@pytest.mark.unit
def test_empty_report_is_missing_not_zero(app):
    result = report(app)
    assert result.exit_code == 0, result.output
    assert "no bars delivered in this window" in result.output and "D1 MISSING" in result.output
    assert "latest_bar_end=UNAVAILABLE" in result.output and "age=UNAVAILABLE" in result.output
    assert "0.0000 USD" not in result.output


@pytest.mark.unit
def test_inactive_date_is_not_applicable_without_invented_health_status(app):
    result = report(app, start="1998-12-01T00:00:00Z", end=datetime(1998, 12, 2, tzinfo=UTC))
    assert result.exit_code == 0, result.output
    assert "Health checks not applicable" in result.output and "1999-01-22" in result.output
    assert "D1 MISSING" not in result.output and "D1 OK" not in result.output


@pytest.mark.unit
def test_only_the_named_providers_bars_and_corrections_are_shown(app):
    yf = history(app)
    tv = history(app, "testvendor")
    yf.write_candles([candle(date(2024, 6, 3), close="101.0000", received=FRIDAY)], import_id="yf-fix")
    tv.write_candles([candle(date(2024, 6, 3), "testvendor", close="100.5000", received=FRIDAY)], import_id="tv-fix")
    result = report(app, provider="testvendor")
    assert result.exit_code == 0 and "provider=testvendor" in result.output
    assert "100.0000 -> 100.5000 USD" in result.output and "101.0000" not in result.output
    assert "testvendor D1 OK" in result.output and "yfinance D1" not in result.output
    assert "RESEARCH DATA (testvendor)" in result.output


@pytest.mark.unit
def test_corporate_action_output_has_basis_time_and_revision(app):
    writer = history(app)
    ex = date(2024, 6, 6)
    seen = ex_date_start(ex, "America/New_York") + timedelta(hours=1)
    writer.write_corporate_actions([ActionObservation(
        source="yfinance", instrument_id=NVDA, currency="USD", exchange_timezone="America/New_York",
        action_type=ActionType.DIVIDEND, ex_date=ex, ratio=None, amount=Money(Decimal("0.0100"), "USD"),
        amount_basis=AmountBasis.AS_REPORTED, new_symbol=None, source_version="1.7.0",
        received_at=seen, processed_at=seen, backfill_available_from=ex_date_start(ex, "America/New_York"),
    )], import_id="dividend")
    result = report(app)
    assert result.exit_code == 0
    for text in ("CORPORATE_ACTION", "DIVIDEND", "0.0100 USD", "AS_REPORTED", "ex_date=2024-06-06", "BACKFILL_ASSUMED"):
        assert text in result.output


@pytest.mark.unit
@pytest.mark.parametrize("extra", [
    ("--from", "2024-06-03"), ("--to", "2024-06-03T00:00:00Z"),
    ("--as-of", "2024-06-07T00:00:00Z"), ("--latency", "-1"),
    ("--latency", "NaN"), ("--latency", "Infinity"),
], ids=["naive-time", "empty-window", "future-window", "negative-latency", "nan", "infinite"])
def test_bad_arguments_are_refused(app, extra):
    result = report(app, extra=extra)
    assert result.exit_code != 0


@pytest.mark.unit
def test_hourly_report_is_explicitly_blocked(app):
    cli, _ = app
    result = RUNNER.invoke(cli.app, ["report", "--instrument", NVDA, "--timeframe", "H1",
                                   "--from", "2024-06-03T00:00:00Z", "--to", SATURDAY.isoformat()])
    assert result.exit_code != 0 and "H1" in result.output and "BLOCKED" in result.output


@pytest.mark.unit
def test_default_cutoff_comes_from_the_injected_entry_point_clock(app):
    cli, _ = app
    result = RUNNER.invoke(cli.app, ["report", "--from", "2024-06-03T00:00:00Z", "--to", SATURDAY.isoformat()])
    assert result.exit_code == 0 and SATURDAY.isoformat() in result.output


@pytest.mark.unit
def test_missing_optional_engines_give_install_instructions(app, monkeypatch):
    cli, _ = app
    def missing():
        raise ModuleNotFoundError("no pyarrow", name="pyarrow")
    monkeypatch.setattr(cli, "_load_store", missing)
    result = report(app)
    assert result.exit_code != 0 and ".[engine]" in result.output


@pytest.mark.unit
@pytest.mark.parametrize("daily_only", [True, False], ids=["explicit-daily", "default-full"])
def test_import_wiring_reports_partial_work_and_never_calls_hourly(app, monkeypatch, daily_only):
    from investment_engine.market.importers.yfinance_actions import ActionImportReport
    from investment_engine.market.importers.yfinance_bars import BarImportReport
    cli, _ = app
    calls = []
    def actions(instrument_id, **kwargs):
        calls.append("actions")
        return ActionImportReport(WriteResult(2, 0, 0, "actions-test"), 29)
    def bars(instrument_id, timeframe, start, end, **kwargs):
        assert timeframe is Timeframe.D1
        calls.append("daily")
        kwargs["writer"].write_candles([candle(date(2024, 6, 3))], import_id="fixture-import")
        return BarImportReport(WriteResult(1, 0, 0, "daily-test"), 0, [],
                               (CAL.session(date(2024, 6, 3)).open, CAL.session(date(2024, 6, 3)).close), (), Decimal(1))
    monkeypatch.setattr(cli, "_import_actions", actions)
    monkeypatch.setattr(cli, "_import_bars", bars)
    args = ["import-yfinance", "--instrument", NVDA, "--daily-from", "2024-06-03", "--daily-to", "2024-06-04"]
    if daily_only:
        args += ["--daily-only"]
    result = RUNNER.invoke(cli.app, args)
    assert result.exit_code == (0 if daily_only else 1), result.output
    assert calls == ["actions", "daily"]
    assert "skipped_before_verified_from=29" in result.output and "new_records=1" in result.output
    assert "H1 BLOCKED" in result.output and "PARTIAL M1" in result.output
    assert report(app).exit_code == 0  # init -> fixture import -> report, under the network guard


@pytest.mark.unit
def test_module_help_registers_all_commands_without_network():
    result = subprocess.run([sys.executable, "-m", "investment_engine", "--help"],
                            capture_output=True, text=True, encoding="utf-8", cwd=Path(__file__).parents[2])
    assert result.returncode == 0, result.stderr
    for command in ("init", "report", "import-yfinance"):
        assert command in result.stdout


@pytest.mark.unit
def test_recorded_import_to_report_uses_real_importers_offline(app, monkeypatch):
    import pandas as pd

    from investment_engine.market.importers import yfinance_actions, yfinance_bars
    from investment_engine.market.importers.yahoo_semantics import load_recording

    cli, _ = app
    fixtures = Path(__file__).parent / "fixtures" / "yfinance"
    now = datetime(2026, 10, 12, 9, tzinfo=UTC)
    monkeypatch.setattr(cli, "LiveClock", lambda: ReplayClock(now))
    for module in (yfinance_actions, yfinance_bars):
        monkeypatch.setattr(module, "version", lambda name: "1.7.0")

    def series(filename):
        recording = load_recording(fixtures / filename)
        return pd.Series([row[1] for row in recording.rows],
                         index=pd.to_datetime([row[0] for row in recording.rows], utc=True))

    splits = series("nvda_splits_before.json")
    dividends = series("nvda_dividends.json")
    monkeypatch.setattr(yfinance_actions, "fetch_full_splits", lambda symbol: splits.copy())
    monkeypatch.setattr(yfinance_actions, "fetch_full_dividends", lambda symbol: dividends.copy())
    monkeypatch.setattr(yfinance_bars, "fetch_full_splits", lambda symbol: splits.copy())
    recording = load_recording(fixtures / "nvda_1d_2019_2026.json")
    data = pd.DataFrame([r[1:] for r in recording.rows], columns=recording.columns,
                        index=pd.to_datetime([r[0] for r in recording.rows], utc=True).tz_convert("America/New_York"))

    def fetch(symbol, **kwargs):
        assert kwargs["interval"] == "1d" and kwargs["actions"] is False
        dates = data.index.tz_convert("America/New_York").date
        return data[(dates >= kwargs["start"]) & (dates < kwargs["end"])].copy()

    monkeypatch.setattr(yfinance_bars, "fetch_daily_bars", fetch)
    result = RUNNER.invoke(cli.app, ["import-yfinance", "--daily-only", "--daily-from", "2021-07-01",
                                   "--daily-to", "2021-07-20"])
    assert result.exit_code == 0, result.output
    assert "new_records=12" in result.output and "skipped_before_verified_from=29" in result.output
    output = report(app, start="2021-07-01T00:00:00Z", end=datetime(2021, 7, 20, tzinfo=UTC))
    assert output.exit_code == 0, output.output
    assert "751.1900 USD" in output.output and "RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED" in output.output
    assert "2021-07-19T16:00:00-04:00" in output.output


@pytest.mark.unit
def test_report_without_init_creates_no_database(tmp_path, monkeypatch, pg_database):
    from investment_engine import cli

    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path / "unused"))
    monkeypatch.setenv(ENV_PG_DSN, pg_database)
    result = RUNNER.invoke(cli.app, ["report", "--from", "2024-06-03T00:00:00Z", "--to", SATURDAY.isoformat(),
                                   "--as-of", SATURDAY.isoformat()])
    assert result.exit_code != 0 and "init" in result.output
    assert not (tmp_path / "unused").exists()
    db = operational()
    try:  # nothing was created in the Operational Database either
        assert db.fetchall("SELECT tablename FROM pg_tables WHERE schemaname = 'public'") == []
    finally:
        db.connection.close()


@pytest.mark.unit
def test_init_never_replaces_a_conflicting_reference_identity(app):
    cli, root = app
    db = operational()
    db.execute("UPDATE instruments SET currency = 'EUR' WHERE instrument_id = :id", {"id": NVDA})
    db.connection.close()
    result = RUNNER.invoke(cli.app, ["init"])
    assert result.exit_code != 0 and "conflicts" in result.output
    db = operational()
    assert db.fetchone("SELECT currency FROM instruments WHERE instrument_id = :id", {"id": NVDA})[0] == "EUR"
    db.connection.close()
