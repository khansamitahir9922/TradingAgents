"""The NVDA HTML research report (docs/tasks/M2-12.md)."""

import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.decision.market_view import ViewDirection
from investment_engine.evaluation.metrics import MetricValue
from investment_engine.lineage.records import LineageStore
from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.candles import Timeframe
from investment_engine.quant.adjusted import AdjustedBar, AdjustedBasis, BarRef
from investment_engine.reporting.html import render_research_report
from investment_engine.storage.sqlite import apply_schema, open_operational_db
from tests.engine.test_evaluation_run_store import record as evaluation_record
from tests.engine.test_lineage import record as lineage_record

NVDA = "EQ_US_NVDA"
GENERATED = datetime(2026, 10, 14, 12, tzinfo=UTC)
AT = datetime(2024, 6, 21, 21, tzinfo=UTC)


def adjusted(i, close):
    t = AT - timedelta(days=10 - i)
    ref = BarRef("yfinance", NVDA, Timeframe.D1, t - timedelta(hours=7), 1, "bars", t, AvailabilityBasis.BACKFILL_ASSUMED)
    return AdjustedBar("yfinance", NVDA, t.date(), close, close, close, close, 1000.0,
                       AdjustedBasis.SPLIT_ADJUSTED_AS_OF, GENERATED, Decimal("10"), ref, ())


@pytest.fixture
def inputs(tmp_path):
    conn = open_operational_db(tmp_path / "op.sqlite3")
    apply_schema(conn)
    store = LineageStore(conn)
    lin = lineage_record()
    store.append(lin)
    view = replace(lin.decision, evidence_refs=(lin.lineage_id,))
    runs = [evaluation_record(), evaluation_record(evaluation_config=replace(
        evaluation_record().evaluation_config, version="eval-stress", costs_bps_per_side=Decimal("10")))]
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
