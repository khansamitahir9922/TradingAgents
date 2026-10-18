"""Which broker adapters exist, and for which accounts: an allowlist (D23; docs/tasks/M4-03.md rule 1).

M4-03 knows no production adapter, so every request is refused and the worker
won't start; tests build the worker with a test-only broker double instead.
M4-06 adds `simulated`, for RESEARCH accounts only. M7 adds the paper adapter.
No path here loads secrets: the entry point passes in what an adapter needs.
"""

from investment_engine.policy.accounts import AccountKind


class BrokerUnavailable(RuntimeError):
    """No adapter of this kind is available for this account kind."""


KINDS: dict[str, frozenset[AccountKind]] = {}  # kind -> the account kinds it may serve


def check_available(kind: str, *, account_kind: AccountKind) -> None:
    """Refuse an unknown kind, or one that may not serve this account kind (checked before anything opens)."""
    allowed = KINDS.get(kind)
    if allowed is None:
        raise BrokerUnavailable(f"no broker adapter {kind!r} is available yet (M4-03 has none; the simulator "
                                "arrives in M4-06)")
    if AccountKind(account_kind) not in allowed:
        raise BrokerUnavailable(f"the {kind} broker serves only {sorted(k.value for k in allowed)} accounts")


def build_broker(kind: str, *, account_kind: AccountKind, **deps):
    check_available(kind, account_kind=account_kind)
    raise BrokerUnavailable(f"{kind} is listed but not built")  # replaced when an adapter is wired (M4-06)


__all__ = ["KINDS", "BrokerUnavailable", "build_broker", "check_available"]
