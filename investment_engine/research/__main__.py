"""`python -m investment_engine.research run`: the Research Worker process (M6-07; D48).

The only place that reads `research_worker.env`. Startup is refused, before the
database is touched, when the file is missing, when an LLM key is in the
inherited environment, or when broker credentials are visible. SIGINT/SIGTERM
finish the current step and exit. Output is plain ASCII and never shows a secret
or the DSN.
"""

import argparse
import contextlib
import os
import signal
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal


def _code_version() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False)
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else "unversioned"
    except (OSError, subprocess.SubprocessError):
        return "unversioned"


def main(argv: list[str] | None = None) -> int:
    from investment_engine import config
    from investment_engine.research.secrets import (
        ResearchSecretsError,
        check_environment,
        install,
        load_research_secrets,
    )

    parser = argparse.ArgumentParser(prog="python -m investment_engine.research")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the Research Worker")
    run.add_argument("--poll", default="30", help="seconds between steps")
    run.add_argument("--deadline-minutes", default="30", help="per-run deadline")
    run.add_argument("--once", action="store_true", help="one step, then exit")
    args = parser.parse_args(argv)

    try:
        check_environment(os.environ, execution_secrets=config.worker_secrets_path())
        secrets = load_research_secrets(config.research_worker_secrets_path())
    except ResearchSecretsError as exc:
        print(f"Research Worker not started: {exc}")
        return 2
    install(secrets)

    from investment_engine.clock import LiveClock
    from investment_engine.market.calendar.us_equities import load_us_equities_calendar
    from investment_engine.research.adapter import TradingAgentsAdapter
    from investment_engine.research.worker import ResearchWorker
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg

    stopping = []
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stopping.append(True))
    clock, calendar, version = LiveClock(), load_us_equities_calendar(), _code_version()
    port = TradingAgentsAdapter(work_dir=config.data_dir() / "research", code_version=version,
                                secrets=tuple(secrets.values()))
    deadline = timedelta(minutes=float(args.deadline_minutes))
    opened = []

    def build() -> ResearchWorker:
        for old in opened:
            with contextlib.suppress(Exception):
                old.close()
        opened.clear()
        opened.append(open_operational_pg(config.operational_db_dsn()))
        return ResearchWorker(PostgresDatabase(opened[0]), worker_id=f"research-{os.getpid()}", clock=clock,
                              port=port, calendar=calendar, deadline=deadline, code_version=version)

    try:
        worker = build()
        if args.once:
            report = worker.step()
            print(f"Research Worker: one step done; claimed {report.claimed}, succeeded {report.succeeded}, "
                  f"failed {report.failed}, budget-refused {report.refused}.")
        else:
            print("Research Worker running; stop with Ctrl+C.")
            worker.run(poll_seconds=Decimal(args.poll), stop=lambda: bool(stopping), reconnect=build)
            print("Research Worker stopped.")
    finally:
        for conn in opened:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
