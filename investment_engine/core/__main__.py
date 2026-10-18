"""`python -m investment_engine.core run`: the Core Engine process (docs/tasks/M4-03.md).

It publishes what an earlier run left unpublished before anything else (G4),
then steps until stopped. It reads no secrets file. Output is plain ASCII and
never shows the DSN.
"""

import argparse
import signal
import sys
import time


def main(argv: list[str] | None = None) -> int:
    from investment_engine import config
    from investment_engine.clock import LiveClock
    from investment_engine.core.engine import CoreEngine
    from investment_engine.oms.pipeline import ControlStores
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg
    from investment_engine.storage.sqlite import SqliteInstrumentRepository

    parser = argparse.ArgumentParser(prog="python -m investment_engine.core")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the Core Engine loop")
    run.add_argument("--poll", default="2", help="seconds between steps")
    run.add_argument("--once", action="store_true", help="one step, then exit")
    args = parser.parse_args(argv)

    stopping = []
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stopping.append(True))
    conn = open_operational_pg(config.operational_db_dsn())
    try:
        clock = LiveClock()
        db = PostgresDatabase(conn)
        engine = CoreEngine(ControlStores.open(db, clock, instruments=SqliteInstrumentRepository(db)), clock=clock)
        recovered = engine.outbox.publish_pending()
        if args.once:
            report = engine.step()
            print(f"Core Engine: one step done; republished {recovered}, converted {report.converted}, "
                  f"published {report.published}.")
            return 0
        print("Core Engine running; stop with Ctrl+C.")
        while not stopping:
            engine.step()
            deadline = time.monotonic() + float(args.poll)
            while not stopping and time.monotonic() < deadline:
                time.sleep(0.05)
        print("Core Engine stopped.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
