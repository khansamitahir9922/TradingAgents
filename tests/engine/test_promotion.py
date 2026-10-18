"""Promotion assessment: evidence target, recipe identity and the aggregate formulas (docs/tasks/M4-10.md)."""

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from investment_engine.evaluation.promotion import (
    FAILED,
    PASSED,
    REFUSED,
    Thresholds,
    assess,
    paper_promotion_status,
    recipe_of,
)

AT = datetime(2026, 10, 18, 12, tzinfo=UTC)
D21 = Thresholds("thresholds-1", Decimal("0.5"), 30, Decimal("0.60"), Decimal("5"))
CASH = Decimal("10000")


def lineage(ref, *, config="cfg-a", source="yfinance", instrument="EQ_US_NVDA", generated=None):
    return SimpleNamespace(lineage_id=ref, policy_version="policy-0.1", strategy_versions={"trend": "1.0"},
                           feature_versions={"sma": "1"}, config={"window": config}, health_thresholds="ht-1",
                           instrument_id=instrument, snapshot=SimpleNamespace(source=source),
                           generated_at=generated or AT)


class Lineages:
    def __init__(self, *records):
        self.records = {r.lineage_id: r for r in records}

    def get(self, ref):
        return self.records[ref]


def curve(returns, start=CASH):
    out, value, day = [], start, date(2024, 1, 2)
    for r in returns:
        value = value * (Decimal(1) + Decimal(str(r)))
        out.append((day, value))
        day += timedelta(days=1)
    return tuple(out)


def fold(returns, hold, trades, refs=("lin-1",), complete=True):
    run = SimpleNamespace(complete=complete, lineage_refs=refs, equity_curve=curve(returns), trades=(None,) * trades,
                          benchmarks=(SimpleNamespace(name="buy_and_hold", equity_curve=curve(hold)),))
    return SimpleNamespace(run=run)


def record(folds, *, costs="5", stitched=None):
    return SimpleNamespace(
        record_id="rec-1", source="yfinance", instrument_id="EQ_US_NVDA", code_version="c", calendar_version="cal",
        walk_forward_config={"train": 24}, evaluation_config=SimpleNamespace(
            version="ev-1", costs_bps_per_side=Decimal(costs), initial_cash=CASH),
        result=SimpleNamespace(folds=tuple(folds), stitched=tuple(stitched or [(AT, 0.1)] * len(folds))))


GOOD = [fold([0.01, 0.02, -0.005, 0.01], [0.01, -0.03, 0.01, 0.0], 10) for _ in range(3)]


def daily_sharpe(rs):
    mean = sum(rs) / len(rs)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rs) / (len(rs) - 1))
    return mean / sd * math.sqrt(252)


@pytest.mark.unit
def test_three_folds_pass_with_the_daily_sharpe_and_total_trades():
    result = assess(record(GOOD), lineage_store=Lineages(lineage("lin-1")), thresholds=D21, as_of=AT)
    assert result.status == PASSED
    criteria = {c.name: c for c in result.criteria}
    expected = daily_sharpe([0.01, 0.02, -0.005, 0.01] * 3)
    assert criteria["sharpe"].value == f"{expected:.4f}"
    fold_returns = [1.01 * 1.02 * 0.995 * 1.01 - 1] * 3  # a six-month-return Sharpe would be undefined here
    assert len(set(fold_returns)) == 1
    assert criteria["trades"].value == "30"  # 10 per fold; the 30 is across folds
    assert result.recipe_id == recipe_of(lineage("lin-1"))


@pytest.mark.unit
@pytest.mark.parametrize("folds, failing", [
    ([fold([0.001, -0.001, 0.001, -0.0011], [0.0] * 4, 10) for _ in range(3)], "sharpe"),
    ([fold([0.05, -0.2, 0.3, 0.05], [0.01, 0.0, 0.01, 0.0], 10) for _ in range(3)], "max_drawdown"),
    ([fold([0.01, 0.02, -0.005, 0.01], [0.01, -0.03, 0.01, 0.0], 9) for _ in range(3)], "trades"),
    ([fold([0.01, 0.02, -0.005, 0.01], [0.01, -0.03, 0.01, 0.0], 10),
      fold([0.04, -0.03, 0.002, -0.02], [0.01, -0.03, 0.01, 0.0], 10),
      fold([0.04, -0.03, 0.002, -0.02], [0.01, -0.03, 0.01, 0.0], 10)], "positive_folds"),
])
def test_each_criterion_can_fail(folds, failing):
    result = assess(record(folds), lineage_store=Lineages(lineage("lin-1")), thresholds=D21, as_of=AT)
    assert result.status == FAILED
    assert failing in [c.name for c in result.criteria if not c.passed]


@pytest.mark.unit
@pytest.mark.parametrize("change, reason", [
    ("incomplete", "incomplete"), ("costs", "below the minimum"), ("missing", "missing"), ("mixed", "mixes 2 recipes"),
    ("provider", "from other"), ("instrument", "is for"), ("stitched", "unavailable")])
def test_ineligible_evidence_is_refused_with_its_reason(change, reason):
    folds, costs, stitched = list(GOOD), "5", None
    store = Lineages(lineage("lin-1"), lineage("lin-2", config="cfg-b"), lineage("lin-3", source="other"),
                     lineage("lin-4", instrument="EQ_US_AMD"))
    if change == "incomplete":
        folds[0] = fold([0.01] * 4, [0.0] * 4, 10, complete=False)
    elif change == "costs":
        costs = "4"
    elif change == "missing":
        folds[1] = fold([0.01] * 4, [0.0] * 4, 10, refs=("lin-gone",))
    elif change == "mixed":
        folds[2] = fold([0.01] * 4, [0.0] * 4, 10, refs=("lin-2",))
    elif change == "provider":
        folds[2] = fold([0.01] * 4, [0.0] * 4, 10, refs=("lin-3",))
    elif change == "instrument":
        folds[2] = fold([0.01] * 4, [0.0] * 4, 10, refs=("lin-4",))
    else:
        stitched = [(AT, 0.1), (AT, None), (AT, 0.1)]
    result = assess(record(folds, costs=costs, stitched=stitched), lineage_store=store, thresholds=D21, as_of=AT)
    assert result.status == REFUSED and any(reason in r for r in result.reasons), result.reasons


@pytest.mark.unit
def test_the_recipe_is_the_decision_parameters_never_the_session_data():
    a, b = lineage("x", config="cfg-a"), lineage("y", config="cfg-b")
    later = lineage("z", config="cfg-a", generated=AT + timedelta(days=200))
    assert recipe_of(a) != recipe_of(b)  # the same costs and execution, other parameters: another recipe
    assert recipe_of(a) == recipe_of(later)  # a later view of the same recipe matches


@pytest.mark.unit
def test_paper_is_blocked_even_by_a_passing_assessment():
    passed = assess(record(GOOD), lineage_store=Lineages(lineage("lin-1")), thresholds=D21, as_of=AT)
    assert "shadow evidence missing" in paper_promotion_status(passed)
    assert "NOT ASSESSED" in paper_promotion_status(None)
    failed = assess(record([fold([0.01, 0.02, -0.005, 0.01], [0.0] * 4, 1)] * 3),
                    lineage_store=Lineages(lineage("lin-1")), thresholds=D21, as_of=AT)
    status = paper_promotion_status(failed)
    assert status.startswith("walk-forward FAILED") and "trades: 3 (needs >= 30)" in status


@pytest.mark.unit
def test_the_same_inputs_give_the_same_assessment_id():
    one = assess(record(GOOD), lineage_store=Lineages(lineage("lin-1")), thresholds=D21, as_of=AT)
    two = assess(record(GOOD), lineage_store=Lineages(lineage("lin-1")), thresholds=D21, as_of=AT + timedelta(days=1))
    assert one.assessment_id == two.assessment_id  # when it was assessed is recorded, not identity


# ---------------------------------------------------------------- the store and the CLI (PostgreSQL)


@pytest.fixture
def pg(pg_database, tmp_path, monkeypatch):
    from investment_engine import admin_cli
    from investment_engine.audit.events import AuditStore
    from investment_engine.clock import ReplayClock
    from investment_engine.config import ENV_PG_DSN
    from investment_engine.policy.accounts import AccountRegistry
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg

    conn = open_operational_pg(pg_database)
    apply_pg_schema(conn)
    db = PostgresDatabase(conn)
    AccountRegistry(db, AuditStore(db), ReplayClock(AT)).bootstrap_admin("owner", os_user="LOQ")
    monkeypatch.setenv(ENV_PG_DSN, pg_database)
    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(admin_cli, "LiveClock", lambda: ReplayClock(AT))
    yield db
    conn.close()


@pytest.mark.postgres
@pytest.mark.unit
def test_thresholds_are_versioned_and_earlier_assessments_keep_theirs(pg):
    from investment_engine.audit.events import Actor, ActorKind, AuditStore
    from investment_engine.evaluation.promotion import PromotionStore, load_proposed_thresholds

    store, owner = PromotionStore(pg, AuditStore(pg)), Actor(ActorKind.OPERATOR, "owner", "ADMIN", None)
    first = store.publish(load_proposed_thresholds(), by=owner, reason="D21", at=AT)
    early = store.record(assess(record(GOOD), lineage_store=Lineages(lineage("lin-1")), thresholds=first, as_of=AT),
                         by=owner)
    second = store.publish({**load_proposed_thresholds(), "min_trades": 50}, by=owner, reason="stricter", at=AT)
    late = store.record(assess(record(GOOD), lineage_store=Lineages(lineage("lin-1")), thresholds=second,
                               as_of=AT + timedelta(days=1)), by=owner)
    assert (first.version, second.version, early.status, late.status) == ("thresholds-1", "thresholds-2", PASSED, FAILED)
    assert store.for_recipe(early.recipe_id, source="yfinance", instrument_id="EQ_US_NVDA") == late
    assert store.current() == second


@pytest.mark.postgres
@pytest.mark.unit
def test_the_cli_publishes_and_assesses_a_real_stored_record_honestly(pg):
    from typer.testing import CliRunner

    from investment_engine import cli
    from investment_engine.cli import shipped_calendars
    from investment_engine.evaluation.run_store import EvaluationRunStore
    from investment_engine.market.calendar.us_equities import load_us_equities_calendar
    from tests.engine.test_evaluation_run_store import record as m2_record

    runner = CliRunner()
    refused = runner.invoke(cli.app, ["promotion", "assess", "--record", "x", "--operator", "owner"])
    assert refused.exit_code == 1 and "no promotion thresholds are published" in refused.output
    published = runner.invoke(cli.app, ["promotion", "thresholds", "publish", "--operator", "owner", "--reason", "D21"])
    assert published.exit_code == 0 and "PUBLISHED thresholds-1" in published.output
    (version,) = shipped_calendars()
    stored = m2_record(calendar_version=version)
    EvaluationRunStore(pg, calendars={v: load_us_equities_calendar() for v in shipped_calendars()}).append(stored)
    out = runner.invoke(cli.app, ["promotion", "assess", "--record", stored.record_id, "--operator", "owner"])
    assert out.exit_code == 0, out.output
    assert out.output.split()[0] in (PASSED, FAILED, REFUSED)  # computed, never assumed
    assert "PAPER promotion:" in out.output and "ACCEPTED" not in out.output
