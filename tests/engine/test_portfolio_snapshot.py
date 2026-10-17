"""PortfolioSnapshot: declared starting state, point-in-time valuation and the drawdown baseline (docs/tasks/M3-07.md)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import MarketDataWriter
from investment_engine.policy.accounts import AccountKind, AccountRegistry, NotAuthorized, Role
from investment_engine.portfolio.reference import StoreKnowledge, Unavailable
from investment_engine.portfolio.snapshot import (
    PortfolioSnapshotStore,
    SnapshotSource,
    StartingState,
    build_snapshot,
)
from investment_engine.quant.adjusted import ActionCoverage
from investment_engine.risk.limits import Halt
from investment_engine.storage.database import AppendOnlyViolation, PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg
from tests.engine.test_raw_reference import observation

CAL = load_us_equities_calendar()
NVDA = "EQ_US_NVDA"
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
START = CAL.session(date(2024, 6, 3)).close + timedelta(minutes=5)
OWNER = Actor(ActorKind.OPERATOR, "owner", "ADMIN", "LOQ")
TRADER = Actor(ActorKind.OPERATOR, "trader", "TRADER", None)
DAYS = [s.date for s in CAL.sessions_between(date(2024, 6, 3), date(2024, 6, 14))]


def state(positions=(), cash="100000", effective_at=START):
    return StartingState("R1", effective_at, NOW, Decimal(cash), "USD", positions, "owner", "D14 default")


def coverage(first=date(2024, 6, 3), last=date(2024, 6, 30), established=True):
    return ActionCoverage("yfinance", NVDA, (ActionType.SPLIT, ActionType.DIVIDEND), first, last, NOW, established,
                          ("verification:test",), "test coverage")


@pytest.fixture
def market(tmp_path):
    writer = MarketDataWriter(tmp_path / "market")
    closes = {d: Decimal("120") + i for i, d in enumerate(DAYS)}
    writer.write_candles([observation(d, close=f"{closes[d]:.4f}") for d in DAYS], import_id="bars")
    return writer, StoreKnowledge(MarketDataReader(tmp_path / "market"), CAL), closes


def snapshot(knowledge, *, at, starting=None, history=(), last_clear=None, cover=None):
    return build_snapshot("R1", at=at, starting=starting or state(), knowledge=knowledge, calendar=CAL,
                          coverage=cover or coverage(), last_clear=last_clear, history=history, source="yfinance")


def at_close(d):
    return CAL.session(d).close + timedelta(minutes=5)


@pytest.mark.unit
def test_the_default_start_is_100000_cash_and_no_positions(market):
    _, knowledge, _ = market
    s = snapshot(knowledge, at=at_close(DAYS[1]))
    assert s.source is SnapshotSource.DECLARED_STARTING_STATE and s.cash == s.equity == Decimal("100000")
    assert s.positions == () and s.held(NVDA) == Decimal(0) and s.peak_equity == Decimal("100000")
    assert s.snapshot_id.startswith("psn-")


@pytest.mark.unit
def test_a_declared_position_is_valued_at_the_expected_sessions_raw_close(market):
    _, knowledge, closes = market
    starting = state(positions=((NVDA, Decimal("10")),), cash="98800")
    for d in DAYS[:4]:
        s = snapshot(knowledge, at=at_close(d), starting=starting)
        (p,) = s.positions
        assert p.price == closes[d] and p.value == closes[d] * 10 and s.equity == Decimal("98800") + closes[d] * 10
    midday = CAL.session(DAYS[2]).open + timedelta(hours=2)  # the latest completed session is the previous one
    assert snapshot(knowledge, at=midday, starting=starting).positions[0].price == closes[DAYS[1]]
    at_the_close = CAL.session(DAYS[2]).close  # received a minute after the close: not yet known
    result = snapshot(knowledge, at=at_the_close, starting=starting)
    assert isinstance(result, Unavailable) and "not known" in result.reason


@pytest.mark.unit
def test_a_missing_expected_session_is_unavailable_even_when_an_older_bar_exists(tmp_path):
    writer = MarketDataWriter(tmp_path / "market")
    writer.write_candles([observation(d) for d in DAYS if d != DAYS[3]], import_id="gap")
    knowledge = StoreKnowledge(MarketDataReader(tmp_path / "market"), CAL)
    result = snapshot(knowledge, at=at_close(DAYS[3]), starting=state(positions=((NVDA, Decimal("1")),)))
    assert isinstance(result, Unavailable) and str(DAYS[3]) in result.reason


@pytest.mark.unit
def test_actions_since_the_start_or_missing_coverage_make_a_held_snapshot_unavailable(market, tmp_path):
    writer, knowledge, _ = market
    held = state(positions=((NVDA, Decimal("1")),))
    no_cover = snapshot(knowledge, at=at_close(DAYS[3]), starting=held, cover=coverage(established=False))
    assert isinstance(no_cover, Unavailable) and "coverage" in no_cover.reason
    short = snapshot(knowledge, at=at_close(DAYS[3]), starting=held, cover=coverage(last=DAYS[1]))
    assert isinstance(short, Unavailable) and "coverage" in short.reason
    from investment_engine.market.corporate_actions import AmountBasis
    from investment_engine.market.store.writer import ActionObservation
    from investment_engine.money import Money

    arrived = at_close(DAYS[2])
    writer.write_corporate_actions([ActionObservation(
        source="yfinance", instrument_id=NVDA, currency="USD", exchange_timezone="America/New_York",
        action_type=ActionType.DIVIDEND, ex_date=DAYS[2], ratio=None, amount=Money(Decimal("0.01"), "USD"),
        amount_basis=AmountBasis.AS_REPORTED, new_symbol=None, source_version="1.7.0", received_at=arrived,
        processed_at=arrived, backfill_available_from=None)], import_id="dividend")
    after = snapshot(knowledge, at=at_close(DAYS[3]), starting=held)
    assert isinstance(after, Unavailable) and "ledger needed (M5)" in after.reason
    flat = snapshot(knowledge, at=at_close(DAYS[3]), cover=coverage(established=False))  # nothing held
    assert not isinstance(flat, Unavailable)


@pytest.mark.unit
def test_peak_equity_and_the_drawdown_baseline(tmp_path):
    closes = dict(zip(DAYS[:7], ("120", "121", "122", "123", "124", "123", "122"), strict=True))  # up, then down
    writer = MarketDataWriter(tmp_path / "rise-fall")
    writer.write_candles([observation(d, close=f"{c}.0000") for d, c in closes.items()], import_id="bars")
    knowledge = StoreKnowledge(MarketDataReader(tmp_path / "rise-fall"), CAL)
    starting = state(positions=((NVDA, Decimal("100")),), cash="0")
    history = []
    for d in DAYS[:5]:
        history.append(snapshot(knowledge, at=at_close(d), starting=starting, history=history))
    assert [s.peak_equity for s in history] == [Decimal(closes[d]) * 100 for d in DAYS[:5]]  # rising: peak follows
    later = snapshot(knowledge, at=at_close(DAYS[6]), starting=starting, history=history)
    assert later.peak_equity == Decimal("12400") and later.equity == Decimal("12200")  # hand-calculated drawdown
    assert (later.peak_equity - later.equity) / later.peak_equity == Decimal("200") / Decimal("12400")
    # Cleared on DAYS[5] at its equity, 12,300: the high-water mark restarts there, with that value as a floor
    # even though no snapshot was taken at the clear (D3; Codex M3 review B4).
    cleared = Halt("R1", False, at_close(DAYS[5]), "owner", "reviewed", "risk-1", Decimal("12300"))
    reset = snapshot(knowledge, at=at_close(DAYS[6]), starting=starting, history=history, last_clear=cleared)
    assert reset.baseline_at == cleared.at and reset.peak_equity == Decimal("12300")  # not 12,400, not 12,200
    floor = replace(cleared, baseline_equity=Decimal("13000"))
    assert snapshot(knowledge, at=at_close(DAYS[6]), starting=starting, history=history,
                    last_clear=floor).peak_equity == Decimal("13000")
    with pytest.raises(ValueError, match="this account's clear, not a halt"):
        snapshot(knowledge, at=at_close(DAYS[6]), starting=starting, history=history,
                 last_clear=Halt("R1", True, at_close(DAYS[5]), "core-engine", "drawdown", "risk-1", None))


@pytest.mark.unit
def test_a_clear_always_records_its_equity():
    with pytest.raises(ValueError, match="equity at the clear"):
        Halt("R1", False, at_close(DAYS[5]), "owner", "reviewed", "risk-1", None)
    with pytest.raises(ValueError, match="equity at the clear"):
        Halt("R1", False, at_close(DAYS[5]), "owner", "reviewed", "risk-1", Decimal("NaN"))
    with pytest.raises(ValueError, match="no baseline"):
        Halt("R1", True, at_close(DAYS[5]), "core-engine", "drawdown", "risk-1", Decimal("1"))


@pytest.mark.unit
def test_a_loss_after_a_clear_without_a_snapshot_is_measured_from_the_clearing_equity(tmp_path):
    """Codex's counterexample: 100,000, cleared at 85,000, then 60,000 at the first snapshot after the clear."""
    root = tmp_path / "drawdown"
    MarketDataWriter(root).write_candles([observation(d, close=f"{c}.0000")
                                          for d, c in zip(DAYS[:3], ("100", "85", "60"), strict=True)],
                                         import_id="fall")
    knowledge = StoreKnowledge(MarketDataReader(root), CAL)
    start = state(cash="0", positions=((NVDA, Decimal("1000")),))
    cleared = Halt("R1", False, at_close(DAYS[1]), "owner", "clear", "risk-1", Decimal("85000"))
    after = snapshot(knowledge, at=at_close(DAYS[2]), starting=start, last_clear=cleared)
    assert (after.equity, after.peak_equity) == (Decimal("60000"), Decimal("85000"))  # a 29.4% drawdown, not 0


@pytest.mark.unit
def test_the_same_inputs_give_the_same_id(market):
    _, knowledge, _ = market
    a = snapshot(knowledge, at=at_close(DAYS[2]))
    assert snapshot(knowledge, at=at_close(DAYS[2])) == a
    assert snapshot(knowledge, at=at_close(DAYS[3])).snapshot_id != a.snapshot_id
    assert state().state_id == replace(state(), recorded_at=NOW + timedelta(days=1), declared_by="x").state_id


@pytest.mark.unit
def test_starting_states_are_validated():
    with pytest.raises(ValueError, match="whole"):
        state(positions=((NVDA, Decimal("1.5")),))
    with pytest.raises(TypeError):
        StartingState("R1", START, NOW, 100000.0, "USD", (), "owner", "x")  # a float is never money
    with pytest.raises(ValueError):
        StartingState("R1", START, NOW, Decimal("-1"), "USD", (), "owner", "x")


# ---------------------------------------------------------------- the store (PostgreSQL)


@pytest.fixture
def stores(pg_database):
    conn = open_operational_pg(pg_database)
    db = PostgresDatabase(conn)
    apply_pg_schema(conn)
    clock, audit = ReplayClock(NOW), AuditStore(db)
    accounts = AccountRegistry(db, audit, clock)
    accounts.bootstrap_admin("owner", os_user="LOQ")
    accounts.add_operator("trader", Role.TRADER, by=OWNER, reason="t")
    accounts.create_account("R1", AccountKind.RESEARCH, "USD", by=OWNER, reason="demo", effective_at=START)
    accounts.create_account("P1", AccountKind.PAPER, "USD", by=OWNER, reason="paper")
    yield PortfolioSnapshotStore(db, audit, accounts, clock), db, audit
    conn.close()


@pytest.mark.postgres
@pytest.mark.unit
def test_declaring_a_start_is_admin_only_audited_and_once(stores):
    store, db, audit = stores
    with pytest.raises(NotAuthorized):
        store.declare_start("R1", by=TRADER, reason="no", effective_at=START)
    declared = store.declare_start("R1", by=OWNER, reason="D14 default", effective_at=START)
    assert declared.cash == Decimal("100000") and declared.positions == () and declared.recorded_at == NOW
    assert store.starting_state("R1") == declared
    with pytest.raises(ValueError, match="once"):
        store.declare_start("R1", by=OWNER, reason="again", effective_at=START)
    with pytest.raises(ValueError, match="backdate"):
        store.declare_start("P1", by=OWNER, reason="no", effective_at=START)
    assert [e.action for e in audit.for_target("account", "R1")].count("portfolio.declare_start") == 1


@pytest.mark.postgres
@pytest.mark.unit
def test_snapshots_are_append_only_and_queried_by_time(stores, market):
    store, db, _ = stores
    _, knowledge, _ = market
    taken = [snapshot(knowledge, at=at_close(d)) for d in DAYS[:3]]
    with db.transaction():
        for s in taken:
            store.append(s)
            store.append(s)  # identical: a no-op
    assert store.get(taken[1].snapshot_id) == taken[1]
    assert store.latest("R1", at_close(DAYS[1])) == taken[1]
    assert store.history("R1", since=at_close(DAYS[1]), at=at_close(DAYS[2])) == taken[1:]
    with pytest.raises(AppendOnlyViolation):
        db.execute("DELETE FROM portfolio_snapshots")


@pytest.mark.postgres
@pytest.mark.unit
def test_a_fresh_process_decodes_starting_state_events(stores, pg_database):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    store, db, audit = stores
    declared = store.declare_start("R1", by=OWNER, reason="D14 default", effective_at=START)
    probe = (
        "import json, os, sys\n"
        "from investment_engine.audit.events import AuditStore\n"
        "from investment_engine.storage.database import PostgresDatabase\n"
        "from investment_engine.storage.postgres import open_operational_pg\n"
        "events = AuditStore(PostgresDatabase(open_operational_pg(os.environ['IE_PROBE_DSN']))).for_target('account', 'R1')\n"
        "e = [x for x in events if x.action == 'portfolio.declare_start'][0]\n"
        "print(json.dumps([type(e.after).__name__, e.after.state_id, str(e.after.cash)]))\n"
    )
    root = Path(__file__).parents[2]
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120,
                         cwd=root, env={**os.environ, "IE_PROBE_DSN": pg_database, "PYTHONPATH": str(root)})
    assert out.returncode == 0, out.stderr.splitlines()[-1:]
    assert json.loads(out.stdout) == ["StartingState", declared.state_id, "100000"]


@pytest.mark.postgres
@pytest.mark.unit
def test_the_cli_declares_a_research_start(pg_database, monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from investment_engine import admin_cli, cli
    from investment_engine.config import ENV_PG_DSN

    monkeypatch.setenv(ENV_PG_DSN, pg_database)
    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(admin_cli, "LiveClock", lambda: ReplayClock(NOW))
    runner = CliRunner()
    for args in (["init"], ["operators", "bootstrap-admin", "owner"],
                 ["accounts", "create", "R1", "--kind", "RESEARCH", "--operator", "owner", "--reason", "demo",
                  "--effective-at", "2024-06-03T20:05:00Z"]):
        assert runner.invoke(cli.app, args).exit_code == 0
    declared = runner.invoke(cli.app, ["accounts", "declare-start", "R1", "--operator", "owner", "--reason", "D14",
                                       "--effective-at", "2024-06-03T20:05:00Z"])
    assert declared.exit_code == 0, declared.output
    assert "DECLARED starting state 100,000.00 USD cash, 0 positions" in declared.output
    again = runner.invoke(cli.app, ["accounts", "declare-start", "R1", "--operator", "owner", "--reason", "again",
                                    "--effective-at", "2024-06-03T20:05:00Z"])
    assert again.exit_code != 0 and "once" in again.output


@pytest.mark.postgres
@pytest.mark.unit
def test_the_peak_query_returns_the_highest_equity_snapshot_in_range(stores, tmp_path):
    store, db, _ = stores
    closes = dict(zip(DAYS[:5], ("120", "124", "121", "123", "122"), strict=True))
    writer = MarketDataWriter(tmp_path / "peaks")
    writer.write_candles([observation(d, close=f"{c}.0000") for d, c in closes.items()], import_id="bars")
    knowledge = StoreKnowledge(MarketDataReader(tmp_path / "peaks"), CAL)
    starting = state(positions=((NVDA, Decimal("100")),), cash="0")
    taken = [snapshot(knowledge, at=at_close(d), starting=starting) for d in DAYS[:5]]
    with db.transaction():
        for s in taken:
            store.append(s)
    assert store.peak("R1", since=START, at=at_close(DAYS[4])) == taken[1]  # 12,400 on the second day
    assert store.peak("R1", since=at_close(DAYS[2]), at=at_close(DAYS[4])) == taken[3]  # after it: 12,300
    assert store.peak("R1", since=at_close(DAYS[4]) + timedelta(days=1), at=at_close(DAYS[4])) is None
