"""Research commands (M6-08; D49, D50). Requests are recorded, never run inline.

`research request` (Trader or Admin, with a reason) records a job for today's
exchange date; the Research Worker runs it. `research budget set` is Admin-only.
`research status`, `research show` and `research budget show` are read-only.
This module never imports TradingAgents, LangChain or the research adapter.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import typer

research_app = typer.Typer(no_args_is_help=True, help="Advisory TradingAgents research: request, status, budget.")
budget_app = typer.Typer(no_args_is_help=True, help="The daily LLM budget (Admin sets; anyone reads).")
research_app.add_typer(budget_app, name="budget")

EXCHANGE_ZONE = ZoneInfo("America/New_York")
ANALYSTS = ("market", "social", "news", "fundamentals")


def _stores(db, clock):
    from investment_engine.audit.events import AuditStore
    from investment_engine.events.outbox import Outbox
    from investment_engine.oms.order_states import ProcessRole
    from investment_engine.policy.accounts import AccountRegistry
    from investment_engine.research.store import ResearchStore

    audit = AuditStore(db)
    store = ResearchStore(db, role=ProcessRole.CORE, audit=audit,
                          outbox=Outbox(db, writer=ProcessRole.CORE, clock=clock), clock=clock)
    return store, AccountRegistry(db, audit, clock)


def request_research(db, *, instrument_id: str, operator: str, reason: str, provider: str, quick_model: str,
                     deep_model: str, live_clock, research_date: date | None = None, debate_rounds: int = 1,
                     risk_rounds: int = 1):
    from investment_engine.admin_cli import _actor
    from investment_engine.market.availability import check_name
    from investment_engine.policy.accounts import Role
    from investment_engine.research.contracts import ResearchJob, ResearchSettings
    from investment_engine.storage.sqlite import SqliteSymbolResolver

    check_name(reason, "reason")
    store, accounts = _stores(db, live_clock)
    now = live_clock.now()
    today = now.astimezone(EXCHANGE_ZONE).date()
    if research_date is not None and research_date != today:
        raise ValueError(f"research runs only for the current exchange date {today.isoformat()} (D50); "
                         "historical research would see later news")
    ticker = SqliteSymbolResolver(db).symbol_for(instrument_id, "yfinance", today)
    settings = ResearchSettings(provider, quick_model, deep_model, debate_rounds, risk_rounds, ANALYSTS, None, "English")
    with db.transaction():
        db.lock(f"operator|{operator}")
        actor = _actor(accounts, operator)
        accounts.authorize(actor, (Role.TRADER, Role.ADMIN), live_clock.now())
        version = store.request(ResearchJob(instrument_id, ticker, today, operator, now, reason, settings), by=actor)
    store.outbox.publish_pending()  # after the commit: the request's event does not wait for a Core process
    return version


def set_budget(db, *, operator: str, reason: str, daily_requests: int, daily_tokens: int, reserve_requests: int,
               reserve_tokens: int, live_clock, daily_usd=None):
    """Admin only, authorized at live command time under the operator's lock; versioned and audited (D46)."""
    from investment_engine.admin_cli import _actor
    from investment_engine.audit.events import AuditEvent
    from investment_engine.market.availability import check_utc
    from investment_engine.policy.accounts import Role
    from investment_engine.research.contracts import BudgetPolicy

    store, accounts = _stores(db, live_clock)
    with db.transaction():
        db.lock(f"operator|{operator}")
        actor = _actor(accounts, operator)
        now = check_utc(live_clock.now(), "command time")
        accounts.authorize(actor, (Role.ADMIN,), now)
        latest = store.latest_policy()
        policy = BudgetPolicy(1 if latest is None else latest.version + 1, daily_requests, daily_tokens, daily_usd,
                              reserve_requests, reserve_tokens, actor.actor_id, now, reason)
        store.set_policy(policy)
        key = f"research.budget_policy:{policy.version}"
        store.audit.append(AuditEvent(actor, "research.budget_policy", "research-budget", "daily", latest, policy,
                                      now, None, reason, key, key))
        return policy


def status_text(db, job_id: str) -> str:
    from investment_engine.clock import LiveClock

    store, _ = _stores(db, LiveClock())
    job = store.job(job_id)
    lines = [f"Job {job_id}: {job.instrument_id} ({job.ticker}) for {job.research_date.isoformat()}, requested by "
             f"{job.requested_by} at {job.requested_at.isoformat()}",
             f"Models: {job.settings.provider} {job.settings.quick_model} / {job.settings.deep_model}"]
    lines += [f"  v{v.version} {v.state.value} at {v.at.isoformat()} by {v.actor}" + (f" run {v.run_id}" if v.run_id else "")
              + f": {v.reason}" for v in store.versions(job_id)]
    return "\n".join(lines)


def show_text(db, run_id: str) -> str:
    from investment_engine.clock import LiveClock

    store, _ = _stores(db, LiveClock())
    record = store.record(run_id)
    u = record.usage
    lines = [f"Run {run_id}: {record.outcome.value} (attempt {record.attempt}), {record.started_at.isoformat()} to "
             f"{record.finished_at.isoformat()}",
             f"Usage: {u.requests} requests, tokens in {u.input_tokens if u.input_tokens is not None else 'UNKNOWN'}, "
             f"out {u.output_tokens if u.output_tokens is not None else 'UNKNOWN'}, {u.tool_calls} tool calls",
             f"Upstream {record.upstream_version}; code {record.code_version}"]
    if record.failure:
        lines.append(f"Failure: {record.failure}")
    try:
        ctx = store.context(run_id)
    except KeyError:
        lines.append("No research context (the run produced none).")
    else:
        now = LiveClock().now()
        levels = ctx.suggested_levels
        lines += [f"ADVISORY research, not used by sizing, risk or orders. Status: {ctx.status(now)} "
                  f"(valid until {ctx.valid_until.isoformat()})",
                  f"Rating: {ctx.rating.value} ({ctx.source.value}); trader action: "
                  f"{ctx.trader_action.value if ctx.trader_action else 'unavailable'}",
                  f"{levels.label}: entry {levels.entry if levels.entry is not None else 'none'}, "
                  f"stop {levels.stop if levels.stop is not None else 'none'}"]
        lines += [f"Warning: {w}" for w in ctx.warnings]
    lines += [f"Warning: {w}" for w in record.warnings]
    return "\n".join(lines)


def budget_text(db, *, day: date) -> str:
    from investment_engine.clock import LiveClock
    from investment_engine.research.budget import day_totals

    store, _ = _stores(db, LiveClock())
    policy = store.latest_policy()
    requests, tokens = day_totals(store.usage_on(day))
    if policy is None:
        return f"No budget policy is set: research is refused. Used on {day.isoformat()}: {requests} requests."
    return (f"Budget policy v{policy.version} (set by {policy.set_by} at {policy.set_at.isoformat()}): "
            f"{policy.daily_requests} requests and {policy.daily_tokens} tokens per UTC day; each run reserves "
            f"{policy.reserve_requests} requests and {policy.reserve_tokens} tokens.\n"
            f"Used on {day.isoformat()}: {requests} requests, {tokens} tokens (measured usage replaces reservations).")


def _with_db(action, *, read_only: bool) -> None:
    from investment_engine.cli import _fail, _open_db

    conn = None
    try:
        conn, db = _open_db(read_only=read_only)
        action(db)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc)
        raise typer.Exit(1) from None
    finally:
        if conn is not None:
            conn.close()


@research_app.command("request")
def request_command(instrument: str, operator: str = typer.Option(..., "--operator"),
                    reason: str = typer.Option(..., "--reason"),
                    quick_model: str = typer.Option(..., "--quick-model", help="pinned model version (D45)"),
                    deep_model: str = typer.Option(..., "--deep-model", help="pinned model version (D45)"),
                    provider: str = typer.Option("google", "--provider"),
                    research_date: str | None = typer.Option(None, "--date", help="must be today's exchange date")):
    """Record a research request; the Research Worker runs it within the daily budget."""
    from investment_engine.cli import _print
    from investment_engine.clock import LiveClock

    def action(db):
        version = request_research(db, instrument_id=instrument, operator=operator, reason=reason, provider=provider,
                                   quick_model=quick_model, deep_model=deep_model, live_clock=LiveClock(),
                                   research_date=None if research_date is None else date.fromisoformat(research_date))
        _print(f"Research requested: job {version.job_id}. It is ADVISORY and runs in the Research Worker; "
               "nothing is traded.")
    _with_db(action, read_only=False)


@research_app.command("status")
def status_command(job_id: str):
    """Read-only: a job's history."""
    from investment_engine.cli import _print
    _with_db(lambda db: _print(status_text(db, job_id)), read_only=True)


@research_app.command("show")
def show_command(run_id: str):
    """Read-only: a run's record summary and its advisory context."""
    from investment_engine.cli import _print
    _with_db(lambda db: _print(show_text(db, run_id)), read_only=True)


@budget_app.command("set")
def budget_set_command(operator: str = typer.Option(..., "--operator"), reason: str = typer.Option(..., "--reason"),
                       daily_requests: int = typer.Option(..., "--daily-requests"),
                       daily_tokens: int = typer.Option(..., "--daily-tokens"),
                       reserve_requests: int = typer.Option(..., "--reserve-requests"),
                       reserve_tokens: int = typer.Option(..., "--reserve-tokens")):
    """Admin only: set the daily caps (D46)."""
    from investment_engine.cli import _print
    from investment_engine.clock import LiveClock

    def action(db):
        policy = set_budget(db, operator=operator, reason=reason, daily_requests=daily_requests,
                            daily_tokens=daily_tokens, reserve_requests=reserve_requests,
                            reserve_tokens=reserve_tokens, live_clock=LiveClock())
        _print(f"Budget policy v{policy.version} set.")
    _with_db(action, read_only=False)


@budget_app.command("show")
def budget_show_command():
    """Read-only: today's (UTC) caps and usage."""
    from datetime import UTC

    from investment_engine.cli import _print
    from investment_engine.clock import LiveClock
    _with_db(lambda db: _print(budget_text(db, day=LiveClock().now().astimezone(UTC).date())), read_only=True)
