"""`python -m investment_engine.execution run --broker KIND`: the Execution Worker process (docs/tasks/M4-03.md).

The only place that reads the worker's secrets file (D32). The broker comes
from the factory's allowlist; with none available the worker refuses to start
and says why, before touching the database. SIGINT and SIGTERM (CTRL_BREAK on
Windows, for a process started in its own process group) finish the current
step and exit; a crash at any point is safe because every write is a
transaction (rule 6). A lost database connection is rebuilt in the running loop,
which recovers before it resumes (M4-08; Codex M4 review B4). Output is plain ASCII and never shows a secret or the DSN.
"""

import argparse
import contextlib
import signal
import sys
from decimal import Decimal


def main(argv: list[str] | None = None) -> int:
    from investment_engine import config
    from investment_engine.execution.factory import BrokerUnavailable, build_broker, check_available
    from investment_engine.execution.secrets import SecretsFileError, load_worker_secrets
    from investment_engine.policy.accounts import AccountKind

    parser = argparse.ArgumentParser(prog="python -m investment_engine.execution")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the Execution Worker")
    run.add_argument("--broker", required=True, help="the broker adapter (an allowlisted kind)")
    run.add_argument("--poll", default="2", help="seconds between steps in live mode (D26)")
    run.add_argument("--once", action="store_true", help="one step, then exit")
    args = parser.parse_args(argv)

    try:
        secrets = load_worker_secrets(config.worker_secrets_path())
    except SecretsFileError as exc:
        print(f"Execution Worker not started: {exc}")
        return 2
    try:
        check_available(args.broker, account_kind=AccountKind.RESEARCH)
    except BrokerUnavailable as exc:
        print(f"Execution Worker not started: {exc}")
        return 2

    from investment_engine.clock import LiveClock
    from investment_engine.execution.worker import ExecutionWorker
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg

    stopping = []

    def stop(*_):
        stopping.append(True)

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)
    from investment_engine.execution.reads import StoreGateReads
    from investment_engine.killswitch.flag import FLAG_FILE, KillSwitchReader
    from investment_engine.market.calendar.us_equities import load_us_equities_calendar
    from investment_engine.market.store.reader import MarketDataReader
    from investment_engine.oms.pipeline import ControlStores
    from investment_engine.portfolio.provisional import ProvisionalFingerprints
    from investment_engine.portfolio.reference import StoreKnowledge
    from investment_engine.storage.sqlite import SqliteInstrumentRepository

    clock, calendar = LiveClock(), load_us_equities_calendar()
    knowledge = StoreKnowledge(MarketDataReader(config.market_store_dir()), calendar)
    opened = []

    def build() -> ExecutionWorker:
        """The worker and its broker, each on a new connection: at start-up, and again after a lost connection
        (Codex M4 review B4). The broker never shares the worker's connection (B5)."""
        for old in opened:
            with contextlib.suppress(Exception):  # already gone with the lost connection
                old.close()
        opened.clear()
        dsn = config.operational_db_dsn()
        opened.extend([open_operational_pg(dsn), open_operational_pg(dsn)])
        db = PostgresDatabase(opened[0])
        broker = build_broker(args.broker, account_kind=AccountKind.RESEARCH, db=PostgresDatabase(opened[1]),
                              clock=clock, secrets=secrets, knowledge=knowledge, calendar=calendar)
        worker = ExecutionWorker(db, clock=clock, broker=broker,
                                 kill_switch=KillSwitchReader(config.control_dir() / FLAG_FILE))
        stores = ControlStores.open(db, clock, instruments=SqliteInstrumentRepository(db))
        # No established action coverage is configured for live mode, so any holding makes the projection, and
        # with it the gate's `positions` check, unavailable: fail closed (Law 9; D22 means no PAPER trading in M4).
        worker.reads = StoreGateReads(stores, worker.orders, knowledge=knowledge, calendar=calendar,
                                      fingerprints=ProvisionalFingerprints(stores.snapshots, worker.orders,
                                                                           knowledge=knowledge, calendar=calendar,
                                                                           coverage=None))
        return worker

    try:
        worker = build()
        if args.once:
            from investment_engine.execution.recovery import recover

            recover(worker)
            report = worker.step()
            print(f"Execution Worker: one step done; published {report.published} events.")
        else:
            print("Execution Worker running; stop with Ctrl+C.")
            worker.run(poll_seconds=Decimal(args.poll), stop=lambda: bool(stopping), reconnect=build)
            print("Execution Worker stopped.")
    finally:
        for conn in opened:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
