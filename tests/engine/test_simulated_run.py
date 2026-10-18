"""The simulated research run end to end (docs/tasks/M4-13.md rules 1–7)."""

import json
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from investment_engine.killswitch.flag import FLAG_FILE, FlagState, encode_flag
from investment_engine.market.corporate_actions import ActionType, AmountBasis
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import ActionObservation, MarketDataWriter
from investment_engine.money import Money
from investment_engine.oms.order_states import OrderState as S, ProcessRole
from investment_engine.oms.order_store import OrderStore
from investment_engine.policy.accounts import AccountKind
from investment_engine.portfolio.reference import StoreKnowledge
from investment_engine.reporting.order_log import LABEL, build_order_log
from investment_engine.simulation.run import SimulationRefused, simulate
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import open_operational_pg
from tests.engine.recording_outbox import RecordingOutbox
from tests.engine.test_intent_pipeline import CAL, NOW, SESSIONS, Env, view_for
from tests.engine.test_raw_reference import observation

pytestmark = pytest.mark.postgres
A, B, C, E = SESSIONS[60], SESSIONS[62], SESSIONS[64], SESSIONS[66]
COVERAGE = SimpleNamespace(established=True, source="yfinance", instrument_id="EQ_US_NVDA",
                           types=(ActionType.SPLIT, ActionType.DIVIDEND), first=date(2000, 1, 1), last=date(2030, 1, 1))


def bars(root, *, missing=(), actions=()):
    """120 everywhere, except: SESSIONS[63] opens 118 and reaches 119 (a SELL at 118.80 only touches intraday);
    SESSIONS[65] opens 125 with a low of 122 (a BUY at 121.20 never fills). Sessions in `missing` have no bar."""
    special = {SESSIONS[63]: ("118.0000", "119.0000", "117.0000", "118.5000"),
               SESSIONS[65]: ("125.0000", "126.0000", "122.0000", "124.0000")}
    obs = []
    for d in SESSIONS:
        if d in missing:
            continue
        o = replace(observation(d, close="120.0000"), volume=Decimal("1000000"))
        if d in special:
            op, hi, lo, cl = (Decimal(x) for x in special[d])
            o = replace(o, open=op, high=hi, low=lo, close=cl)
        obs.append(o)
    writer = MarketDataWriter(root)
    writer.write_candles(obs, import_id="bars")
    if actions:
        writer.write_corporate_actions(list(actions), import_id="actions")
    return MarketDataReader(root)


def action(kind, ex, *, ratio=None, amount=None):
    """A corporate action on `ex`, known well before the run starts."""
    known = CAL.session(SESSIONS[50]).close
    return ActionObservation(
        source="yfinance", instrument_id="EQ_US_NVDA", currency="USD", exchange_timezone="America/New_York",
        action_type=kind, ex_date=ex, ratio=None if ratio is None else Decimal(ratio),
        amount=None if amount is None else Money(Decimal(amount), "USD"),
        amount_basis=None if amount is None else AmountBasis.AS_REPORTED, new_symbol=None, source_version="1.7.0",
        received_at=known, processed_at=known, backfill_available_from=None)


class Run:
    def __init__(self, dsn, tmp, *, enabled=True, missing=(), actions=()):
        self.env = Env(dsn, tmp / "market", reader=bars(tmp / "market", missing=missing, actions=actions))
        self.env.account("R2", level=2)
        self.dsn, self.flag, self.opened = dsn, tmp / "control" / FLAG_FILE, []
        self.flag.parent.mkdir(parents=True)
        if enabled:
            self.flag.write_text(encode_flag(FlagState(True, 1, NOW, "owner", True, "go")), encoding="utf-8")
        s = self.env.stores
        self.views = [view_for(s, self.env.reader, A, "BULLISH", tag="a"), view_for(s, self.env.reader, B, "BEARISH", tag="b"),
                      view_for(s, self.env.reader, C, "BULLISH", tag="c"), view_for(s, self.env.reader, E, "BULLISH", tag="e")]

    def open_db(self):
        self.opened.append(open_operational_pg(self.dsn))
        return PostgresDatabase(self.opened[-1])

    def run(self, account="R2", views=None):
        return simulate(account, views=views or self.views, open_db=self.open_db,
                        knowledge=StoreKnowledge(self.env.reader, CAL), calendar=CAL, coverage=COVERAGE,
                        flag_path=self.flag, source="yfinance", calendar_version="cal-1", code_version="test")

    def orders(self):
        db = self.env.stores.db
        return OrderStore(db, role=ProcessRole.CORE, audit=self.env.stores.audit, outbox=RecordingOutbox(db),
                          clock=self.env.clock)

    def log(self, report):
        return build_order_log("R2", orders=self.orders(), intents=self.env.stores.intents,
                               lineage=self.env.stores.lineage, calendar=CAL, source="yfinance",
                               header_extra={"kill switch": "test"}, stops=report.stops,
                               snapshots=self.env.stores.snapshots, at=CAL.session(SESSIONS[70]).close)

    def close(self):
        for c in self.opened:
            c.close()
        self.env.close()


@pytest.fixture
def run(pg_database, tmp_path):
    r = Run(pg_database, tmp_path)
    yield r
    r.close()


def correct_decision_bar_just_before_submission(r):
    """A correction of E's decision bar, received a microsecond after E's view: the gate sees it, the proposal didn't."""
    t = r.views[3].generated_at
    MarketDataWriter(r.env.root).write_candles(
        [replace(observation(E, close="119.5000", received=t + timedelta(microseconds=1)), volume=Decimal("1000000"))],
        import_id="correction")
    r.env.reader = MarketDataReader(r.env.root)


@pytest.mark.unit
def test_a_short_range_through_the_whole_order_path(run):
    correct_decision_bar_just_before_submission(run)
    report = run.run()
    rows = {o.target_session: (o, s) for o, s in run.orders().for_account("R2")}
    buy_a, sell_b, buy_c, buy_e = (rows[CAL.next_session(d).date] for d in (A, B, C, E))
    assert buy_a[1].state is S.FILLED and sell_b[1].state is S.FILLED  # open fill, then the intraday-only SELL
    assert buy_c[1].state is S.EXPIRED and buy_e[1].state is S.GATE_REJECTED
    fill_a, = run.orders().fills(buy_a[0].order_id)
    fill_b, = run.orders().fills(sell_b[0].order_id)
    assert fill_a.executed_at == CAL.session(SESSIONS[61]).open and json.loads(fill_a.provenance)["timing"] == "AT_OPEN"
    assert fill_b.executed_at == CAL.session(SESSIONS[63]).close  # stamped at the close, never the open
    assert json.loads(fill_b.provenance)["timing"] == "INTRADAY_UNKNOWN" and fill_b.price == Decimal("118.80")
    assert sell_b[0].quantity == fill_a.quantity  # the SELL was sized on the post-fill portfolio
    (gate,) = run.orders().gate_decisions(buy_e[0].order_id)
    assert [c.name for c in gate.checks if not c.passed] == ["view"]
    assert report.orders == 4 and report.stops == ()


@pytest.mark.unit
def test_with_trading_disabled_every_order_is_gate_rejected_and_the_log_says_why(pg_database, tmp_path):
    r = Run(pg_database, tmp_path, enabled=False)
    try:
        r.run()
        states = {s.state for _, s in r.orders().for_account("R2")}
        assert states == {S.GATE_REJECTED}
        text = r.log(SimpleNamespace(stops=())).to_text()
        assert "kill_switch: trading disabled: missing" in text
    finally:
        r.close()


@pytest.mark.unit
def test_two_fresh_runs_give_byte_identical_logs(tmp_path):
    from tests.engine.conftest import maintenance_dsn, temporary_database

    dsn = maintenance_dsn()
    if dsn is None:
        pytest.skip("PostgreSQL test DSN not set (see docs/dev/postgresql.md)")
    logs = []
    for name in ("one", "two"):
        with temporary_database(dsn) as database:
            r = Run(database, tmp_path / name)
            try:
                logs.append(r.log(r.run()).to_json())
            finally:
                r.close()
    assert logs[0] == logs[1]


@pytest.mark.unit
def test_the_log_is_labelled_ascii_with_units_and_round_trips(run):
    text_log = run.log(run.run())
    text = text_log.to_text()
    assert text.startswith(LABEL) and all(ord(ch) < 128 for ch in text)
    assert "shares" in text and "USD" in text and "timezone: UTC, with exchange time America/New_York" in text
    assert "fill model: daily-fill-v1" in text and "fee schedule: fees-1" in text
    assert json.loads(text_log.to_json())["label"] == LABEL


@pytest.mark.unit
def test_paper_accounts_and_second_runs_are_refused(run):
    run.env.account("P1", level=2, kind=AccountKind.PAPER)
    with pytest.raises(SimulationRefused, match="RESEARCH"):
        run.run(account="P1")
    run.run()
    with pytest.raises(SimulationRefused, match="already has orders"):
        run.run()


@pytest.mark.unit
def test_a_missing_bar_expires_the_order_at_the_cutoff_without_a_fill(pg_database, tmp_path):
    r = Run(pg_database, tmp_path, missing=(SESSIONS[61],))
    try:
        r.run(views=r.views[:1])
        ((order, status),) = r.orders().for_account("R2")
        assert order.target_session == SESSIONS[61] and status.state is S.EXPIRED
        assert r.orders().fills(order.order_id) == []
        expired = [t for t in r.orders().history(order.order_id) if t.to_state is S.EXPIRED]
        assert expired[0].at >= CAL.session(SESSIONS[62]).open  # the cutoff: the next session's open
    finally:
        r.close()


@pytest.mark.unit
def test_a_covered_dividend_becomes_a_receivable_and_the_log_lists_it(pg_database, tmp_path):
    r = Run(pg_database, tmp_path, actions=(action(ActionType.DIVIDEND, SESSIONS[62], amount="0.5000"),))
    try:
        report = r.run(views=r.views[:2])
        rows = {o.target_session: o for o, _ in r.orders().for_account("R2")}
        (fill_a,) = r.orders().fills(rows[SESSIONS[61]].order_id)
        at_b = r.views[1].generated_at
        snapshot = r.env.stores.snapshots.latest("R2", at_b)
        assert snapshot.receivables == fill_a.quantity * Decimal("0.5000")  # entitled at A's fill, paid later
        assert report.stops == ()
        text = r.log(report).to_text()
        assert f"DIVIDEND EQ_US_NVDA {SESSIONS[62]} (receivable {snapshot.receivables} USD)" in text
    finally:
        r.close()


@pytest.mark.unit
def test_a_fractional_split_stops_proposing_with_the_reason_in_the_log(pg_database, tmp_path):
    r = Run(pg_database, tmp_path, actions=(action(ActionType.SPLIT, SESSIONS[62], ratio="1.0001"),))
    try:
        report = r.run()
        assert report.orders == 1 and len(report.stops) == 1  # only A's order; B, C and E are never proposed
        assert "split" in report.stops[0] and report.proposals["NOT_PROPOSED (stopped)"] == 2
        assert report.stops[0].startswith(r.views[1].generated_at.isoformat())
        text = r.log(report).to_text()
        assert "stops (projection unavailable): " + report.stops[0] in text
    finally:
        r.close()
