"""Cost-inclusive SIMULATED research at next-open raw prices (docs/tasks/M2-10.md)."""

import ast
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from investment_engine.decision.market_view import MarketView, ViewDirection
from investment_engine.evaluation.simulation import (
    EvaluationConfig,
    EvaluationRun,
    simulate_research,
)
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType, AmountBasis, ex_date_start
from investment_engine.market.data_health import Applicability, DataHealth
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import (
    ActionObservation,
    CandleObservation,
    MarketDataWriter,
)
from investment_engine.money import Money
from investment_engine.quant.adjusted import (
    AdjustmentUnavailable,
    VerificationEvidence,
    establish_coverage,
)

NVDA = "EQ_US_NVDA"
CAL = load_us_equities_calendar()
TZ = "America/New_York"
DAYS = [s.date for s in CAL.sessions_between(date(2024, 3, 4), date(2024, 3, 15))]  # Mon 4 – Fri 15
AT = datetime(2024, 3, 20, 22, tzinfo=UTC)
LATE = datetime(2026, 10, 12, 20, tzinfo=UTC)


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


def bar(d, o, c, received_at=None):
    s = CAL.session(d)
    o, c = Decimal(o), Decimal(c)
    received = received_at or s.close
    return CandleObservation(
        source="yfinance", instrument_id=NVDA, timeframe=Timeframe.D1, start_time=s.open, end_time=s.close,
        open=o, high=max(o, c), low=min(o, c), close=c, currency="USD", volume=Decimal("1000"),
        state=BarState.CLOSED, source_version="1.7.0", price_basis=PriceBasis.RAW_AS_REPORTED,
        volume_basis=VolumeBasis.RAW_AS_REPORTED, event_time=s.close, received_at=received, processed_at=received,
        backfill_available_from=s.close)


def action(ex, *, ratio=None, dividend=None):
    return ActionObservation(
        source="yfinance", instrument_id=NVDA, currency="USD", exchange_timezone=TZ,
        action_type=ActionType.SPLIT if ratio else ActionType.DIVIDEND, ex_date=ex,
        ratio=Decimal(ratio) if ratio else None, amount=Money(Decimal(dividend), "USD") if dividend else None,
        amount_basis=AmountBasis.AS_REPORTED if dividend else None, new_symbol=None, source_version="1.7.0",
        received_at=LATE, processed_at=LATE, backfill_available_from=ex_date_start(ex, TZ))


def coverage(at=AT, types=(ActionType.SPLIT, ActionType.DIVIDEND)):
    evidence = [VerificationEvidence("yfinance", NVDA, t, date(2019, 1, 1), date(2026, 10, 12), date(2019, 1, 1),
                                     date(2026, 10, 12), "test-verification", "COMPLETE") for t in types]
    return establish_coverage(evidence, source="yfinance", instrument_id=NVDA, types=types, first=date(2019, 1, 1),
                              last=date(2026, 10, 12), as_of=at, reason="test")


def view(d, direction, *, at=None, valid_until=None, lineage="lin-x"):
    t = at or CAL.session(d).close
    health = DataHealth(NVDA, t, Applicability(True, ""), (), True)
    strength = 0.5 if direction in ("BULLISH", "BEARISH") else 0.0
    return MarketView(NVDA, ViewDirection(direction), strength, None, "5 sessions", t,
                      valid_until or CAL.next_session(d).close, None, health, (f"{lineage}-{d}",), "0.1.0",
                      "warm-up" if direction == "ABSTAIN" else "", ())


CONFIG = EvaluationConfig(version="eval-test", initial_cash=Decimal("10000"), currency="USD",
                          costs_bps_per_side=Decimal("5"), exposure="LONG_OR_CASH",
                          dividend_treatment="CASH_ON_EX_DATE_RESEARCH_ASSUMPTION")


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "market"
    writer = MarketDataWriter(root)
    writer.write_candles([bar(d, "100", "100") for d in DAYS], import_id="flat")
    return {"writer": writer, "reader": MarketDataReader(root), "root": root}


def run(store, views, *, config=CONFIG, first=DAYS[0], last=DAYS[-1], at=AT, cov=None):
    return simulate_research(views, reader=store["reader"], calendar=CAL, source="yfinance", instrument_id=NVDA,
                             first=first, last=last, at=at, coverage=cov or coverage(at), config=config)


def metric(r, key, *, benchmark=None):
    metrics = r.metrics if benchmark is None else next(b for b in r.benchmarks if b.name == benchmark).metrics
    [m] = [m for m in metrics if m.key == key]
    return m


# ------------------------------------------------------------------ timing


@pytest.mark.unit
def test_next_open_and_exact_costs_at_5_bps(store):
    r = run(store, [view(DAYS[0], "BULLISH")])
    [buy] = r.trades
    assert buy.simulated_time == CAL.session(DAYS[1]).open and buy.decision_time == CAL.session(DAYS[0]).close
    # 10000 / (100 * 1.0005) = 99.95 -> 99 shares; cost 99 * 100 * 0.0005 = 4.95.
    assert (buy.side, buy.quantity, buy.raw_price, buy.costs) == ("BUY", Decimal("99"), Decimal("100"),
                                                                 Decimal("4.9500"))
    assert buy.label == "SIMULATED" and buy.decision_lineage_id == f"lin-x-{DAYS[0]}"
    assert r.equity_curve[-1][1] == Decimal("10000") - Decimal("4.95")  # 100 cash left + 99 * 100


@pytest.mark.unit
def test_costs_at_10_bps_and_cash_never_negative(store):
    config = replace(CONFIG, costs_bps_per_side=Decimal("10"), version="eval-stress")
    r = run(store, [view(DAYS[0], "BULLISH"), view(DAYS[2], "NEUTRAL")], config=config)
    buy, sell = r.trades
    assert buy.quantity == Decimal("99") and buy.costs == Decimal("9.9000")
    assert sell.side == "SELL" and sell.costs == Decimal("9.9000")
    assert r.equity_curve[-1][1] == Decimal("10000") - Decimal("19.8")
    assert all(cash >= 0 for _, cash in r.cash_curve)


@pytest.mark.unit
def test_a_decision_at_an_open_cannot_trade_at_that_same_open(store):
    o = CAL.session(DAYS[2]).open
    r = run(store, [view(DAYS[1], "BULLISH", at=o, valid_until=CAL.session(DAYS[3]).close)])
    assert r.trades[0].simulated_time == CAL.session(DAYS[3]).open


@pytest.mark.unit
def test_an_expired_decision_does_not_trade(store):
    expired = view(DAYS[0], "BULLISH", valid_until=CAL.session(DAYS[0]).close + timedelta(hours=1))
    r = run(store, [expired])
    assert r.trades == () and metric(r, "expired_decisions").value == 1


@pytest.mark.unit
def test_the_latest_valid_decision_wins_when_several_target_the_same_open(store):
    close = CAL.session(DAYS[0]).close
    first = view(DAYS[0], "BULLISH", at=close, lineage="first")
    second = view(DAYS[0], "NEUTRAL", at=close + timedelta(minutes=5), lineage="second")
    assert run(store, [first, second]).trades == ()
    r = run(store, [second, replace(first, generated_at=close + timedelta(minutes=10),
                                    data_health=replace(first.data_health, as_of=close + timedelta(minutes=10)))])
    assert [t.side for t in r.trades] == ["BUY"]


@pytest.mark.unit
def test_repeated_unchanged_exposure_does_not_trade_and_abstain_keeps_exposure(store):
    r = run(store, [view(DAYS[0], "BULLISH"), view(DAYS[1], "BULLISH"), view(DAYS[2], "ABSTAIN"),
                    view(DAYS[3], "NEUTRAL"), view(DAYS[4], "BEARISH")])
    assert [t.side for t in r.trades] == ["BUY", "SELL"]
    assert r.trades[1].simulated_time == CAL.session(DAYS[4]).open  # NEUTRAL on day 3 -> cash at day 4's open
    assert metric(r, "abstain_views").value == 1
    assert metric(r, "entries").value == 1 and metric(r, "round_trips").value == 1


# ------------------------------------------------------------------ actions


@pytest.mark.unit
def test_a_split_multiplies_shares_before_trading_with_no_fictitious_loss(tmp_path):
    root = tmp_path / "m"
    writer = MarketDataWriter(root)
    writer.write_candles([bar(DAYS[0], "100", "100"), bar(DAYS[1], "100", "100"), bar(DAYS[2], "50", "50"),
                          bar(DAYS[3], "50", "50")], import_id="b")
    writer.write_corporate_actions([action(DAYS[2], ratio="2")], import_id="a")
    s = {"reader": MarketDataReader(root)}
    r = run(s, [view(DAYS[0], "BULLISH")], last=DAYS[3])
    curve = dict(r.equity_curve)
    assert curve[DAYS[1]] == curve[DAYS[2]] == curve[DAYS[3]]
    assert r.ending_shares == Decimal("198") and len(r.trades) == 1


@pytest.mark.unit
def test_a_dividend_is_cash_on_its_ex_date(tmp_path):
    root = tmp_path / "m"
    writer = MarketDataWriter(root)
    writer.write_candles([bar(DAYS[0], "100", "100"), bar(DAYS[1], "100", "100"), bar(DAYS[2], "99", "99")],
                         import_id="b")
    writer.write_corporate_actions([action(DAYS[2], dividend="1")], import_id="a")
    s = {"reader": MarketDataReader(root)}
    r = run(s, [view(DAYS[0], "BULLISH")], last=DAYS[2])
    curve = dict(r.equity_curve)
    assert curve[DAYS[2]] == curve[DAYS[1]]  # 99 shares lose 1 each in price, gain 1 each in cash
    assert any("ex-date" in lim for lim in r.limitations)


@pytest.mark.unit
def test_unestablished_dividend_coverage_refuses_the_run(store):
    with pytest.raises(AdjustmentUnavailable):
        run(store, [view(DAYS[0], "BULLISH")], cov=coverage(types=(ActionType.SPLIT,)))


# ------------------------------------------------------------------ benchmarks and completeness


@pytest.mark.unit
def test_buy_and_hold_shares_the_first_open_cash_and_costs(store):
    r = run(store, [view(DAYS[2], "NEUTRAL")])
    hold = next(b for b in r.benchmarks if b.name == "buy_and_hold")
    assert hold.entry_time == CAL.session(DAYS[3]).open and hold.shares == Decimal("99")
    assert hold.equity_curve[-1][1] == Decimal("10000") - Decimal("4.95")
    cash = next(b for b in r.benchmarks if b.name == "cash")
    assert all(v == Decimal("10000") for _, v in cash.equity_curve)
    assert r.equity_curve[0][0] == hold.equity_curve[0][0] == DAYS[3]
    assert any("not liquidated" in lim for lim in r.limitations)


@pytest.mark.unit
def test_a_missing_execution_bar_makes_the_run_incomplete_not_zero_priced(tmp_path):
    root = tmp_path / "m"
    writer = MarketDataWriter(root)
    writer.write_candles([bar(d, "100", "100") for d in DAYS if d != DAYS[1]], import_id="b")
    s = {"reader": MarketDataReader(root)}
    r = run(s, [view(DAYS[0], "BULLISH")])
    assert not r.complete and str(DAYS[1]) in " ".join(r.limitations)
    assert metric(r, "net_return").value is None and "incomplete" in metric(r, "net_return").unavailable_reason
    assert r.trades == ()


# ------------------------------------------------------------------ metrics


@pytest.mark.unit
def test_net_return_drawdown_and_sharpe_by_hand(tmp_path):
    root = tmp_path / "m"
    writer = MarketDataWriter(root)
    closes = ["100", "110", "99", "121"]
    writer.write_candles([bar(DAYS[0], "100", "100")] + [bar(DAYS[i + 1], "100", c) for i, c in enumerate(closes)],
                         import_id="b")
    s = {"reader": MarketDataReader(root)}
    config = replace(CONFIG, costs_bps_per_side=Decimal("0"), initial_cash=Decimal("10000"))
    r = run(s, [view(DAYS[0], "BULLISH")], config=config, last=DAYS[4])
    # 100 shares bought at 100: equity 10000, 11000, 9900, 12100.
    assert [v for _, v in r.equity_curve] == [Decimal(x) for x in ("10000", "11000", "9900", "12100")]
    assert metric(r, "net_return").value == pytest.approx(0.21)
    assert metric(r, "max_drawdown").value == pytest.approx(-0.1)
    rets = [0.1, -0.1, 12100 / 9900 - 1]
    mean = sum(rets) / 3
    sd = (sum((x - mean) ** 2 for x in rets) / 2) ** 0.5
    assert metric(r, "sharpe_daily_annualized").value == pytest.approx(mean / sd * 252 ** 0.5)


@pytest.mark.unit
def test_zero_variance_sharpe_is_unavailable(store):
    r = run(store, [view(DAYS[0], "NEUTRAL")])
    m = metric(r, "sharpe_daily_annualized")
    assert m.value is None and m.unavailable_reason


# ------------------------------------------------------------------ revisions and boundaries


@pytest.mark.unit
def test_a_late_correction_changes_realised_revisions_but_not_decision_lineage(store):
    views = [view(DAYS[0], "BULLISH")]
    before = run(store, views)
    store["writer"].write_candles([bar(DAYS[5], "100", "130", received_at=utc(2024, 3, 18))], import_id="fix")
    after = run(store, views)
    assert before.lineage_refs == after.lineage_refs == (f"lin-x-{DAYS[0]}",)
    assert before.equity_curve != after.equity_curve
    assert {r.revision for r in after.input_refs if getattr(r, "start_time", None) == CAL.session(DAYS[5]).open} == {2}
    assert before.run_id != after.run_id


@pytest.mark.unit
def test_runs_are_labelled_simulated_and_deterministic(store):
    a = run(store, [view(DAYS[0], "BULLISH")])
    b = run(store, [view(DAYS[0], "BULLISH")])
    assert isinstance(a, EvaluationRun) and a == b and a.run_id == b.run_id
    assert a.label.startswith("SIMULATED")
    assert all(t.label == "SIMULATED" for t in a.trades)


@pytest.mark.unit
def test_the_module_has_no_broker_oms_ledger_or_clock_access():
    source = Path(__file__).resolve().parents[2] / "investment_engine" / "evaluation" / "simulation.py"
    imports = {n.module for n in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
               if isinstance(n, ast.ImportFrom) and n.module}
    assert not any(word in m for m in imports for word in ("broker", "oms", "ledger", "execution", "clock"))


@pytest.mark.unit
def test_config_is_validated():
    for bad in ({"costs_bps_per_side": Decimal("-1")}, {"initial_cash": Decimal("0")}, {"exposure": "LONG_SHORT"},
                {"costs_bps_per_side": 5}, {"currency": "usd"}):
        with pytest.raises((TypeError, ValueError)):
            replace(CONFIG, **bad)
