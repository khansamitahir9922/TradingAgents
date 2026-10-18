"""The simulate and order-log commands (docs/tasks/M4-13.md rules 3, 5)."""

import json
from dataclasses import replace
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from investment_engine.clock import ReplayClock
from investment_engine.config import ENV_PG_DSN
from investment_engine.killswitch.flag import FLAG_FILE, FlagState, encode_flag
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import MarketDataWriter
from investment_engine.policy.accounts import AccountKind
from tests.engine.test_intent_pipeline import CAL, NOW, SESSIONS, Env, view_for
from tests.engine.test_raw_reference import observation

pytestmark = pytest.mark.postgres
RUNNER = CliRunner()


def backfilled_bars(root):
    """Like the real local store: history downloaded today (received at NOW), each bar available from its close.
    The run must know a bar at its replay delivery time, not at its download time."""
    obs = [replace(observation(d, close="120.0000", received=NOW, available=CAL.session(d).close),
                   volume=Decimal("1000000")) for d in SESSIONS]
    MarketDataWriter(root).write_candles(obs, import_id="bars")
    return MarketDataReader(root)


@pytest.fixture
def cli(pg_database, tmp_path, monkeypatch):
    from investment_engine import admin_cli, cli, intents_cli

    env = Env(pg_database, tmp_path / "market", reader=backfilled_bars(tmp_path / "market"))
    env.account("R2", level=2)
    env.account("P1", level=2, kind=AccountKind.PAPER)
    for n, (day, direction) in enumerate(((SESSIONS[60], "BULLISH"), (SESSIONS[62], "BEARISH"))):
        view_for(env.stores, env.reader, day, direction, tag=f"cli-{n}")  # a buy, then a sell of what was bought
    flag = tmp_path / "control" / FLAG_FILE
    flag.parent.mkdir(parents=True)
    flag.write_text(encode_flag(FlagState(True, 1, NOW, "owner", True, "go")), encoding="utf-8")
    monkeypatch.setenv(ENV_PG_DSN, pg_database)
    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path))
    for module in (admin_cli, intents_cli):
        monkeypatch.setattr(module, "LiveClock", lambda: ReplayClock(NOW))
    yield cli, tmp_path
    env.close()


def run(app, *args):
    result = RUNNER.invoke(app.app, [str(a) for a in args])
    assert all(ord(ch) < 128 for ch in result.output), "CLI output is plain ASCII"
    return result


@pytest.mark.unit
def test_simulate_then_the_order_log_with_its_label_header_units_and_json(cli):
    app, tmp = cli
    first, last = SESSIONS[59].isoformat(), SESSIONS[63].isoformat()
    refused = run(app, "intents", "simulate", "--account", "P1", "--from", first, "--to", last)
    assert refused.exit_code == 1 and "RESEARCH" in refused.output
    done = run(app, "intents", "simulate", "--account", "R2", "--from", first, "--to", last)
    assert done.exit_code == 0, done.output
    assert "SIMULATED | RESEARCH | NOT PROMOTED | PROVISIONAL POSITIONS" in done.output and "2 orders" in done.output
    again = run(app, "intents", "simulate", "--account", "R2", "--from", first, "--to", last)
    assert again.exit_code == 1 and "already has orders" in again.output
    path = tmp / "log.json"
    log = run(app, "intents", "order-log", "--account", "R2", "--json", str(path))
    assert log.exit_code == 0, log.output
    for needle in ("provider (source): yfinance", "timezone: UTC", "shares", "USD", "kill switch now: enabled",
                   "fill model: daily-fill-v1", "FINAL FILLED"):
        assert needle in log.output, needle
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["label"].startswith("SIMULATED") and len(data["orders"]) == 2


@pytest.mark.unit
def test_the_reporter_never_reads_the_simulators_private_tables():
    from pathlib import Path

    import investment_engine.reporting.order_log as order_log

    assert "sim_broker" not in Path(order_log.__file__).read_text(encoding="utf-8")


@pytest.mark.unit
def test_an_account_without_orders_says_so_and_never_prints_none(cli):
    app, _ = cli
    log = run(app, "intents", "order-log", "--account", "R2")
    assert log.exit_code == 0, log.output
    assert "range: none (no orders)" in log.output and "by final state: none (no orders)" in log.output
    assert "None" not in log.output
