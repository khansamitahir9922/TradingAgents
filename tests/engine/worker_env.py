"""Test-only wiring for the Execution Worker over a real converted order (docs/tasks/M4-07.md onwards)."""

from datetime import timedelta

from investment_engine.clock import ReplayClock
from investment_engine.execution.reads import StoreGateReads
from investment_engine.execution.worker import ExecutionWorker
from investment_engine.killswitch.flag import FlagState, KillSwitchReader, encode_flag
from investment_engine.oms.conversion import convert_approved, request_cancel
from investment_engine.oms.order_states import ProcessRole
from investment_engine.portfolio.fingerprint import DeclaredFingerprints
from tests.engine.broker_doubles import ScriptedBroker
from tests.engine.test_conversion import order_store
from tests.engine.test_intent_pipeline import CAL, NOW, Env, view_for


class WorkerEnv(Env):
    def __init__(self, dsn, root, flag_dir):
        super().__init__(dsn, root)
        self.account("R2", level=2)
        self.flag = flag_dir / "trading_enabled.json"
        self.flag.parent.mkdir(parents=True, exist_ok=True)
        self.enable(True)
        self.broker = ScriptedBroker()

    def enable(self, on: bool, sequence: int = 1):
        self.flag.write_text(encode_flag(FlagState(on, sequence, NOW, "owner", True, "test")), encoding="utf-8")

    def approved_view(self, day, tag=""):
        """Propose at Level 2 (APPROVED) without converting: the Core Engine's job in the process tests."""
        view = view_for(self.stores, self.reader, day, tag=tag or str(day))
        self.propose("R2", view)
        return view

    def convert(self, day, tag=""):
        view = view_for(self.stores, self.reader, day, tag=tag or str(day))
        self.propose("R2", view)
        (order,) = convert_approved("R2", at=view.generated_at, stores=self.stores, orders=order_store(self)).converted
        return order, view

    def worker(self, at, *, broker=None):
        """A worker at time `at`. One connection is reused while time moves forward, so long tests don't exhaust
        the server's connection slots."""
        cached = getattr(self, "_worker_stores", None)
        if cached is None or at < cached.clock.now():
            cached = self._worker_stores = self.connect(ReplayClock(at))
        else:
            cached.clock.advance_to(at)
        stores = cached
        worker = ExecutionWorker(stores.db, clock=stores.clock, broker=broker or self.broker,
                                 kill_switch=KillSwitchReader(self.flag))
        worker.reads = StoreGateReads(stores, worker.orders, knowledge=self.knowledge, calendar=CAL,
                                      fingerprints=DeclaredFingerprints(stores.snapshots))
        return worker

    def cancel(self, order, at=None, operator="owner"):
        """A cancel command; operators are checked at the real command time (the live clock), never replay time."""
        return request_cancel(order.order_id, operator_id=operator, reason="test", command_at=self.clock.now(),
                              stores=self.stores, orders=order_store(self))

    def state(self, order):
        return order_store(self, role=ProcessRole.EXECUTION).get(order.order_id)[1]


def pre_open(order, view):
    at = view.generated_at + timedelta(minutes=1)
    assert at < CAL.session(order.target_session).open
    return at


def after_close(order):
    return CAL.session(order.target_session).close + timedelta(minutes=30)
