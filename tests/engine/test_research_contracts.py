"""M6-01: immutable research records; advisory, untrusted and honestly incomplete."""
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investment_engine.lineage.records import canonical_json, decode
from investment_engine.oms.order_states import OWNER, ProcessRole
from investment_engine.research.contracts import (
    MAX_TEXT,
    UNTRUSTED_LABEL,
    BudgetPolicy,
    BudgetUsage,
    CallRecord,
    CapturedText,
    ContextSource,
    JobState,
    JobVersion,
    Rating,
    ResearchContext,
    ResearchJob,
    ResearchRecord,
    ResearchSettings,
    RunOutcome,
    ToolRecord,
    TraderAction,
    UntrustedLevels,
    UsageTotals,
    check_job_edge,
)

T = datetime(2026, 1, 9, 15, tzinfo=UTC)
pytestmark = pytest.mark.unit


def settings(**changes):
    return replace(ResearchSettings("google", "gemini-quick-001", "gemini-deep-001", 1, 1,
                                    ("market", "social", "news", "fundamentals"), None, "English"), **changes)


def job(**changes):
    return replace(ResearchJob("EQ_US_NVDA", "NVDA", date(2026, 1, 9), "op-trader", T, "check the thesis",
                               settings()), **changes)


def usage(tokens=True):
    call = CallRecord("c1", "Trader", "gemini-quick-001", T, T + timedelta(seconds=2),
                      10 if tokens else None, 3 if tokens else None, None)
    return (call,), (ToolRecord("t1", "Market Analyst", "get_stock_data", "a" * 64, 40, T, T, None),)


def record(**changes):
    calls, tools = usage()
    value = ResearchRecord(job().job_id, 1, settings(), "0.6.0", "abc123", calls, tools,
                           (CapturedText("c1", "Trader", "prompt", "hello", 0),), (), '{"final_rating":"Buy"}',
                           UsageTotals.of(calls, len(tools)), (), T, T + timedelta(minutes=3), RunOutcome.SUCCEEDED,
                           None)
    return replace(value, **changes)


def context(**changes):
    value = ResearchContext(record().run_id, "EQ_US_NVDA", Rating.OVERWEIGHT, TraderAction.BUY,
                            UntrustedLevels(Decimal("120.5"), Decimal("110")), 5, T, T + timedelta(days=7), (),
                            ContextSource.TYPED)
    return replace(value, **changes)


def test_records_round_trip_through_the_lineage_codec_and_are_frozen():
    for value in (settings(), job(), record(), context(), JobVersion(job().job_id, 1, JobState.REQUESTED, T,
                  "op-trader", None, None, "requested"),
                  BudgetPolicy(1, 3, 300000, None, 1, 100000, "op-admin", T, "provisional D46"),
                  BudgetUsage(date(2026, 1, 9), record().run_id, "RESERVED", 1, 100000, None, T)):
        assert decode(json.loads(canonical_json(value))) == value
    with pytest.raises(FrozenInstanceError):
        job().ticker = "AMD"


def test_ids_are_deterministic_business_identities():
    assert job().job_id == job().job_id and job(reason="other").job_id == job().job_id
    assert job(requested_at=T + timedelta(seconds=1)).job_id != job().job_id  # a new request is a new job
    assert settings(deep_model="gemini-deep-002").settings_hash != settings().settings_hash
    assert record(attempt=2).run_id != record().run_id


@pytest.mark.parametrize("bad", [
    lambda: job(instrument_id="nvda"), lambda: job(requested_at=datetime(2026, 1, 9)),
    lambda: job(requested_at=T.astimezone(timezone(timedelta(hours=5)))), lambda: job(research_date=T),
    lambda: settings(max_debate_rounds=0), lambda: settings(analysts=()), lambda: settings(temperature=0.2),
    lambda: context(valid_until=T - timedelta(seconds=1)), lambda: context(horizon_sessions=0),
    lambda: UntrustedLevels(1.5, None), lambda: UntrustedLevels(Decimal("NaN"), None),
    lambda: UntrustedLevels(Decimal("-1"), None),
    lambda: CapturedText("c1", "Trader", "prompt", "x" * (MAX_TEXT + 1), 0),
    lambda: CapturedText("c1", "Trader", "secret", "x", 0),
    lambda: record(outcome=RunOutcome.FAILED, failure=None),
    lambda: record(finished_at=T - timedelta(seconds=1)),
    lambda: BudgetPolicy(1, 0, 1, None, 1, 1, "op-admin", T, "zero"),
    lambda: BudgetUsage(date(2026, 1, 9), "r", "SPENT", 1, 1, None, T),
])
def test_invalid_values_are_refused(bad):
    with pytest.raises((TypeError, ValueError)):
        bad()


def test_unknown_tokens_stay_unknown_and_known_tokens_sum():
    calls, _ = usage(tokens=False)
    assert UsageTotals.of(calls, 0).input_tokens is None
    assert UsageTotals.of(usage()[0] * 1, 1) == UsageTotals(1, 10, 3, 1)


def test_suggested_levels_are_labelled_untrusted_and_convert_to_nothing():
    levels = UntrustedLevels(Decimal("120.5"), None)
    assert levels.label == UNTRUSTED_LABEL and "not a price used by the system" in UNTRUSTED_LABEL
    assert not any(hasattr(levels, name) for name in ("to_limit", "to_order", "limit_price", "quantity"))


def test_job_state_edges():
    check_job_edge(None, JobState.REQUESTED)
    for a, b in ((JobState.REQUESTED, JobState.CLAIMED), (JobState.CLAIMED, JobState.SUCCEEDED),
                 (JobState.CLAIMED, JobState.FAILED), (JobState.CLAIMED, JobState.BUDGET_REFUSED),
                 (JobState.CLAIMED, JobState.CLAIMED), (JobState.REQUESTED, JobState.EXPIRED_UNCLAIMED)):
        check_job_edge(a, b)
    for a, b in ((None, JobState.CLAIMED), (JobState.SUCCEEDED, JobState.CLAIMED),
                 (JobState.REQUESTED, JobState.SUCCEEDED), (JobState.FAILED, JobState.REQUESTED)):
        with pytest.raises(ValueError):
            check_job_edge(a, b)


def test_research_role_adds_no_order_edge():
    assert ProcessRole.RESEARCH.value == "research-worker"
    assert ProcessRole.RESEARCH not in set(OWNER.values())


def test_contracts_import_no_langchain_or_tradingagents():
    code = ("import sys, investment_engine.research.contracts, investment_engine.audit.events; "
            "print(sorted(m for m in sys.modules if m.split('.')[0] in ('langchain_core', 'tradingagents', 'langgraph')))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"
