"""Test-only: run the real worker or Core code as OS processes, with fault points (docs/tasks/M4-08.md rule 5;
M4-12).

Production modules contain no fault hooks. This module, run as a child process with
`python -m tests.engine.process_harness <spec.json>`, builds the unchanged role objects and patches one named
function inside the child so that, at the chosen point, it writes a marker file and blocks. The parent waits for
the marker and calls `Popen.kill()` (TerminateProcess on Windows): a real crash, never a graceful stop.

Roles:
- "worker": recover() then one step(), with the real simulated broker over the test market store;
- "core": a CoreEngine: republish, convert the account's approved intents at the given replay time, publish.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parents[2]

FAULTS = {
    # worker
    "before_submit": ("investment_engine.execution.simulated_broker", "SimulatedBroker", "submit", "before"),
    "after_submit": ("investment_engine.execution.simulated_broker", "SimulatedBroker", "submit", "after"),
    "mid_ingest": ("investment_engine.events.outbox", "Outbox", "add", "fill_event"),
    "cancel_before_call": ("investment_engine.execution.simulated_broker", "SimulatedBroker", "cancel", "before"),
    "cancel_after_accept": ("investment_engine.execution.simulated_broker", "SimulatedBroker", "cancel", "after"),
    # core
    "core_before_conversion": ("investment_engine.oms.order_store", "OrderStore", "create", "before"),
    "core_after_conversion": ("investment_engine.events.outbox", "Outbox", "publish_pending", "pending"),
    # M4-12: behaviours rather than kill points (the child runs to completion or fails)
    "raise_timeout": ("investment_engine.execution.simulated_broker", "SimulatedBroker", "submit", "timeout"),
    "drop_connection": ("investment_engine.execution.ingest", None, "ingest", "drop"),
}
BEHAVIOURS = ("raise_timeout", "drop_connection")


def _block(marker: str) -> None:
    Path(marker).write_text("reached", encoding="utf-8")
    while True:  # the parent kills us here
        time.sleep(1)


def _install(fault: str, marker: str) -> None:
    import importlib

    module, cls, name, when = FAULTS[fault]
    if when == "drop":  # the client side drops its connection in the middle of a step (M4-08 rule 6)
        import investment_engine.execution.worker as worker_module

        real_ingest = worker_module.ingest

        def dropping(*, broker, orders, clock):
            orders._db.connection.close()
            return real_ingest(broker=broker, orders=orders, clock=clock)

        worker_module.ingest = dropping
        return
    owner = getattr(importlib.import_module(module), cls)
    real = getattr(owner, name)

    def patched(self, *args, **kwargs):
        if when == "timeout":  # the broker records the order, then the answer is lost
            from investment_engine.execution.broker_port import BrokerTimeout

            real(self, *args, **kwargs)
            raise BrokerTimeout("simulated: the answer was lost")
        if when == "before":
            _block(marker)
        if when == "fill_event" and args and getattr(args[0], "event_type", "") == "order.fill_recorded":
            _block(marker)  # inside the fill's transaction, before its commit
        if when == "pending" and self.pending() > 0:
            _block(marker)  # converted and committed, not yet published
        result = real(self, *args, **kwargs)
        if when == "after":
            _block(marker)
        return result

    setattr(owner, name, patched)


def child(spec: dict) -> None:
    from investment_engine.clock import ReplayClock
    from investment_engine.events.outbox import Outbox
    from investment_engine.execution.reads import StoreGateReads
    from investment_engine.execution.recovery import recover
    from investment_engine.execution.simulated_broker import SimulatedBroker, load_fee_schedule
    from investment_engine.execution.worker import ExecutionWorker
    from investment_engine.killswitch.flag import KillSwitchReader
    from investment_engine.market.calendar.us_equities import load_us_equities_calendar
    from investment_engine.market.store.reader import MarketDataReader
    from investment_engine.oms.order_states import ProcessRole
    from investment_engine.oms.order_store import OrderStore
    from investment_engine.oms.pipeline import ControlStores
    from investment_engine.portfolio.fingerprint import DeclaredFingerprints
    from investment_engine.portfolio.reference import StoreKnowledge
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg
    from investment_engine.storage.sqlite import SqliteInstrumentRepository

    if spec.get("fault"):
        _install(spec["fault"], spec["marker"])
    clock = ReplayClock(datetime.fromisoformat(spec["at"]))
    conn = open_operational_pg(os.environ["IE_HARNESS_DSN"])
    db = PostgresDatabase(conn)
    stores = ControlStores.open(db, clock, instruments=SqliteInstrumentRepository(db))
    calendar = load_us_equities_calendar()
    if spec["role"] == "cancel":  # a Core-side cancel command, as the Admin CLI records it
        from investment_engine.oms.conversion import request_cancel

        outbox = Outbox(db, writer=ProcessRole.CORE, clock=clock)
        orders = OrderStore(db, role=ProcessRole.CORE, audit=stores.audit, outbox=outbox, clock=clock)
        try:
            request_cancel(spec["order_id"], operator_id="owner", reason="fault test",
                           command_at=datetime.fromisoformat(spec["command_at"]), stores=stores, orders=orders)
        except ValueError:
            print("nothing to cancel")
    elif spec["role"] == "worker":
        knowledge = StoreKnowledge(MarketDataReader(Path(spec["market"])), calendar)
        broker = SimulatedBroker(db, knowledge=knowledge, calendar=calendar, source="yfinance",
                                 fees=load_fee_schedule())
        worker = ExecutionWorker(db, clock=clock, broker=broker, kill_switch=KillSwitchReader(Path(spec["flag"])))
        worker.reads = StoreGateReads(stores, worker.orders, knowledge=knowledge, calendar=calendar,
                                      fingerprints=DeclaredFingerprints(stores.snapshots))
        recover(worker)
        worker.step()
    else:  # the unchanged Core role object (Codex M4 review B12): republish (G4), convert at replay time, publish
        from investment_engine.core.engine import CoreEngine

        engine = CoreEngine(stores, clock=clock)
        engine.outbox.publish_pending()
        engine.convert(spec["account"], at=clock.now())
        engine.publish_and_consume()
    conn.close()
    print("child done")


def start(spec: dict, *, dsn: str, tmp: Path):
    """Start a child without waiting (for concurrent children); returns the Popen."""
    path = tmp / f"spec-{time.monotonic_ns()}.json"
    path.write_text(json.dumps({**spec, "marker": str(tmp / "unused")}), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT), "IE_HARNESS_DSN": dsn}
    return subprocess.Popen([sys.executable, "-m", "tests.engine.process_harness", str(path)], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run(spec: dict, *, dsn: str, tmp: Path, timeout: float = 120):
    """Run a child to completion, or, with a fault, until it reaches the fault point; then kill it.
    Returns the completed process, or None when it was killed at the fault."""
    spec = dict(spec)
    marker = tmp / f"marker-{time.monotonic_ns()}"
    spec["marker"] = str(marker)
    path = tmp / f"spec-{time.monotonic_ns()}.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT), "IE_HARNESS_DSN": dsn}
    process = subprocess.Popen([sys.executable, "-m", "tests.engine.process_harness", str(path)], cwd=ROOT, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if not spec.get("fault") or spec["fault"] in BEHAVIOURS:
        out, err = process.communicate(timeout=timeout)
        if process.returncode != 0 and not spec.get("expect_failure"):
            raise RuntimeError(f"child failed: {err[-2000:]}")
        return process
    deadline = time.monotonic() + timeout
    while not marker.exists():
        if process.poll() is not None:
            raise RuntimeError(f"child ended before its fault point: {process.stderr.read()[-2000:]}")
        if time.monotonic() > deadline:
            process.kill()
            raise TimeoutError("the fault point was never reached")
        time.sleep(0.05)
    process.kill()  # a hard crash at the fault point
    process.communicate(timeout=60)
    return None


if __name__ == "__main__":
    child(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
