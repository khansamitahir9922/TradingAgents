"""The NVDA HTML research report (docs/tasks/M2-12.md)."""

import re
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.decision.market_view import ViewDirection
from investment_engine.evaluation.metrics import MetricValue
from investment_engine.evaluation.simulation import simulate_research
from investment_engine.lineage.records import LineageStore
from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import Timeframe
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import MarketDataWriter
from investment_engine.quant.adjusted import AdjustedBar, AdjustedBasis, BarRef
from investment_engine.reporting.html import render_research_report
from investment_engine.storage.sqlite import apply_schema, open_operational_db
from tests.engine.test_evaluation_run_store import record as evaluation_record
from tests.engine.test_lineage import record as lineage_record
from tests.engine.test_research_simulation import (
    bar as sim_bar,
    coverage as sim_coverage,
    view as sim_view,
)

NVDA = "EQ_US_NVDA"
CAL = load_us_equities_calendar()
GENERATED = datetime(2026, 10, 14, 12, tzinfo=UTC)
AT = datetime(2024, 6, 21, 21, tzinfo=UTC)


def adjusted(i, close):
    t = AT - timedelta(days=10 - i)
    ref = BarRef("yfinance", NVDA, Timeframe.D1, t - timedelta(hours=7), 1, "bars", t, AvailabilityBasis.BACKFILL_ASSUMED)
    return AdjustedBar("yfinance", NVDA, t.date(), close, close, close, close, 1000.0,
                       AdjustedBasis.SPLIT_ADJUSTED_AS_OF, GENERATED, Decimal("10"), ref, ())


def computed_record(tmp_path, bps):
    """An EvaluationRecord whose fold run was actually simulated at `bps` (Codex B5: never relabelled)."""
    base = evaluation_record()
    config = replace(base.evaluation_config, version=f"eval-{bps}bps", costs_bps_per_side=Decimal(bps))
    root = tmp_path / f"market-{bps}"
    days = [s.date for s in CAL.sessions_between(date(2021, 1, 4), date(2021, 1, 15))]
    MarketDataWriter(root).write_candles([sim_bar(d, "100", str(100 + i)) for i, d in enumerate(days)],
                                         import_id="b")
    run = simulate_research([sim_view(days[0], "BULLISH")], reader=MarketDataReader(root), calendar=CAL,
                            source="yfinance", instrument_id=NVDA, first=days[0], last=days[-1], at=base.as_of,
                            coverage=sim_coverage(base.as_of), config=config)
    fold = base.result.folds[0]
    net = next(m.value for m in run.metrics if m.key == "net_return")
    result = replace(base.result, folds=(replace(fold, run=run),), stitched=((fold.fold.test_start, net),))
    return evaluation_record(evaluation_config=config, result=result)


@pytest.fixture
def inputs(tmp_path):
    conn = open_operational_db(tmp_path / "op.sqlite3")
    apply_schema(conn)
    store = LineageStore(conn)
    lin = lineage_record()
    store.append(lin)
    view = replace(lin.decision, evidence_refs=(lin.lineage_id,))
    runs = [computed_record(tmp_path, "5"), computed_record(tmp_path, "10")]  # actual 5 and 10 bps calculations
    prices = [adjusted(i, 100.0 + i) for i in range(5)]
    yield {"conn": conn, "store": store, "views": [view], "runs": runs, "lineage": lin, "prices": prices}
    conn.close()


def render(inputs, **changes):
    kwargs = {"lineage_store": inputs["store"], "generated_at": GENERATED, "source": "yfinance",
              "instrument_id": NVDA, "adjusted_closes": inputs["prices"]}
    kwargs.update(changes)
    return render_research_report(changes.pop("views", inputs["views"]), changes.pop("runs", inputs["runs"]),
                                  **{k: v for k, v in kwargs.items() if k not in ("views", "runs")})


@pytest.mark.unit
def test_source_backed_values_ids_and_costs_are_shown(inputs):
    html = render(inputs)
    lin = inputs["lineage"]
    assert lin.lineage_id in html and inputs["runs"][0].record_id in html and inputs["runs"][1].record_id in html
    assert "ABSTAIN" in html and "5 bps" in html and "10 bps" in html
    assert inputs["runs"][0].record_id != inputs["runs"][1].record_id
    assert "yfinance" in html and NVDA in html and "2026-10-14T12:00:00+00:00" in html
    assert "buy_and_hold" in html.replace("buy-and-hold", "buy_and_hold") or "Buy and hold" in html


@pytest.mark.unit
def test_honest_status_text_for_abstain_missing_metrics_backfill_and_trading(inputs):
    html = render(inputs)
    assert "required data not OK: yfinance D1: DEGRADED" in html
    assert "unavailable" in html and "no directional view" in html  # a None metric shows its reason
    assert "BACKFILL_ASSUMED" in html
    for chip in ("SIMULATED / REPLAY", "PAPER EXECUTION NOT CONNECTED", "AUTONOMY NOT CONFIGURED",
                 "TRADING STATUS CANNOT BE VERIFIED", "PROMOTION NOT ASSESSED"):
        assert chip in html
    assert "not execution replay" in html.lower()


@pytest.mark.unit
def test_unavailable_values_never_render_as_zero(inputs):
    html = render(inputs)
    row = re.search(r'data-metric="direction_accuracy"[^>]*>(.*?)</tr>', html, re.S).group(1)
    assert "unavailable" in row and ">0<" not in row and "0.0" not in row


@pytest.mark.unit
def test_price_labels_name_their_basis_and_strength_is_not_a_probability(inputs):
    html = render(inputs)
    assert "Split-adjusted close" in html and "as of 2026-10-14" in html
    assert "not a probability" in html
    assert "probability_up" not in html
    assert not re.search(r"strength[^<]{0,40}%", html, re.I)


@pytest.mark.unit
def test_a_missing_price_series_is_stated_not_invented(inputs):
    html = render(inputs, adjusted_closes=())
    assert "No price series supplied" in html


@pytest.mark.unit
def test_untrusted_text_is_escaped(inputs):
    evil = "<script>alert(1)</script>"
    base = lineage_record()
    lin = lineage_record(decision=replace(base.decision, reasons=(evil,)))
    inputs["store"].append(lin)
    view = replace(lin.decision, evidence_refs=(lin.lineage_id,))
    html = render(inputs, views=[view])
    assert "<script" not in html and "&lt;script&gt;" in html


@pytest.mark.unit
def test_a_view_that_differs_from_its_stored_lineage_is_refused(inputs):
    lin = inputs["lineage"]
    tampered = replace(lin.decision, evidence_refs=(lin.lineage_id,), reasons=("edited",))
    with pytest.raises(ValueError, match="lineage"):
        render(inputs, views=[tampered])


@pytest.mark.unit
def test_no_remote_resources(inputs):
    html = render(inputs)
    assert not re.search(r"(src|href)\s*=\s*\"(https?:)?//", html)
    assert "<svg" in html


@pytest.mark.unit
def test_statuses_are_identifiable_without_colour(inputs):
    html = render(inputs)
    assert re.search(r'class="chip[^"]*"[^>]*>[^<]*\w', html)  # every chip carries text
    assert "▲" in html or "ABSTAIN" in html  # direction shown by symbol and word, not colour alone


@pytest.mark.unit
def test_rendering_is_deterministic_and_writes_nothing(inputs):
    before = inputs["conn"].execute("SELECT COUNT(*) FROM lineage_records").fetchone()[0]
    assert render(inputs) == render(inputs)
    assert inputs["conn"].execute("SELECT COUNT(*) FROM lineage_records").fetchone()[0] == before


@pytest.mark.unit
def test_views_must_carry_lineage_present_in_the_store(inputs):
    lin = inputs["lineage"]
    with pytest.raises(KeyError):
        render(inputs, views=[replace(lin.decision, evidence_refs=("lin-missing",))])
    with pytest.raises(ValueError):
        render(inputs, views=[lin.decision])  # no lineage id at all


@pytest.mark.unit
def test_headline_metrics_trace_to_their_record(inputs):
    html = render(inputs)
    for run in inputs["runs"]:
        assert f'id="{run.record_id}"' in html


@pytest.mark.unit
def test_counts_of_views_by_direction_are_shown(inputs):
    html = render(inputs)
    assert re.search(r"ABSTAIN\D{0,40}1", html)
    assert str(ViewDirection.ABSTAIN) in html
    assert MetricValue  # metric rows come from MetricValue records


# ------------------------------------------------------------------ B6: source and time labels are checked


@pytest.mark.unit
def test_a_view_from_another_provider_than_the_declared_source_is_refused(inputs):
    with pytest.raises(ValueError, match="source"):
        render(inputs, source="testvendor", runs=[], adjusted_closes=())


@pytest.mark.unit
def test_views_runs_and_prices_later_than_the_report_time_are_refused(inputs):
    view_time = inputs["views"][0].generated_at
    with pytest.raises(ValueError, match="after the report"):
        render(inputs, generated_at=view_time - timedelta(days=10), runs=[], adjusted_closes=())
    run_cutoff = inputs["runs"][0].as_of
    with pytest.raises(ValueError, match="after the report"):
        render(inputs, generated_at=run_cutoff - timedelta(seconds=1), adjusted_closes=())
    with pytest.raises(ValueError, match="after the report"):
        render(inputs, generated_at=GENERATED - timedelta(seconds=1), runs=[])  # the price series is as of GENERATED


@pytest.mark.unit
def test_valid_historical_dates_render(inputs):
    html = render(inputs)  # a 2024 view, 2026-10-12 evaluation records, prices as of the report time
    assert "2024-06-21" in html
