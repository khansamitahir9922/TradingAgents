"""Which broker adapters exist, and for which accounts: an allowlist (D23; docs/tasks/M4-03.md rule 1).

M4-03 knew no adapter (tests build the worker with a test-only double). M4-06
adds `simulated`, for RESEARCH accounts only (D23). M7 adds the paper adapter.
No path here loads secrets: the entry point passes in what an adapter needs.
"""

from investment_engine.policy.accounts import AccountKind


class BrokerUnavailable(RuntimeError):
    """No adapter of this kind is available for this account kind."""


KINDS: dict[str, frozenset[AccountKind]] = {"simulated": frozenset({AccountKind.RESEARCH})}  # kind -> who it serves


def check_available(kind: str, *, account_kind: AccountKind) -> None:
    """Refuse an unknown kind, or one that may not serve this account kind (checked before anything opens)."""
    allowed = KINDS.get(kind)
    if allowed is None:
        raise BrokerUnavailable(f"no broker adapter {kind!r} is available yet (M4-03 has none; the simulator "
                                "arrives in M4-06)")
    if AccountKind(account_kind) not in allowed:
        raise BrokerUnavailable(f"the {kind} broker serves only {sorted(k.value for k in allowed)} accounts")


def build_broker(kind: str, *, account_kind: AccountKind, **deps):
    """`simulated` needs db, knowledge and calendar (optionally source, and account_id to serve one account
    only, B9); it holds no credentials."""
    check_available(kind, account_kind=account_kind)
    from investment_engine.execution.simulated_broker import SimulatedBroker, load_fee_schedule

    return SimulatedBroker(deps["db"], knowledge=deps["knowledge"], calendar=deps["calendar"],
                           source=deps.get("source", "yfinance"), fees=load_fee_schedule(),
                           account_id=deps.get("account_id"))


def build_gate_reads(stores, orders, *, knowledge, calendar, fingerprints, accounting=None):
    """The gate's read provider, for a composer outside this package (the offline harness, M4-13) that may import
    only this factory, the worker, the port and the simulator (M4-03 layering)."""
    from investment_engine.execution.reads import StoreGateReads

    return StoreGateReads(stores, orders, knowledge=knowledge, calendar=calendar, fingerprints=fingerprints,
                           accounting=accounting)


__all__ = ["KINDS", "BrokerUnavailable", "build_broker", "build_gate_reads", "check_available"]
