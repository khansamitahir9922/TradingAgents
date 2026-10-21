"""M5-11: exact, pinned accounting reports; missing data is never zero."""
import json
from dataclasses import replace
from decimal import Decimal

import pytest

from investment_engine.reporting.accounting import build_report, legacy_snapshot_report
from tests.engine.test_candles import bar
from tests.engine.test_ledger_activation import env as env
from tests.engine.test_ledger_time import CAL, NVDA, example

pytestmark = pytest.mark.postgres


def report(e, *, mark=True, **kwargs):
    _, close, _, _, sale = example(e)
    session = CAL.session(close.date())
    candle = bar(start_time=session.open, end_time=session.close, event_time=session.close, available_from=session.close,
                 received_at=close, processed_at=close, open=Decimal(125), high=Decimal(125), low=Decimal(125), close=Decimal(125))
    marks = {NVDA: (candle, close)} if mark else {}
    from investment_engine.ledger.restate import sync_account
    from investment_engine.ledger.service import SourceSelector
    from tests.engine.test_ledger_actions import coverage
    selector = SourceSelector(e.db, clock=e.clock, command_clock=e.clock, calendar=CAL, provider="yfinance",
                              coverage=lambda a, t: (coverage(t),), delivered_actions=lambda a, t: ())
    head = sync_account("R1", through=e.clock.now(), sources=selector("R1", e.clock.now()), ledger=e.ledger)
    return build_report("R1", effective_at=close, known_at=e.clock.now(), book_id=head.book_id,
                          ledger=e.ledger, calendar=CAL, source="yfinance", marks=marks, **kwargs)


def test_adr_pnl_228_and_equity_bridge_are_exact_and_auditable(env):
    value = report(env)
    assert value.complete
    payload = json.loads(value.to_json())
    assert payload["metrics"]["net_pnl"] == "228"
    assert payload["metrics"]["equity"] == "100228"
    assert payload["metrics"]["gross_realized"] == "80"
    assert payload["metrics"]["unrealized"] == "150"
    assert payload["metrics"]["fees"] == "2"
    assert payload["label"] == "LEDGER | SIMULATED | RESEARCH | NOT PROMOTED"
    assert payload["sources"] and payload["mark_refs"] and payload["query_id"]
    assert payload["daily_pnl"] is None and payload["daily_reason"]
    assert "228" in value.to_text() and "USD" in value.to_text()


def test_missing_mark_is_prominent_and_not_zero(env):
    value = report(env, mark=False)
    assert not value.complete
    payload = json.loads(value.to_json())
    assert payload["metrics"]["net_pnl"] is None
    assert payload["metrics"]["equity"] is None
    assert payload["metrics"]["cash"] == "99478"
    assert "UNAVAILABLE" in value.to_text() and "raw mark missing" in value.to_text()


def test_html_escapes_text_instead_of_interpreting_it(env):
    value = report(env)
    hostile = replace(value, reasons=("<script>alert('bad')</script>",), complete=False)
    html = hostile.to_html()
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "INCOMPLETE" in html


def test_future_book_and_cross_account_query_are_refused(env):
    value = report(env)
    with pytest.raises(ValueError, match="account|cutoff|book"):
        build_report("R2", effective_at=value.effective_at, known_at=value.known_at, book_id=value.book_id,
                       ledger=env.ledger, calendar=CAL, source="yfinance", marks={})
    from datetime import timedelta
    with pytest.raises(ValueError, match="cutoff"):
        build_report("R1", effective_at=value.effective_at, known_at=value.known_at-timedelta(days=1), book_id=value.book_id,
                       ledger=env.ledger, calendar=CAL, source="yfinance", marks={})


@pytest.mark.parametrize("bad", ["future", "provider", "instrument"])
def test_future_or_unrelated_raw_marks_are_refused(env, bad):
    from datetime import timedelta
    value = report(env)
    session = CAL.session(value.effective_at.date())
    candle = bar(start_time=session.open, end_time=session.close, event_time=session.close, available_from=session.close,
                 received_at=session.close, processed_at=session.close,
                 open=Decimal(125), high=Decimal(125), low=Decimal(125), close=Decimal(125))
    delivered = session.close
    if bad == "future":
        delivered = value.known_at + timedelta(days=1)
    elif bad == "provider":
        candle = replace(candle, source="other")
    else:
        candle = replace(candle, instrument_id="EQ_US_MSFT")
    with pytest.raises(ValueError, match="provider|instrument|future"):
        build_report("R1", effective_at=value.effective_at, known_at=value.known_at, book_id=value.book_id,
            ledger=env.ledger, calendar=CAL, source="yfinance", marks={NVDA: (candle, delivered)})


def test_real_m4_snapshot_keeps_label_and_absent_ledger_fields():
    from pathlib import Path

    from investment_engine.lineage.records import decode
    fixture = json.loads(Path("tests/engine/fixtures/m4_snapshot_record.json").read_text(encoding="utf-8"))
    # Fixture format comes from the accepted M4 code, not a hand-built legacy DTO.
    from investment_engine.portfolio.snapshot import PortfolioSnapshot
    snapshot = PortfolioSnapshot(**decode(json.loads(fixture["content"])))
    value = legacy_snapshot_report(snapshot)
    assert "PROVISIONAL" in value["label"]
    assert value["book_id"] is None and value["basis"] is None
    assert value["snapshot_id"] == snapshot.snapshot_id


def test_uncovered_intermediate_book_cannot_claim_complete_pnl(env):
    _, close, _, _, sale = example(env)
    value = build_report("R1", effective_at=close, known_at=env.clock.now(), book_id=sale.book_id,
                          ledger=env.ledger, calendar=CAL, source="yfinance", marks={})
    assert not value.complete and any("coverage" in r for r in value.reasons)
    assert json.loads(value.to_json())["metrics"]["net_pnl"] is None


def test_query_before_declared_start_is_unavailable_instead_of_zero(env):
    from datetime import timedelta
    value = report(env)
    opening = env.ledger.activation("R1")
    missing = build_report("R1", effective_at=opening.posted_at-timedelta(days=1), known_at=value.known_at,
        book_id=value.book_id, ledger=env.ledger, calendar=CAL, source="yfinance", marks={})
    assert not missing.complete
    assert json.loads(missing.to_json())["metrics"]["cash"] is None


def test_unresolved_incident_is_prominent_and_verified_pnl_is_unavailable(pg_database):
    from tests.engine.test_reconciliation_incidents import Env
    e = Env(pg_database)
    try:
        incident, _ = e.opened()
        book = e.ledger.read_head("R1", known_at=e.clock.now())
        value = build_report("R1", effective_at=e.clock.now(), known_at=e.clock.now(), book_id=book.book_id,
                              ledger=e.ledger, calendar=CAL, source="yfinance", marks={})
        assert not value.complete and incident.incident_id in value.to_text()
        assert json.loads(value.to_json())["metrics"]["net_pnl"] is None
    finally:
        e.conn.close()
