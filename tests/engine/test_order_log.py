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


def recorded_bars_with_a_correction_at_the_sell_view(root):
    """Bars recorded as they happened (each received a minute after its close), and a correction of SESSIONS[62]'s
    bar received at exactly the time of the view made from that bar."""
    from tests.engine.test_intent_pipeline import t_of

    writer = MarketDataWriter(root)
    writer.write_candles([replace(observation(d, close="120.0000"), volume=Decimal("1000000")) for d in SESSIONS],
                         import_id="bars")
    writer.write_candles([replace(observation(SESSIONS[62], close="119.0000", received=t_of(SESSIONS[62])),
                                  volume=Decimal("1000000"))], import_id="correction-at-the-view-time")
    return MarketDataReader(root)


@pytest.fixture
def cli(pg_database, tmp_path, monkeypatch):
    yield from cli_with(pg_database, tmp_path, monkeypatch, backfilled_bars)


@pytest.fixture
def cli_and_env(pg_database, tmp_path, monkeypatch):
    yield from cli_with(pg_database, tmp_path, monkeypatch, backfilled_bars, with_env=True)


@pytest.fixture
def cli_with_a_correction(pg_database, tmp_path, monkeypatch):
    yield from cli_with(pg_database, tmp_path, monkeypatch, recorded_bars_with_a_correction_at_the_sell_view)


def cli_with(pg_database, tmp_path, monkeypatch, bars, with_env=False):
    from investment_engine import admin_cli, cli, intents_cli

    env = Env(pg_database, tmp_path / "market", reader=bars(tmp_path / "market"))
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
    yield (cli, tmp_path, env) if with_env else (cli, tmp_path)
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


@pytest.mark.unit
def test_a_proposal_never_sees_an_equal_time_event_its_view_did_not(cli_with_a_correction, pg_database):
    """B3 (Codex M4 review): `simulate` preloaded the whole feed with no per-view sequence boundary, so a correction
    delivered at exactly a view's time, after the view's own bar, reached that proposal (Law 5). Each proposal
    now has its view's boundary, as M3's replay path does; the gate, a moment later, does see the correction."""
    from investment_engine.audit.events import AuditStore
    from investment_engine.oms.order_states import OrderState, ProcessRole
    from investment_engine.oms.order_store import OrderStore
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg
    from tests.engine.recording_outbox import RecordingOutbox
    app, _ = cli_with_a_correction
    sell_day = SESSIONS[62]
    done = run(app, "intents", "simulate", "--account", "R2", "--from", SESSIONS[59].isoformat(), "--to",
               SESSIONS[63].isoformat())
    assert done.exit_code == 0 and "2 orders" in done.output, done.output
    conn = open_operational_pg(pg_database)
    try:
        db = PostgresDatabase(conn)
        orders = OrderStore(db, role=ProcessRole.CORE, audit=AuditStore(db), outbox=RecordingOutbox(db),
                            clock=ReplayClock(NOW))
        rows = {o.target_session: (o, st) for o, st in orders.for_account("R2")}
        sell, status = rows[CAL.next_session(sell_day).date]
        assert status.state is OrderState.GATE_REJECTED  # proposed on the view's revision; the gate saw the newer one
        (gate,) = orders.gate_decisions(sell.order_id)
        assert [c.name for c in gate.checks if not c.passed] == ["view"]
    finally:
        conn.close()


@pytest.mark.unit
def test_simulate_feeds_the_whole_local_history_and_says_where_its_knowledge_begins(cli, monkeypatch):
    """B7 (Codex M4 review): the feed began sixty days before the first view, so actions since an earlier declared
    start were absent while the projection looked complete."""
    import investment_engine.market.replay as replay
    from investment_engine.simulation import run as run_module
    from tests.engine.test_intent_pipeline import START

    app, _ = cli
    starts, seen = [], []
    real_feed, real_simulate = replay.ReplayFeed, run_module.simulate

    def recording_feed(*args, **kwargs):
        starts.append(kwargs["start"])
        return real_feed(*args, **kwargs)

    def recording_simulate(*args, **kwargs):
        seen.append(kwargs["knowledge"].known_from)
        return real_simulate(*args, **kwargs)

    monkeypatch.setattr(replay, "ReplayFeed", recording_feed)
    monkeypatch.setattr(run_module, "simulate", recording_simulate)
    done = run(app, "intents", "simulate", "--account", "R2", "--from", SESSIONS[59].isoformat(), "--to",
               SESSIONS[63].isoformat())
    assert done.exit_code == 0, done.output
    assert starts and starts[0] <= START and seen == [starts[0]]  # from before the declared start, and it says so


# ---------------------------------------------------------------- ordinary proposals use the order store (B6)


def proposal(env, view_day):
    """The stored proposal for R2's view of `view_day`."""
    from tests.engine.test_intent_pipeline import t_of

    (record,) = [r for r in env.stores.proposals.for_account("R2") if r.at == t_of(view_day)]
    return record


@pytest.mark.unit
def test_intents_propose_after_a_fill_sizes_the_sell_on_what_was_filled(cli_and_env):
    """B6 (Codex M4 review): `intents propose` kept M3's declared snapshot after M4 fills existed, so a BEARISH view
    after a filled BUY said "nothing held"."""
    from tests.engine.test_conversion import order_store
    from tests.engine.test_intent_pipeline import t_of

    app, _, env = cli_and_env
    done = run(app, "intents", "simulate", "--account", "R2", "--from", SESSIONS[59].isoformat(), "--to",
               SESSIONS[61].isoformat())  # only the BUY view of SESSIONS[60]
    assert done.exit_code == 0 and "1 orders" in done.output, done.output
    ((buy, status),) = order_store(env).for_account("R2")
    assert status.state.value == "FILLED"
    proposed = run(app, "intents", "propose", "--account", "R2", "--at", t_of(SESSIONS[62]).isoformat())
    assert proposed.exit_code == 0, proposed.output
    record = proposal(env, SESSIONS[62])
    assert record.intent_id is not None, record.reason
    intent = env.stores.intents.get(record.intent_id).intent
    assert (intent.side.value, intent.quantity) == ("SELL", buy.quantity)


@pytest.mark.unit
def test_a_second_buy_while_the_first_is_pending_counts_the_pending_exposure(cli_and_env):
    from investment_engine.events.outbox import Outbox
    from investment_engine.oms.conversion import convert_approved
    from investment_engine.oms.order_states import ProcessRole
    from investment_engine.oms.order_store import OrderStore
    from tests.engine.test_intent_pipeline import t_of

    app, _, env = cli_and_env
    first = run(app, "intents", "propose", "--account", "R2", "--at", t_of(SESSIONS[60]).isoformat())
    assert first.exit_code == 0 and proposal(env, SESSIONS[60]).intent_id is not None, first.output
    # Converted at replay time, as the harness's Core role does (the projection is point in time: an order recorded
    # later than a proposal is unknown to it). NEW: not yet filled.
    core = env.connect(ReplayClock(t_of(SESSIONS[60])))
    orders = OrderStore(core.db, role=ProcessRole.CORE, audit=core.audit,
                        outbox=Outbox(core.db, writer=ProcessRole.CORE, clock=core.clock), clock=core.clock)
    (pending,) = convert_approved("R2", at=t_of(SESSIONS[60]), stores=core, orders=orders).converted
    view_for(env.stores, env.reader, SESSIONS[61], "BULLISH", tag="second-buy")
    second = run(app, "intents", "propose", "--account", "R2", "--at", t_of(SESSIONS[61]).isoformat())
    assert second.exit_code == 0, second.output
    record = proposal(env, SESSIONS[61])
    # The pending BUY's remainder x limit holds the cap's room: what is left buys less than one share. Without the
    # pending order the same proposal was APPROVED (the red run of this test).
    assert record.outcome.value == "NO_INTENT" and "below one share (room" in record.reason, record.reason
    assert pending.quantity > 0


@pytest.mark.unit
def test_a_proposal_without_the_order_store_fails_closed_once_the_account_has_orders(cli_and_env):
    from investment_engine.oms.pipeline import propose
    from tests.engine.test_intent_pipeline import CAL as PIPELINE_CAL, t_of

    app, _, env = cli_and_env
    assert run(app, "intents", "simulate", "--account", "R2", "--from", SESSIONS[59].isoformat(), "--to",
               SESSIONS[61].isoformat()).exit_code == 0
    view = view_for(env.stores, env.reader, SESSIONS[63], "BEARISH", tag="no-order-store")
    record = propose("R2", view, at=t_of(SESSIONS[63]), stores=env.stores, knowledge=env.knowledge,
                     calendar=PIPELINE_CAL, coverage=None, calendar_version="cal-1", code_version="test",
                     correlation_id="no-order-store")
    assert record.outcome.value == "PREREQUISITE_MISSING" and "order history" in record.missing, record.reason


@pytest.mark.unit
def test_an_unknown_order_never_claims_a_lookup_that_has_not_happened(pg_database, tmp_path):
    """B11: every UNKNOWN was labelled "broker has no record", even straight after a lost submit answer."""
    from investment_engine.reporting.order_log import build_order_log
    from tests.engine.test_intent_pipeline import DAY
    from tests.engine.worker_env import WorkerEnv, after_close, pre_open

    env = WorkerEnv(pg_database, tmp_path / "market", tmp_path / "control")
    try:
        order, view = env.convert(DAY)
        env.broker.timeout_next_submit = True
        env.broker.lookup = lambda client, *, at: (_ for _ in ()).throw(RuntimeError("not yet"))
        worker = env.worker(pre_open(order, view))
        worker.step()

        def text():
            return build_order_log("R2", orders=worker.orders, intents=env.stores.intents, lineage=env.stores.lineage,
                                   calendar=CAL, source="yfinance", header_extra={}).to_text()

        before = text()
        assert "broker has no record" not in before and "no record at a lookup" not in before
        assert "UNCONFIRMED: the outcome is unknown; no lookup has answered yet" in before
        del env.broker.lookup  # the double's own lookup again
        env.broker.known.pop(order.client_order_id)  # the broker never had it (D20)
        worker = env.worker(after_close(order))
        worker.step()
        after = text()
        assert "UNRESOLVED: the broker had no record at a lookup at " in after
    finally:
        env.close()
