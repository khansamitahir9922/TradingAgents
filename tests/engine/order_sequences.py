"""Seeded random sequences for the Part J invariant tests (docs/tasks/M4-11.md; D33). Test-only.

A sequence is fully determined by its seed, so any failure is replayed exactly by re-running that seed.
"""

import random
from datetime import timedelta
from decimal import Decimal

from investment_engine.execution.broker_port import BrokerFill, BrokerMessage

KINDS = ("ACK", "FILL", "FILL", "FILL", "CANCELLED", "EXPIRED", "REJECTED")


def messages(seed: int, client_order_id: str, quantity: Decimal, start) -> list[BrokerMessage]:
    """A random broker message stream for one order: partial fills, a delayed fill after CANCELLED, identical and
    conflicting duplicate fills, reordered acks and repeated messages."""
    rng = random.Random(seed)
    out, filled = [], Decimal(0)
    for n in range(1, rng.randint(1, 7) + 1):
        kind = rng.choice(KINDS)
        at = start + timedelta(minutes=n)
        mid = f"s{seed}-m{n}"
        if kind == "FILL":
            room = max(quantity - filled, Decimal(1))
            q = Decimal(rng.randint(1, int(room)))
            fill = BrokerFill(f"s{seed}-f{n}", q, Decimal(rng.choice(["99.50", "100.00", "100.25"])), Decimal(0),
                              "USD", at, "{}")
            out.append(BrokerMessage(mid, client_order_id, "FILL", at, fill, ""))
            filled += q
            if rng.random() < 0.25:  # the same fill again: identical or conflicting
                again = fill if rng.random() < 0.5 else BrokerFill(fill.broker_fill_id, fill.quantity + 1, fill.price,
                                                                    fill.fee, "USD", at, "{}")
                out.append(BrokerMessage(mid + "-dup", client_order_id, "FILL", at, again, ""))
        else:
            out.append(BrokerMessage(mid, client_order_id, kind, at, None, "random"))
    if rng.random() < 0.3:
        rng.shuffle(out)  # reordering
    if out and rng.random() < 0.3:
        out.append(out[rng.randrange(len(out))])  # a repeated delivery
    return out


def flow_plan(seed: int) -> dict:
    """One order's flow: kill-switch flips, a submit timeout, a cancel, and the market's answer; and, on some
    seeds, the same view proposed for an account whose policy (RP) or risk (RR) rejects it (Codex M4 review B12)."""
    rng = random.Random(seed)
    plan = {"enabled": rng.random() < 0.8, "timeout": rng.random() < 0.2, "cancel": rng.random() < 0.3,
            "answer": rng.choice(["FILL", "FILL", "EXPIRED", "CANCELLED", "none"]), "flip_after": rng.random() < 0.3}
    plan["rejected_on"] = rng.choice([None, None, "RP", "RR"])  # drawn last: the earlier draws are unchanged
    plan["unreadable"] = not plan["enabled"] and rng.random() < 0.5  # off by a bad flag, not a halt
    return plan


def cancel_plan(seed: int) -> dict:
    """A cancel after submission (Codex M4 review B12): a partial fill first or not, the first send timing out or
    a crash before it, and the broker's final answer. Valid timelines only: a pending cancel ends CANCELLED or
    filled (D25; G3 has no CANCEL_PENDING -> EXPIRED), so an expiry is delivered before the cancel is processed."""
    rng = random.Random(10_000 + seed)
    partial = rng.random() < 0.3
    plan = {"partial": partial, "timeout_first": rng.random() < 0.3, "crash_before_send": rng.random() < 0.2,
            "answer": rng.choice(["CANCELLED", "FILL"] if partial else ["CANCELLED", "FILL", "EXPIRED_FIRST"])}
    if plan["answer"] == "EXPIRED_FIRST":  # final before the cancel is processed: nothing is sent to crash in
        plan["crash_before_send"] = plan["timeout_first"] = False
    plan["trading_off"] = rng.random() < 0.5  # the kill switch never blocks a cancel (Law 15)
    return plan
