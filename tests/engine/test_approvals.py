"""Level 1 approve and decline (docs/tasks/M3-13.md)."""

import threading
from dataclasses import replace
from datetime import timedelta

import pytest

from investment_engine.oms.approvals import ApprovalRefused, approve, decline
from investment_engine.oms.intents import IntentState
from investment_engine.oms.pipeline import expire_due
from investment_engine.policy.accounts import AccountKind, NotAuthorized, Role
from investment_engine.risk.limits import load_limits_file
from tests.engine.test_intent_pipeline import (
    CAL,
    DAY,
    LIVE,
    NOW,
    OWNER,
    PROPOSED,
    SESSIONS,
    Env,
    t_of,
    view_for,
    write_bars,
)

pytestmark = pytest.mark.postgres


def operators(env):
    env.stores.accounts.add_operator("trader", Role.TRADER, by=OWNER, reason="t")
    env.stores.accounts.add_operator("viewer", Role.VIEWER, by=OWNER, reason="v")
    env.stores.accounts.add_operator("gone", Role.TRADER, by=OWNER, reason="g")
    env.stores.accounts.deactivate_operator("gone", by=OWNER, reason="left")


@pytest.fixture
def env(pg_database, tmp_path):
    e = Env(pg_database, tmp_path / "market")
    operators(e)
    e.account("R1")
    yield e
    e.close()


def waiting(env, day=DAY, tag="", account="R1"):
    record = env.propose(account, view_for(env.stores, env.reader, day, tag=tag))
    assert record.outcome.value == "AWAITING_APPROVAL", record
    return env.stores.intents.get(record.intent_id)


def act(env, stored, *, operator="trader", at=None, version=None, fn=approve, stores=None, **kw):
    at = at or stored.intent.created_at + timedelta(hours=1)
    if fn is approve:
        kw.setdefault("calendar", CAL)
    return fn(stored.intent.intent_id, version or stored.intent.version, operator_id=operator, at=at,
              command_at=env.clock.now(), stores=stores or env.stores, **kw)


def events(env, stored, action):
    return [e for e in env.stores.audit.for_target("intent", stored.intent.intent_id) if e.action == action]


@pytest.mark.unit
@pytest.mark.parametrize("operator", ["trader", "owner"])
def test_a_trader_or_admin_approves_and_the_expiry_comes_from_the_calendar(env, operator):
    stored = waiting(env)
    approved = act(env, stored, operator=operator)
    target = stored.intent.target_session
    assert approved.state is IntentState.APPROVED and approved.approved_by == operator
    assert approved.approved_at == stored.intent.created_at + timedelta(hours=1)  # business (replay) time
    assert approved.approval_recorded_at == NOW  # the real command time
    assert approved.approval_expires_at == CAL.session(target).close
    (event,) = events(env, stored, "intent.approved")
    assert event.at == NOW and event.business_at == approved.approved_at and event.actor.actor_id == operator


@pytest.mark.unit
def test_a_half_day_close_sets_the_expiry(env):
    half = next(d for d in SESSIONS if CAL.session(CAL.next_session(d).date).close.hour < 20)
    stored = waiting(env, half, tag="half")
    approved = act(env, stored)
    close = CAL.session(stored.intent.target_session).close
    assert approved.approval_expires_at == close and close.hour == 17  # 13:00 exchange time


@pytest.mark.unit
def test_the_view_validity_caps_the_expiry(env):
    view = view_for(env.stores, env.reader, DAY, tag="short")
    short = CAL.session(CAL.next_session(DAY).date).open + timedelta(hours=2)
    record = env.propose("R1", replace(view, valid_until=short))
    stored = env.stores.intents.get(record.intent_id)
    assert act(env, stored).approval_expires_at == short  # D10


@pytest.mark.unit
def test_refusals_change_nothing_and_each_writes_one_refusal_event(env):
    stored = waiting(env)
    deadline = stored.approval_deadline
    cases = [
        ({"version": 2}, ApprovalRefused, "latest"),
        ({"at": deadline}, ApprovalRefused, "deadline"),  # exactly at the deadline is too late
        ({"at": deadline + timedelta(minutes=1)}, ApprovalRefused, "deadline"),
        ({"at": stored.intent.created_at - timedelta(seconds=1)}, ApprovalRefused, "earlier than the proposal"),
        ({"operator": "viewer"}, NotAuthorized, "may not"),
        ({"operator": "gone"}, NotAuthorized, "active"),
        ({"operator": "nobody"}, NotAuthorized, "registered"),
    ]
    for k, (kw, error, message) in enumerate(cases):
        env.clock.advance_by(timedelta(seconds=1))  # each refusal is its own command
        with pytest.raises(error, match=message):
            act(env, stored, **kw)
        refusals = events(env, stored, "intent.approve_refused")
        assert len(refusals) == k + 1, kw  # exactly one refusal event per attempt
        assert message in refusals[-1].reason and refusals[-1].at == env.clock.now()
        assert env.stores.intents.get(stored.intent.intent_id) == stored  # nothing changed


@pytest.mark.unit
def test_an_intent_no_longer_awaiting_approval_is_refused(env):
    stored = waiting(env)
    act(env, stored)
    env.clock.advance_by(timedelta(seconds=1))
    with pytest.raises(ApprovalRefused, match="APPROVED, not AWAITING_APPROVAL"):
        act(env, stored)
    declined = waiting(env, SESSIONS[61], tag="d")
    act(env, declined, fn=decline, reason="no")
    env.clock.advance_by(timedelta(seconds=1))
    with pytest.raises(ApprovalRefused, match="DECLINED, not AWAITING_APPROVAL"):
        act(env, declined)
    assert len(events(env, stored, "intent.approve_refused")) == 1


@pytest.mark.unit
def test_the_old_version_of_a_reduced_intent_is_refused(pg_database, tmp_path):
    env = Env(pg_database, tmp_path / "market", reader=write_bars(tmp_path / "thin", SESSIONS, volume="1000"))
    try:
        operators(env)
        env.account("R1")
        record = env.propose("R1", view_for(env.stores, env.reader, DAY))
        assert record.versions == (1, 2)
        stored = env.stores.intents.get(record.intent_id)
        with pytest.raises(ApprovalRefused, match="not the latest"):
            act(env, stored, version=1)
        assert act(env, stored, version=2).state is IntentState.APPROVED
    finally:
        env.close()


@pytest.mark.unit
def test_an_autonomy_change_even_back_to_level_1_refuses(env):
    stored = waiting(env)
    later = stored.intent.created_at + timedelta(minutes=10)
    env.stores.accounts.set_autonomy("R1", 2, by=OWNER, reason="up", effective_at=later)
    env.stores.accounts.set_autonomy("R1", 1, by=OWNER, reason="back", effective_at=later)  # 1 -> 2 -> 1
    setting = env.stores.accounts.autonomy_at("R1", later)
    assert setting.level == 1 and setting.reason == "back"  # equal effective times: the later sequence wins
    with pytest.raises(ApprovalRefused, match="autonomy changed since proposal"):
        act(env, stored, at=later + timedelta(minutes=1))
    assert act(env, stored, at=later - timedelta(minutes=1)).state is IntentState.APPROVED  # before the change


@pytest.mark.unit
@pytest.mark.parametrize("change", ["risk", "policy", "halt"])
def test_new_limits_rules_or_a_halt_refuse_a_buy(env, change):
    stored = waiting(env)
    later = stored.intent.created_at + timedelta(minutes=10)
    risk, policy = load_limits_file(PROPOSED)
    if change == "risk":
        env.stores.limits.publish_risk("R1", risk, by=OWNER, reason="v2", effective_at=later)
    elif change == "policy":
        env.stores.limits.publish_policy("R1", policy, by=OWNER, reason="v2", effective_at=later)
    else:
        env.stores.limits.set_halt("R1", at=later, limits_version=stored.intent.risk_version, reason="drawdown")
    with pytest.raises(ApprovalRefused, match="controls changed since proposal; propose again"):
        act(env, stored, at=later + timedelta(minutes=1))
    assert env.stores.intents.get(stored.intent.intent_id).state is IntentState.AWAITING_APPROVAL


@pytest.mark.unit
def test_a_paper_account_acts_only_at_live_time(pg_database, tmp_path):
    live = t_of(DAY)
    env = Env(pg_database, tmp_path / "market", now=live)
    try:
        operators(env)
        env.account("P1", kind=AccountKind.PAPER)
        record = env.propose("P1", view_for(env.stores, env.reader, DAY), at=LIVE)  # PAPER: no promotion yet
        stored = env.stores.intents.get(record.intent_id)
        with pytest.raises(ApprovalRefused, match="live time only"):
            act(env, stored, at=live - timedelta(minutes=1))
        with pytest.raises(ApprovalRefused, match="not AWAITING_APPROVAL"):  # at live time it gets this far
            act(env, stored, at=live)
        (first, second) = events(env, stored, "intent.approve_refused")
        assert first.business_at is None and second.business_at is None  # PAPER audit has no replay time
    finally:
        env.close()


@pytest.mark.unit
def test_decline_needs_a_reason_and_is_audited(env):
    stored = waiting(env)
    with pytest.raises(ApprovalRefused, match="reason"):
        act(env, stored, fn=decline, reason=" ")
    assert len(events(env, stored, "intent.decline_refused")) == 1
    env.clock.advance_by(timedelta(seconds=1))
    declined = act(env, stored, fn=decline, reason="not now")
    assert declined.state is IntentState.DECLINED
    (event,) = events(env, stored, "intent.declined")
    assert event.reason == "not now" and event.actor.actor_id == "trader"
    with pytest.raises(NotAuthorized):
        act(env, waiting(env, SESSIONS[61], tag="v"), fn=decline, reason="no", operator="viewer")


@pytest.mark.unit
def test_authorization_is_at_the_command_time_whatever_the_replay_time(env):
    stored = waiting(env)
    early = stored.intent.created_at + timedelta(minutes=1)  # 2024: years before any operator existed
    assert act(env, stored, at=early).state is IntentState.APPROVED  # today's trader approves in replay
    other = waiting(env, SESSIONS[61], tag="y")
    with pytest.raises(NotAuthorized, match="active"):
        act(env, other, operator="gone", at=other.intent.created_at + timedelta(minutes=1))
    assert t_of(DAY) < NOW


# ---------------------------------------------------------------- races on PostgreSQL


def gated(stores, name, barrier, order):
    """Both racers wait at `barrier` just before taking the account-control lock (so an approval has already
    read the intent it acts on), then `name` is noted in `order` once the lock is held. The lock is held until
    commit, so `order` is the commit order."""
    real, first = stores.db.lock, [True]

    def lock(*names):
        gate = first[0] and any(n.startswith("account-control|") for n in names)
        if gate:
            first[0] = False
            barrier.wait()
        real(*names)
        if gate:
            order.append(name)

    stores.db.lock = lock
    return stores


def race(env, one, two):
    """Run two callables on their own connections, gated at the lock; returns their results and the order."""
    barrier, results, order = threading.Barrier(2), {}, []

    def run(name, fn):
        stores = gated(env.connect(), name, barrier, order)
        try:
            results[name] = fn(stores)
        except Exception as exc:  # the outcome under test
            results[name] = exc
        finally:
            stores.db.connection.close()

    threads = [threading.Thread(target=run, args=item) for item in (one, two)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert sorted(order) == sorted(name for name, _ in (one, two)), order
    return results, order


@pytest.mark.unit
def test_approve_and_expire_at_the_deadline_have_one_winner(env):
    for k in range(10):
        stored = waiting(env, SESSIONS[70 + k], tag=f"r{k}")
        just_before = stored.approval_deadline - timedelta(microseconds=1)
        results, _ = race(env, ("approve", lambda s, st=stored, t=just_before: approve(
                           st.intent.intent_id, 1, operator_id="trader", at=t, command_at=NOW, stores=s,
                           calendar=CAL)),
                       ("expire", lambda s, st=stored: expire_due("R1", at=st.approval_deadline, stores=s)))
        final = env.stores.intents.get(stored.intent.intent_id).state
        if isinstance(results["approve"], ApprovalRefused):
            assert "intent changed meanwhile" in str(results["approve"]) and len(results["expire"]) == 1
            assert final is IntentState.EXPIRED
        else:
            assert results["approve"].state is IntentState.APPROVED and results["expire"] == []
            assert final is IntentState.APPROVED


@pytest.mark.unit
def test_two_approvals_have_one_winner_and_the_other_reports_the_stale_write(env):
    for k in range(10):
        stored = waiting(env, SESSIONS[90 + k], tag=f"t{k}")
        at = stored.intent.created_at + timedelta(minutes=1)

        def approving(operator, st=stored, t=at):
            return lambda s: approve(st.intent.intent_id, 1, operator_id=operator, at=t, command_at=NOW, stores=s,
                                     calendar=CAL)

        results, order = race(env, ("trader", approving("trader")), ("owner", approving("owner")))
        won = [n for n, r in results.items() if not isinstance(r, Exception)]
        lost = [r for r in results.values() if isinstance(r, Exception)]
        assert len(won) == 1 and len(lost) == 1, results
        assert isinstance(lost[0], ApprovalRefused) and "intent changed meanwhile" in str(lost[0])
        assert won == order[:1] and env.stores.intents.get(stored.intent.intent_id).approved_by == won[0]


@pytest.mark.unit
@pytest.mark.parametrize("change", ["autonomy", "limits"])
def test_an_approval_never_happens_under_a_superseded_setting(env, change):
    risk, _ = load_limits_file(PROPOSED)
    for k in range(50):
        stored = waiting(env, SESSIONS[100 + k], tag=f"{change}{k}")
        at = stored.intent.created_at + timedelta(minutes=1)

        def approving(s, st=stored, t=at):
            return approve(st.intent.intent_id, 1, operator_id="trader", at=t, command_at=NOW, stores=s,
                           calendar=CAL)

        def changing(s, t=at, k=k):
            if change == "autonomy":
                return s.accounts.set_autonomy("R1", 1, by=OWNER, reason=f"re-set {k}", effective_at=t)
            return s.limits.publish_risk("R1", risk, by=OWNER, reason=f"re-publish {k}", effective_at=t)

        results, order = race(env, ("approve", approving), ("change", changing))
        assert not isinstance(results["change"], Exception), results
        state = env.stores.intents.get(stored.intent.intent_id).state
        if order[0] == "change":  # the change committed first: the approval must see it and refuse
            assert isinstance(results["approve"], ApprovalRefused), (k, results)
            assert "changed since proposal" in str(results["approve"])
            assert state is IntentState.AWAITING_APPROVAL
        else:  # the approval committed first, under the setting that was still current
            assert results["approve"].state is IntentState.APPROVED, (k, results)
            assert state is IntentState.APPROVED
