"""The CLI's replay keeps the stored views' own delivery history (Codex M4 re-review R2; Law 5).

A stored view was generated at its decision bar's delivery: available_from + the feed's latency (M2's run_views).
So each view states its latency exactly. The CLI rebuilds its feed with that latency, so a correction available
between the bar and the view's time, but delivered after it, stays unseen by the proposal. Views that disagree, or
whose decision bar can't be found, are refused: no delivery history is assumed.
"""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.config import ENV_PG_DSN
from investment_engine.killswitch.flag import FLAG_FILE, FlagState, encode_flag
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import MarketDataWriter
from tests.engine.test_intent_pipeline import CAL, NOW, NVDA, SESSIONS, Env, view_for
from tests.engine.test_order_log import run as invoke
from tests.engine.test_raw_reference import observation

pytestmark = pytest.mark.postgres
LATENCY = timedelta(minutes=10)


@pytest.fixture
def produced(pg_database, tmp_path, monkeypatch):
    """A warmed-up history, a correction of the last session's bar available five minutes after its close (so
    delivered at +15 under the feed's latency), and the views M2's own producer made from it at ten-minute latency."""
    from investment_engine import admin_cli, intents_cli
    from investment_engine.decision.pipeline import run_views
    from investment_engine.market.candles import Timeframe
    from investment_engine.market.replay import ReplayFeed
    from investment_engine.market.symbols import SymbolMapping
    from investment_engine.quant.strategies.pullback import PullbackStrategy
    from investment_engine.quant.strategies.trend import TrendStrategy
    from investment_engine.storage.sqlite import SqliteSymbolResolver
    from tests.engine.test_view_pipeline import EVIDENCE

    root, day = tmp_path / "market", SESSIONS[60]
    available = CAL.session(day).close
    writer = MarketDataWriter(root)
    bars = []
    for n, d in enumerate(s.date for s in CAL.sessions_between(date(2023, 1, 3), day)):
        price = Decimal(100) + Decimal(n) / 10
        bars.append(replace(observation(d, close=str(price)), open=price, high=price, low=price,
                            volume=Decimal("1000000")))
    writer.write_candles(bars, import_id="bars")
    writer.write_candles([replace(observation(day, close="119.0000", received=available + timedelta(minutes=5)),
                                  volume=Decimal("1000000"))], import_id="correction")
    reader = MarketDataReader(root)
    env = Env(pg_database, root, reader=reader)
    env.account("R2", level=2)
    SqliteSymbolResolver(env.stores.db).add(SymbolMapping(NVDA, "yfinance", "NVDA", date(2019, 1, 1), None))
    generated = available + LATENCY
    feed = ReplayFeed(reader, ReplayClock(generated - timedelta(days=1000)), sources=["yfinance"], instrument_ids=[NVDA],
                      timeframes=[Timeframe.D1], start=generated - timedelta(days=1000),
                      end=generated + timedelta(microseconds=1), latency=LATENCY)
    views = list(run_views(feed, instrument_id=NVDA, source="yfinance", strategies=(TrendStrategy(), PullbackStrategy()),
                           policy_version="0.1.0", calendar=CAL, instruments=env.stores.instruments,
                           resolver=SqliteSymbolResolver(env.stores.db), lineage_store=env.stores.lineage,
                           coverage_evidence=EVIDENCE, coverage_first=date(2019, 1, 1), coverage_last=date(2026, 10, 12),
                           coverage_reason="test fixture", calendar_version="cal-1", code_version="test"))
    view = views[-1]
    assert view.generated_at == generated and view.direction.value == "BULLISH"  # a real, actionable M2 decision
    flag = tmp_path / "control" / FLAG_FILE
    flag.parent.mkdir(parents=True)
    flag.write_text(encode_flag(FlagState(True, 1, NOW, "owner", True, "go")), encoding="utf-8")
    monkeypatch.setenv(ENV_PG_DSN, pg_database)
    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path))
    for module in (admin_cli, intents_cli):
        monkeypatch.setattr(module, "LiveClock", lambda: ReplayClock(NOW))
    yield env, day, view
    env.close()


@pytest.mark.unit
def test_simulate_keeps_the_views_delivery_latency(produced, monkeypatch):
    """R2: the CLI rebuilt every feed with zero latency, so the correction (available at +5, delivered at +15)
    reached the proposal of the view generated at +10, which had decided on revision 1."""
    from investment_engine import cli
    from investment_engine.simulation import run as run_module
    from investment_engine.simulation.run import SimulationReport

    env, day, view = produced
    seen = []

    def inspect(account, **kwargs):
        knowledge = kwargs["proposal_knowledge"](view, env.stores)
        seen.append(knowledge.latest_closed("yfinance", NVDA, day, at=view.generated_at, calendar=CAL).revision)
        return SimulationReport(account, 1, {}, 0, ())

    monkeypatch.setattr(run_module, "simulate", inspect)
    result = invoke(cli, "intents", "simulate", "--account", "R2", "--from", day.isoformat(),
                    "--to", CAL.next_session(day).date.isoformat())
    assert result.exit_code == 0, result.output
    assert seen == [1]  # the view's own knowledge: the correction is not yet delivered


@pytest.mark.unit
def test_propose_keeps_the_views_delivery_latency(produced, monkeypatch):
    from investment_engine import cli
    from investment_engine.oms import pipeline

    env, day, view = produced
    seen, real = [], pipeline.propose

    def capture(*args, **kwargs):
        seen.append(kwargs["knowledge"].latest_closed("yfinance", NVDA, day, at=kwargs["at"], calendar=CAL).revision)
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, "propose", capture)
    result = invoke(cli, "intents", "propose", "--account", "R2", "--at", view.generated_at.isoformat())
    assert result.exit_code == 0, result.output
    assert seen == [1]


@pytest.mark.unit
def test_views_made_with_different_latencies_are_refused_not_assumed(pg_database, tmp_path, monkeypatch):
    from investment_engine import admin_cli, cli, intents_cli
    from tests.engine.test_intent_pipeline import write_bars

    env = Env(pg_database, tmp_path / "market", reader=write_bars(tmp_path / "market", SESSIONS))
    try:
        env.account("R2", level=2)
        for k, day in enumerate((SESSIONS[60], SESSIONS[61])):  # one at zero latency, one at ten minutes
            view_for(env.stores, env.reader, day, tag=f"mixed-{k}",
                     generated_at=CAL.session(day).close + (LATENCY if k else timedelta(0)))
        monkeypatch.setenv(ENV_PG_DSN, pg_database)
        monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path))
        for module in (admin_cli, intents_cli):
            monkeypatch.setattr(module, "LiveClock", lambda: ReplayClock(NOW))
        for args in (("simulate", "--account", "R2", "--from", SESSIONS[59].isoformat(), "--to", SESSIONS[62].isoformat()),
                     ("propose", "--account", "R2", "--from", SESSIONS[59].isoformat(), "--to",
                      SESSIONS[62].isoformat())):
            result = invoke(cli, "intents", *args)
            assert result.exit_code == 1 and "different delivery latencies" in result.output, result.output
    finally:
        env.close()
