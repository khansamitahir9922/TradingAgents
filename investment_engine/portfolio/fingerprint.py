"""The economic fingerprint of an account: cash, whole-share positions and open-order reservations
(docs/tasks/M4-02.md; Law 13 "no position change since"; Codex M4 review B4).

It deliberately leaves out valuation, `as_of`, peak and provenance, so an
unchanged portfolio has the same fingerprint at any time and at any price.
The proposal's fingerprint is pinned on the order at conversion, and the
Pre-Execution Gate compares it with the fingerprint at submission (M4-05).
The order being gated didn't exist when its intent was proposed, so the
provider excludes it at the gate: both sides leave it out.

`DeclaredFingerprints` reads the declared start only, which is exact until
fills exist; M4-09 replaces it with the provisional projection.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from investment_engine.lineage.records import canonical_json, register
from investment_engine.oms.intents import Side
from investment_engine.portfolio.reference import Unavailable


@dataclass(frozen=True)
class Reservation:
    """What one open order holds back (D30): cash for a BUY, shares for a SELL."""

    order_id: str
    instrument_id: str
    side: Side
    remaining: Decimal  # whole shares not yet filled
    cash: Decimal  # remaining x limit + fee for a BUY; 0 for a SELL

    def __post_init__(self) -> None:
        object.__setattr__(self, "side", Side(self.side))


register(Reservation)


def economic_fingerprint(*, cash: Decimal, positions, reservations=()) -> str:
    """ "pfp-" + SHA-256 of the canonical economic content, in a fixed order."""
    content = {
        "cash": Decimal(cash),
        "positions": sorted((str(i), Decimal(q)) for i, q in positions if Decimal(q) != 0),
        "reservations": sorted((r.order_id, r.instrument_id, r.side.value, r.remaining, r.cash) for r in reservations),
    }
    return "pfp-" + hashlib.sha256(canonical_json(content).encode()).hexdigest()


def fingerprint_of(snapshot) -> str:
    """The fingerprint a proposal was decided on: its snapshot's cash, positions and (from M4-09) reservations."""
    reservations = getattr(snapshot, "reservations", None) or ()
    return economic_fingerprint(cash=snapshot.cash, positions=[(p.instrument_id, p.quantity) for p in snapshot.positions],
                                reservations=reservations)


class FingerprintProvider(Protocol):
    def at(self, account_id: str, at: datetime, *, excluding_order: str | None) -> str | Unavailable: ...


class DeclaredFingerprints:
    """The declared start: exact while the account has no fills (M3 behaviour); replaced in M4-09."""

    def __init__(self, snapshots) -> None:
        self._snapshots = snapshots

    def at(self, account_id: str, at: datetime, *, excluding_order: str | None) -> str | Unavailable:
        try:
            start = self._snapshots.starting_state(account_id)
        except (KeyError, LookupError) as exc:
            return Unavailable(f"no declared start for {account_id}: {exc}")
        return economic_fingerprint(cash=start.cash, positions=start.positions)


__all__ = ["DeclaredFingerprints", "FingerprintProvider", "Reservation", "economic_fingerprint", "fingerprint_of"]
