"""M6-06: the daily LLM budget is enforced before a run and fails closed."""
import threading
from datetime import UTC, date, datetime, timedelta

import pytest

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.oms.order_states import ProcessRole
from investment_engine.policy.accounts import AccountRegistry, NotAuthorized, Role
from investment_engine.research.budget import BudgetRefused, ResearchBudget, actual_usage
from investment_engine.research.contracts import UsageTotals
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import open_operational_pg
from tests.engine.test_research_store import Env

T = datetime(2026, 1, 9, 15, tzinfo=UTC)
OWNER = Actor(ActorKind.OPERATOR, "owner", "ADMIN", "test")
pytestmark = pytest.mark.postgres


@pytest.fixture
def env(pg_database):
    e = Env(pg_database)
    e.accounts = AccountRegistry(e.db, AuditStore(e.db), e.clock)
    e.accounts.bootstrap_admin("owner", os_user="test")
    yield e
    e.conn.close()


def budget(env, role, clock=None):
    return ResearchBudget(env.store(role), clock=clock or env.clock)


def set_policy(env, operator, **kw):
    from investment_engine.research_cli import set_budget

    return set_budget(env.db, operator=operator, live_clock=env.clock, **kw)


def policy(env, requests=3, tokens=300, usd=None, reserve_requests=1, reserve_tokens=100):
    return set_policy(env, "owner", daily_requests=requests, daily_tokens=tokens, daily_usd=usd,
                      reserve_requests=reserve_requests, reserve_tokens=reserve_tokens, reason="provisional D46")


def test_no_policy_refuses_every_run(env):
    with pytest.raises(BudgetRefused, match="no budget policy"):
        budget(env, ProcessRole.RESEARCH).reserve("run-1")


def test_exact_cap_is_allowed_and_one_more_is_refused(env):
    policy(env, requests=3, tokens=1000)
    worker = budget(env, ProcessRole.RESEARCH)
    for n in range(3):
        worker.reserve(f"run-{n}")
    with pytest.raises(BudgetRefused) as refused:
        worker.reserve("run-3")
    assert "requests 3 + 1 > 3" in str(refused.value)
    assert env.db.fetchone("SELECT count(*) FROM research_budget_usage")[0] == 3


def test_tokens_cap_and_measured_usage_replaces_the_reservation(env):
    policy(env, requests=10, tokens=250, reserve_tokens=100)
    worker = budget(env, ProcessRole.RESEARCH)
    first = worker.reserve("run-a")
    worker.reserve("run-b")
    with pytest.raises(BudgetRefused, match="tokens 200 \\+ 100 > 250"):
        worker.reserve("run-c")
    # run-a measured far less than reserved: its ACTUAL replaces the reservation in the day's total
    with env.db.transaction():
        env.store(ProcessRole.RESEARCH).add_usage(actual_usage(first, UsageTotals(1, 20, 5, 0), at=T))
    worker.reserve("run-c")  # 25 + 100 + 100 <= 250


def test_unknown_measured_tokens_count_the_reservation_never_zero(env):
    policy(env, requests=10, tokens=200, reserve_tokens=100)
    worker = budget(env, ProcessRole.RESEARCH)
    first = worker.reserve("run-a")
    unknown = actual_usage(first, UsageTotals(4, None, None, 2), at=T)
    assert (unknown.requests, unknown.tokens) == (4, 100)
    with env.db.transaction():
        env.store(ProcessRole.RESEARCH).add_usage(unknown)
    worker.reserve("run-b")
    with pytest.raises(BudgetRefused):
        worker.reserve("run-c")


def test_a_usd_cap_without_measured_prices_fails_closed(env):
    from decimal import Decimal

    policy(env, usd=Decimal("0"))
    with pytest.raises(BudgetRefused, match="USD cap"):
        budget(env, ProcessRole.RESEARCH).reserve("run-1")


def test_reservation_is_idempotent_per_run_and_days_are_utc(env):
    policy(env, requests=1)
    clock = ReplayClock(datetime(2026, 1, 9, 23, 59, tzinfo=UTC))
    worker = budget(env, ProcessRole.RESEARCH, clock)
    assert worker.reserve("run-1") == worker.reserve("run-1")
    clock.advance_by(timedelta(minutes=2))  # a new UTC day has its own cap
    assert worker.reserve("run-2").day == date(2026, 1, 10)


def test_concurrent_reservations_cannot_both_take_the_last_slot(env, pg_database):
    policy(env, requests=1)
    results = []

    def reserve(run_id):
        conn = open_operational_pg(pg_database)
        try:
            e = Env.__new__(Env)
            e.conn, e.db, e.clock, e.accounts = conn, PostgresDatabase(conn), env.clock, env.accounts
            results.append(budget(e, ProcessRole.RESEARCH).reserve(run_id))
        except BudgetRefused:
            results.append(None)
        finally:
            conn.close()

    threads = [threading.Thread(target=reserve, args=(f"run-{i}",)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r is None for r in results) == [False, True]


@pytest.mark.parametrize("role", [Role.TRADER, Role.VIEWER])
def test_only_a_current_admin_sets_the_policy(env, role):
    env.accounts.add_operator("someone", role, by=OWNER, reason="test role")
    caps = {"daily_requests": 3, "daily_tokens": 300, "reserve_requests": 1, "reserve_tokens": 100, "reason": "x"}
    with pytest.raises(NotAuthorized):
        set_policy(env, "someone", **caps)
    env.accounts.add_operator("admin2", Role.ADMIN, by=OWNER, reason="second admin")
    env.accounts.deactivate_operator("admin2", by=OWNER, reason="left")
    with pytest.raises(NotAuthorized):
        set_policy(env, "admin2", **caps)
    assert env.store(ProcessRole.CORE).latest_policy() is None


def test_policies_are_versioned_and_audited(env):
    first, second = policy(env), policy(env, requests=5)
    assert (first.version, second.version, second.daily_requests) == (1, 2, 5)
    assert env.db.fetchone("SELECT count(*) FROM audit_events WHERE action='research.budget_policy'")[0] == 2
