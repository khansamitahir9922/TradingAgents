"""`python -m investment_engine.core run`: the Core Engine process (docs/tasks/M4-03.md).

It publishes what an earlier run left unpublished before anything else (G4),
then steps until stopped; a lost database connection is rebuilt in the running
loop, which republishes before it resumes (Codex M4 review B4). It reads no secrets file. Output is plain ASCII and
never shows the DSN.
"""

import argparse
import contextlib
import signal
import sys
from decimal import Decimal


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
    clock, opened = LiveClock(), []

    def build() -> CoreEngine:
        """The engine on a new connection: at start-up, and again after a lost connection (Codex M4 review B4)."""
        for old in opened:
            with contextlib.suppress(Exception):  # already gone with the lost connection
                old.close()
        opened.clear()
        opened.append(open_operational_pg(config.operational_db_dsn()))
        db = PostgresDatabase(opened[0])
        return CoreEngine(ControlStores.open(db, clock, instruments=SqliteInstrumentRepository(db)), clock=clock)

    try:
        engine = build()
        if args.once:
            recovered = engine.outbox.publish_pending()
            report = engine.step()
            print(f"Core Engine: one step done; republished {recovered}, converted {report.converted}, "
                  f"published {report.published}.")
            return 0
        print("Core Engine running; stop with Ctrl+C.")
        engine.run(poll_seconds=Decimal(args.poll), stop=lambda: bool(stopping), reconnect=build)
        print("Core Engine stopped.")
    finally:
        for conn in opened:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
