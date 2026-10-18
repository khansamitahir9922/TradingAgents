"""D26's broker deadline, enforced at the worker's call boundary (Codex M4 review B5; docs/tasks/M4-07.md rule 1).

A broker call that doesn't answer within the deadline counts as timed out: a submit becomes UNKNOWN and is never
resent, a cancel stays SENDING and is retried, a lookup or ingestion is skipped for that step. While the stalled
call is still running, the worker makes no other broker call and gates no new submission, so a connection is never
used concurrently and no order is made UNKNOWN for nothing.
"""

import threading
import time
from datetime import timedelta

import pytest

from investment_engine.execution.broker_port import BROKER_DEADLINE_SECONDS, SubmitResult
from investment_engine.oms.order_states import OrderState as S
from tests.engine.test_intent_pipeline import DAY, SESSIONS
from tests.engine.worker_env import WorkerEnv, after_close, pre_open

pytestmark = pytest.mark.postgres
SHORT = 0.3  # seconds: the tests' deadline, so they don't each wait ten seconds


@pytest.fixture
def env(pg_database, tmp_path):
    e = WorkerEnv(pg_database, tmp_path / "market", tmp_path / "control")
    yield e
    e.close()


def stall(release, answer):
    """A broker method that blocks until `release` is set, then answers."""
    def call(*args, **kwargs):
        release.wait(30)
        return answer(*args, **kwargs)
    return call


@pytest.mark.unit
def test_the_default_deadline_is_d26s_ten_seconds_and_a_late_ack_gives_unknown(env):
    assert BROKER_DEADLINE_SECONDS == 10
    order, view = env.convert(DAY)
    worker = env.worker(pre_open(order, view))

    def late(order, *, at):
        time.sleep(10.2)
        return SubmitResult(True, "late-ack", "answered after the deadline")

    worker.broker.submit = late
    started = time.monotonic()
    assert worker.submit(order.order_id) == "UNKNOWN"
    assert 10 <= time.monotonic() - started < 10.2  # the deadline, not the late answer, ended the wait


@pytest.mark.unit
def test_a_stalled_submit_is_unknown_never_resent_and_blocks_other_calls_until_it_returns(env):
    first, view = env.convert(DAY)
    second, second_view = env.convert(SESSIONS[SESSIONS.index(DAY) + 1], tag="second")
    worker = env.worker(pre_open(first, view))
    worker.deadline_seconds = SHORT
    release, real = threading.Event(), env.broker.submit
    calls = []

    def stalled_once(order, *, at):
        calls.append(order.client_order_id)
        if len(calls) == 1:
            release.wait(30)
        return real(order, at=at)

    env.broker.submit = stalled_once
    assert worker.submit(first.order_id) == "UNKNOWN"
    assert worker.broker_stalled()
    report = worker.step()  # the stalled call is still running: nothing goes to the broker
    assert report.submitted == 0 and env.state(second).state is S.NEW and calls == [first.client_order_id]
    release.set()
    deadline = time.monotonic() + 10
    while worker.broker_stalled() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not worker.broker_stalled()
    worker.clock.advance_to(pre_open(second, second_view))
    worker.step()
    assert env.state(second).state is S.SUBMITTED
    assert calls == [first.client_order_id, second.client_order_id]  # the first is never resent
    # Its late answer was discarded; the lookup then found the order at the broker and reconciled it.
    history = [(t.to_state, t.reason) for t in worker.orders.history(first.order_id)]
    assert [s for s, _ in history] == [S.NEW, S.SUBMITTING, S.UNKNOWN, S.SUBMITTED]
    assert history[-1][1] == "the broker reports it open"


@pytest.mark.unit
def test_a_stalled_cancel_stays_sending_and_is_retried_once_the_call_returns(env):
    order, view = env.convert(DAY)
    env.worker(pre_open(order, view)).step()
    t = after_close(order)
    env.cancel(order, t)
    worker = env.worker(t)
    worker.deadline_seconds = SHORT
    release, real = threading.Event(), env.broker.cancel
    env.broker.cancel = stall(release, real)
    worker.step()
    (request,) = list(worker.orders.open_cancels())
    assert request[1].value == "SENDING" and env.state(order).state is S.CANCEL_PENDING
    attempts = env.stores.db.fetchone("SELECT MAX(attempt) FROM cancel_progress")[0]
    worker.step()  # still stalled: no further attempt is recorded, because none is made
    assert env.stores.db.fetchone("SELECT MAX(attempt) FROM cancel_progress")[0] == attempts
    env.broker.cancel = real
    release.set()
    while worker.broker_stalled():
        time.sleep(0.01)
    worker.step()
    assert list(worker.orders.open_cancels())[0][1].value == "SENT"


@pytest.mark.unit
def test_a_stalled_message_read_is_skipped_and_the_step_still_finishes_in_time(env):
    order, view = env.convert(DAY)
    worker = env.worker(pre_open(order, view))
    worker.deadline_seconds = SHORT
    release, real = threading.Event(), env.broker.messages
    env.broker.messages = stall(release, real)
    started = time.monotonic()
    report = worker.step()
    assert time.monotonic() - started < SHORT + 2 and report.ingested == 0
    assert env.state(order).state is S.NEW  # nothing gated while the broker is stalled
    env.broker.messages = real
    release.set()
    while worker.broker_stalled():
        time.sleep(0.01)
    worker.step()
    assert env.state(order).state is S.SUBMITTED


@pytest.mark.unit
def test_a_stalled_lookup_leaves_unknown_and_is_tried_again(env):
    order, view = env.convert(DAY)
    env.broker.timeout_next_submit = True
    env.worker(pre_open(order, view)).step()
    worker = env.worker(after_close(order) + timedelta(minutes=1))
    worker.deadline_seconds = SHORT
    release, real = threading.Event(), env.broker.lookup
    env.broker.lookup = stall(release, real)
    report = worker.step()
    assert report.lookups == 0 and env.state(order).state is S.UNKNOWN
    env.broker.lookup = real
    release.set()
    while worker.broker_stalled():
        time.sleep(0.01)
    assert worker.step().lookups == 1
