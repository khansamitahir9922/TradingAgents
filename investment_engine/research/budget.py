"""The daily LLM budget (M6-06; D46, D47; C4). It fails closed.

Before a run the worker reserves the policy's per-run allowance under the UTC
day's lock and is refused if the day's total would exceed a cap. After the run,
its measured usage replaces the reservation in that day's total. Unknown token
usage counts the reserved tokens, never zero. A USD cap cannot be enforced
until per-run prices are measured (M6-11), so a policy with one refuses runs.
"""

from __future__ import annotations

from datetime import datetime

from investment_engine.market.availability import check_utc
from investment_engine.research.contracts import BudgetUsage, UsageTotals


class BudgetRefused(Exception):
    """The run must not start; the reason carries the numbers."""


def actual_usage(reservation: BudgetUsage, usage: UsageTotals, *, at: datetime) -> BudgetUsage:
    """A run's measured usage, booked on its reservation's day. Unknown tokens count the reservation."""
    tokens = reservation.tokens if usage.input_tokens is None or usage.output_tokens is None \
        else usage.input_tokens + usage.output_tokens
    return BudgetUsage(reservation.day, reservation.run_id, "ACTUAL", usage.requests, tokens, None, check_utc(at, "at"))


def day_totals(usages) -> tuple[int, int]:
    """(requests, tokens) for one day: each run counts its ACTUAL usage, else its reservation."""
    per_run: dict[str, BudgetUsage] = {}
    for usage in usages:
        if usage.kind == "ACTUAL" or usage.run_id not in per_run:
            per_run[usage.run_id] = usage
    return sum(u.requests for u in per_run.values()), sum(u.tokens for u in per_run.values())


class ResearchBudget:
    """The worker's side of the budget: reserve before a run. Setting the policy is an Admin command on the
    Core side (`research_cli.set_budget`), so this module loads no operator-registry code (B9)."""

    def __init__(self, store, *, clock) -> None:
        self.store, self.clock = store, clock

    def reserve(self, run_id: str) -> BudgetUsage:
        """Reserve one run's allowance for today (UTC), or raise BudgetRefused. Idempotent per run."""
        db = self.store.db
        now = check_utc(self.clock.now(), "now")
        day = now.date()
        with db.transaction():
            db.lock(f"research-budget|{day.isoformat()}")
            usages = self.store.usage_on(day)
            existing = next((u for u in usages if u.run_id == run_id and u.kind == "RESERVED"), None)
            if existing is not None:
                return existing
            policy = self.store.latest_policy()
            if policy is None:
                raise BudgetRefused("no budget policy is set; research is refused (fail closed)")
            if policy.daily_usd is not None:
                raise BudgetRefused("a USD cap is set but per-run prices are not yet measured (M6-11); refused")
            requests, tokens = day_totals(usages)
            if requests + policy.reserve_requests > policy.daily_requests:
                raise BudgetRefused(f"daily budget {day}: requests {requests} + {policy.reserve_requests} > "
                                    f"{policy.daily_requests} (policy v{policy.version})")
            if tokens + policy.reserve_tokens > policy.daily_tokens:
                raise BudgetRefused(f"daily budget {day}: tokens {tokens} + {policy.reserve_tokens} > "
                                    f"{policy.daily_tokens} (policy v{policy.version})")
            return self.store.add_usage(BudgetUsage(day, run_id, "RESERVED", policy.reserve_requests,
                                                    policy.reserve_tokens, None, now))


__all__ = ["BudgetRefused", "ResearchBudget", "actual_usage", "day_totals"]
