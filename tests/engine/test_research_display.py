"""M6-09: research beside the MarketView, labelled advisory, honest about status and gaps."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.reporting.research_view import (
    ADVISORY,
    NOT_REPRODUCIBLE,
    ResearchEvidence,
    panel_html,
    panel_text,
)
from investment_engine.research.contracts import (
    ContextSource,
    Rating,
    TraderAction,
    UntrustedLevels,
)
from tests.engine.test_html_report import inputs, render  # noqa: F401  (fixture and helper)
from tests.engine.test_research_contracts import context, record

T = datetime(2026, 1, 9, 15, tzinfo=UTC)
pytestmark = pytest.mark.unit


def evidence(at=T + timedelta(hours=1), **changes):
    ctx = context(generated_at=T, valid_until=T + timedelta(days=7), **changes)
    return ResearchEvidence(ctx, record(), at)


def test_a_valid_context_shows_everything_labelled_advisory():
    text = panel_text(evidence())
    for part in (ADVISORY, NOT_REPRODUCIBLE, "VALID", "Overweight", "Buy", "TYPED", "120.5", "110",
                 "LLM suggestion: not a price used by the system", "google gemini-quick-001 / gemini-deep-001",
                 record().run_id, T.isoformat()):
        assert part in text, part


def test_an_expired_context_says_expired_in_words():
    text = panel_text(evidence(at=T + timedelta(days=8)))
    assert "EXPIRED" in text and "VALID until" not in text


def test_missing_research_is_never_a_default_rating():
    text = panel_text(ResearchEvidence(None, None, T))
    assert "No research" in text
    assert not any(r.value in text for r in Rating)


def test_fallback_source_and_warnings_are_shown():
    text = panel_text(evidence(source=ContextSource.FREE_TEXT_FALLBACK, trader_action=None,
                               suggested_levels=UntrustedLevels(None, None), warnings=("news_report empty",)))
    assert "FREE_TEXT_FALLBACK" in text and "news_report empty" in text and "unavailable" in text


def test_html_escapes_untrusted_text_and_status_is_not_colour_only():
    html = panel_html(evidence(warnings=("<script>alert('x')</script>",)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert ">VALID<" in html or "VALID" in html  # a word, not only a colour


def test_m2_report_bytes_are_unchanged_without_research_and_gain_the_panel_with_it(inputs):  # noqa: F811
    plain, with_panel = render(inputs), render(inputs, research=evidence())
    assert render(inputs) == plain
    assert ADVISORY not in plain and ADVISORY in with_panel
    assert with_panel.replace(panel_html(evidence()), "") == plain


def test_levels_are_shown_exactly_and_never_rounded():
    text = panel_text(evidence(suggested_levels=UntrustedLevels(Decimal("123.4567"), None),
                               trader_action=TraderAction.HOLD))
    assert "123.4567" in text and "stop none" in text


def test_record_failures_cannot_masquerade_as_research():
    text = panel_text(ResearchEvidence(None, replace(record(), outcome="FAILED", failure="provider 429"), T))
    assert "No research" in text and "provider 429" in text


@pytest.mark.postgres
def test_latest_evidence_reads_the_stored_context_or_the_failed_run_and_the_command_prints_both(
        pg_database, monkeypatch):
    from typer.testing import CliRunner

    from investment_engine.cli import app
    from investment_engine.oms.order_states import ProcessRole
    from investment_engine.reporting.research_view import latest_evidence
    from investment_engine.research.contracts import RunOutcome
    from tests.engine.test_research_contracts import job
    from tests.engine.test_research_store import LEASE, TRADER, Env, context_for

    env = Env(pg_database)
    try:
        at = T + timedelta(hours=2)
        assert latest_evidence(env.db, "EQ_US_NVDA", at=at) == ResearchEvidence(None, None, at)
        core, worker = env.store(ProcessRole.CORE), env.store(ProcessRole.RESEARCH)
        core.request(job(), by=TRADER)
        claim = worker.claim(job().job_id, expected_version=1, worker_id="rw-1", lease=LEASE)
        failed = replace(record(), outcome=RunOutcome.FAILED, failure="provider 429 quota")
        worker.finish(job().job_id, expected_version=2, worker_id="rw-1", record=failed, context=None, usage=None)
        assert "provider 429 quota" in panel_text(latest_evidence(env.db, "EQ_US_NVDA", at=at))
        second = job(requested_at=T + timedelta(seconds=1))
        core.request(second, by=TRADER)
        env.clock.advance_by(timedelta(seconds=1))  # the worker's clock reaches the second request
        claim = worker.claim(second.job_id, expected_version=1, worker_id="rw-1", lease=LEASE)
        rec = replace(record(), job_id=second.job_id)
        worker.finish(second.job_id, expected_version=2, worker_id="rw-1", record=rec,
                      context=context_for(claim.run_id), usage=None)
        found = latest_evidence(env.db, "EQ_US_NVDA", at=at)
        assert found.context == context_for(claim.run_id) and found.record == rec
        monkeypatch.setenv("INVESTMENT_ENGINE_PG_DSN", pg_database)
        result = CliRunner().invoke(app, ["research", "view", "EQ_US_NVDA"])
        assert result.exit_code == 0, result.output
        assert "Latest view: none stored" in result.output and ADVISORY in result.output and "Hold" in result.output
    finally:
        env.conn.close()
