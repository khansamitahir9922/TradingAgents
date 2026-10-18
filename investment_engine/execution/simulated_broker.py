"""The simulated broker: its own state, a causal daily fill model, fees and slippage (Law 20; architecture
Part K M4; D19, D25, D26; docs/tasks/M4-06.md).

Its tables (schema `sim_broker`) are written only here; the Core Engine and
the reporter never read them. They see only what the worker records.

Four times are kept apart:
- **submitted_at**: the broker's receipt. Orders must rest from the open, so a
  submit at or after the target session's open is REJECTED.
- **executed_at**: the open for an opening fill; the session close, marked
  INTRADAY_UNKNOWN, when only the day's low (or high) reached the limit. The
  bar can't say when an intraday touch happened, so it is never stamped at the
  open.
- **delivered_at**: the session's **decision moment D**, the first time a
  CLOSED revision of its daily bar was actually known (availability and
  delivery both counted), from `Knowledge.first_known_closed`. Nothing is
  delivered before the knowledge it depends on.
- **recorded_at**: when the worker ingests it.

Every call first **materializes** each outcome whose D <= the call's time,
using only cancels received strictly before D. The result is therefore the
same however often, or how late, the broker is polled. A correction known only
after D never changes an outcome.

Cancels: before the open, conclusive at once (the order never rests); from the
open until D, PENDING, with the first receipt time kept; at or after D, too
late. At D an opening fill stands against a pending cancel, while an
intraday-only fill loses to it: the touch time is unknown, so the conservative
assumption is recorded in provenance. If no bar is known by the next session's
open (the cutoff), the order expires, or is cancelled if a cancel was pending,
with "no market data", and no fill is invented. The full quantity always fills
(D19).
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal
from importlib.resources import files

from investment_engine.execution.broker_port import (
    BrokerFill,
    BrokerMessage,
    BrokerOrderReport,
    CancelResult,
    SubmitResult,
)
from investment_engine.market.availability import check_utc
from investment_engine.oms.intents import Side
from investment_engine.oms.orders import Order
from investment_engine.risk.decisions import exact
from investment_engine.storage.sqlite import port

MODEL_VERSION = "daily-fill-v1"
_PRICE = Context(prec=34, rounding=ROUND_HALF_EVEN)
_CENT = Decimal("0.01")


@dataclass(frozen=True)
class FeeSchedule:
    version: str
    commission_per_order: Decimal
    slippage_bps: Decimal


def load_fee_schedule() -> FeeSchedule:
    data = json.loads(files("investment_engine.execution").joinpath("fees.json").read_text(encoding="utf-8"))
    return FeeSchedule(str(data["version"]), Decimal(str(data["commission_per_order"])),
                       Decimal(str(data["slippage_bps"])))


def _id(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:40]


class SimulatedBroker:
    """`account_id` scopes it to one broker account, as a real broker connection is (Codex M4 review B9): it then
    accepts, decides, reports and looks up that account's orders only. Unscoped (None), it serves every account, as
    the deployed worker's simulator always has."""

    def __init__(self, db, *, knowledge, calendar, source: str, fees: FeeSchedule,
                 account_id: str | None = None) -> None:
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("the simulated broker is PostgreSQL only (docs/tasks/M4-06.md)")
        self.knowledge, self.calendar, self.source, self.fees = knowledge, calendar, source, fees
        self.account_id = account_id

    def _scope(self, alias: str = "") -> tuple[str, dict]:
        """The SQL condition and parameters that keep this simulator to its account."""
        if self.account_id is None:
            return "TRUE", {}
        return f"{alias}account_id = :scope_account", {"scope_account": self.account_id}

    def _owns(self, client_order_id: str) -> bool:
        condition, params = self._scope()
        return self._db.fetchone(f"SELECT 1 FROM sim_broker.orders WHERE client_order_id = :c AND {condition}",
                                 {"c": client_order_id, **params}) is not None

    # ---------------------------------------------------------------- the port

    def submit(self, order: Order, *, at: datetime) -> SubmitResult:
        at = check_utc(at, "at")
        if self.account_id is not None and order.account_id != self.account_id:
            return SubmitResult(False, None, f"this simulated broker serves account {self.account_id} only")
        self.materialize(at)
        with self._db.transaction():
            existing = self._db.fetchone("SELECT broker_order_id, status FROM sim_broker.orders "
                                         "WHERE client_order_id = :c", {"c": order.client_order_id})
            if existing is not None:  # a repeat returns the existing order, never a second one
                return SubmitResult(existing[1] != "REJECTED", existing[0], "already received")
            reason = self._invalid(order, at)
            broker_id = "sim-" + _id("order", order.client_order_id)
            self._db.execute(
                "INSERT INTO sim_broker.orders (client_order_id, broker_order_id, instrument_id, side, quantity, "
                "limit_price, time_in_force, order_type, target_session, submitted_at, status, filled_qty, "
                "cancel_received_at, decided_at, account_id) VALUES (:c, :b, :instrument, :side, :qty, :limit, :tif, "
                ":type, :session, :at, :status, 0, NULL, NULL, :account)",
                {"c": order.client_order_id, "b": broker_id, "instrument": order.instrument_id,
                 "side": order.side.value, "qty": order.quantity, "limit": order.limit_price,
                 "tif": order.time_in_force, "type": order.order_type, "session": order.target_session, "at": at,
                 "status": "REJECTED" if reason else "OPEN", "account": order.account_id})
            if reason:
                return SubmitResult(False, None, reason)
            self._message(order.client_order_id, "ACK", at, None, "accepted; rests from the open")
        return SubmitResult(True, broker_id, "accepted")

    def cancel(self, client_order_id: str, *, at: datetime) -> CancelResult:
        at = check_utc(at, "at")
        self.materialize(at)
        condition, params = self._scope()
        with self._db.transaction():
            row = self._db.fetchone("SELECT status, target_session, cancel_received_at FROM sim_broker.orders "
                                    f"WHERE client_order_id = :c AND {condition} FOR UPDATE",
                                    {"c": client_order_id, **params})
            if row is None:
                return CancelResult("UNKNOWN_ORDER", None, "no such order")
            status, session, received = row
            if status == "CANCELLED":
                return CancelResult("CANCELLED", received, "already cancelled")
            if status in ("FILLED", "EXPIRED", "REJECTED"):
                return CancelResult("TOO_LATE", received or at, f"the order is already {status}")
            if received is not None:  # a retry: the first receipt time stands
                return CancelResult("PENDING", received, "already received; outcome decided when the bar is known")
            if at < self.calendar.session(session).open:  # never rests: conclusive, no price needed
                self._db.execute("UPDATE sim_broker.orders SET status = 'CANCELLED', cancel_received_at = :at "
                                 "WHERE client_order_id = :c", {"at": at, "c": client_order_id})
                self._message(client_order_id, "CANCELLED", at, None, "cancelled before the open")
                return CancelResult("CANCELLED", at, "cancelled before the open")
            self._db.execute("UPDATE sim_broker.orders SET cancel_received_at = :at WHERE client_order_id = :c",
                             {"at": at, "c": client_order_id})
        return CancelResult("PENDING", at, "received; the outcome is decided when the session's bar is known")

    def lookup(self, client_order_id: str, *, at: datetime) -> BrokerOrderReport | None:
        at = check_utc(at, "at")
        self.materialize(at)
        condition, params = self._scope()
        row = self._db.fetchone("SELECT broker_order_id, status, filled_qty, cancel_received_at FROM sim_broker.orders "
                                f"WHERE client_order_id = :c AND {condition}", {"c": client_order_id, **params})
        if row is None:
            return None
        status = "CANCEL_RECEIVED" if row[1] == "OPEN" and row[3] is not None else row[1]
        ids = tuple(r[0] for r in self._db.fetchall(
            "SELECT message_id FROM sim_broker.messages WHERE client_order_id = :c AND delivered_at <= :at "
            "ORDER BY delivered_at, message_id", {"c": client_order_id, "at": at}))
        return BrokerOrderReport(client_order_id, row[0], status, Decimal(row[2]), ids)

    def messages(self, *, after: str | None, at: datetime) -> list[BrokerMessage]:
        at = check_utc(at, "at")
        self.materialize(at)
        cursor = None
        if after is not None:
            cursor = self._db.fetchone("SELECT delivered_at, message_id FROM sim_broker.messages WHERE message_id = :m",
                                       {"m": after})
        condition, params = self._scope("o.")
        rows = self._db.fetchall(
            "SELECT m.message_id, m.client_order_id, m.kind, m.delivered_at, m.fill, m.reason FROM sim_broker.messages m "
            "JOIN sim_broker.orders o ON o.client_order_id = m.client_order_id "
            f"WHERE m.delivered_at <= :at AND {condition} ORDER BY m.delivered_at, m.message_id", {"at": at, **params})
        out = []
        for message_id, client, kind, delivered, fill, reason in rows:
            if cursor is not None and (delivered, message_id) <= tuple(cursor):
                continue
            out.append(BrokerMessage(message_id, client, kind, delivered, _fill(fill), reason))
        return out

    # ---------------------------------------------------------------- the model

    def _invalid(self, order: Order, at: datetime) -> str:
        if (order.order_type, order.time_in_force) != ("LIMIT", "DAY"):
            return "the simulator takes LIMIT / DAY orders only"
        if order.quantity != order.quantity.to_integral_value() or order.quantity <= 0:
            return "whole shares only"
        try:
            session = self.calendar.session(order.target_session)
        except ValueError:
            return f"{order.target_session} is not a session"
        if at >= session.open:
            return "daily model: orders must rest from the open; this one arrived at or after it"
        return ""

    def _message(self, client_order_id: str, kind: str, delivered_at: datetime, fill: BrokerFill | None,
                 reason: str) -> None:
        message_id = "msg-" + _id(client_order_id, kind)
        self._db.execute("INSERT INTO sim_broker.messages VALUES (:m, :c, :k, :d, :f, :r) ON CONFLICT DO NOTHING",
                         {"m": message_id, "c": client_order_id, "k": kind, "d": delivered_at,
                          "f": None if fill is None else _fill_json(fill), "r": reason})

    @exact  # one fully specified Decimal context, whatever the caller's (Codex M4 review B2)
    def _price(self, side: Side, base: Decimal, limit: Decimal) -> tuple[Decimal, Decimal]:
        factor = self.fees.slippage_bps / Decimal(10000)
        moved = _PRICE.multiply(base, Decimal(1) + factor if side is Side.BUY else Decimal(1) - factor)
        rounded = moved.quantize(_CENT, context=_PRICE)
        capped = min(rounded, limit) if side is Side.BUY else max(rounded, limit)
        return moved, capped

    def materialize(self, t: datetime) -> None:
        """Decide every open order whose decision moment is at or before `t` (rule 7)."""
        condition, params = self._scope()
        rows = self._db.fetchall(
            "SELECT client_order_id, instrument_id, side, quantity, limit_price, target_session, cancel_received_at "
            f"FROM sim_broker.orders WHERE status = 'OPEN' AND {condition} ORDER BY target_session, client_order_id",
            params)
        for client, instrument, side, quantity, limit, session_day, received in rows:
            session = self.calendar.session(session_day)
            cutoff = self.calendar.next_session(session_day).open
            known = self.knowledge.first_known_closed(self.source, instrument, session_day, not_after=min(t, cutoff),
                                                      calendar=self.calendar)
            if known is not None:
                decided_at, bar = known
                self._decide(client, Side(side), Decimal(quantity), Decimal(limit), session, decided_at, bar, received)
            elif cutoff <= t:
                self._missing(client, cutoff, received)

    @exact  # one fully specified Decimal context, whatever the caller's (Codex M4 review B2)
    def _decide(self, client, side, quantity, limit, session, decided_at, bar, received) -> None:
        if side is Side.BUY:
            at_open, touched = bar.open <= limit, bar.low <= limit
        else:
            at_open, touched = bar.open >= limit, bar.high >= limit
        provenance = {"model": MODEL_VERSION, "fees": self.fees.version, "slippage_bps": str(self.fees.slippage_bps),
                      "bar": {"provider": bar.source, "instrument": bar.instrument_id, "timeframe": str(bar.timeframe),
                              "start": bar.start_time.isoformat(), "revision": bar.revision, "import_id": bar.import_id},
                      "decided_at": decided_at.isoformat()}
        pending = received is not None
        with self._db.transaction():
            if at_open:
                moved, price = self._price(side, Decimal(bar.open), limit)
                timing, executed = "AT_OPEN", session.open
            elif touched and not pending:
                moved, price = self._price(side, limit, limit)
                timing, executed = "INTRADAY_UNKNOWN", session.close
            else:
                status = "CANCELLED" if pending else "EXPIRED"
                why = ("cancel received before the decision; only an intraday touch could have filled, and its time "
                       "is unknown, so the cancel wins (conservative)" if pending and touched
                       else "cancelled; the limit wasn't reached" if pending else "the limit wasn't reached; expired at "
                       "the close")
                self._db.execute("UPDATE sim_broker.orders SET status = :s, decided_at = :d WHERE client_order_id = :c",
                                 {"s": status, "d": decided_at, "c": client})
                self._message(client, status, decided_at, None, why)
                return
            provenance.update({"base_price": str(bar.open if timing == "AT_OPEN" else limit),
                               "after_slippage": str(moved), "price": str(price), "timing": timing,
                               "cancel_pending": pending})
            fill = BrokerFill("sim-fill-" + _id(client), quantity, price, self.fees.commission_per_order, "USD",
                              executed, json.dumps(provenance, sort_keys=True, separators=(",", ":")))
            self._db.execute("UPDATE sim_broker.orders SET status = 'FILLED', filled_qty = :q, decided_at = :d "
                             "WHERE client_order_id = :c", {"q": quantity, "d": decided_at, "c": client})
            self._message(client, "FILL", decided_at, fill, f"filled {timing}")

    def _missing(self, client, cutoff, received) -> None:
        status = "CANCELLED" if received is not None else "EXPIRED"
        with self._db.transaction():
            self._db.execute("UPDATE sim_broker.orders SET status = :s, decided_at = :d WHERE client_order_id = :c",
                             {"s": status, "d": cutoff, "c": client})
            self._message(client, status, cutoff, None, "no market data for the session; no fill modelled")


def _fill_json(fill: BrokerFill) -> str:
    return json.dumps({"broker_fill_id": fill.broker_fill_id, "quantity": str(fill.quantity), "price": str(fill.price),
                       "fee": str(fill.fee), "currency": fill.currency, "executed_at": fill.executed_at.isoformat(),
                       "provenance": fill.provenance}, sort_keys=True)


def _fill(text) -> BrokerFill | None:
    if text is None:
        return None
    d = json.loads(text)
    return BrokerFill(d["broker_fill_id"], Decimal(d["quantity"]), Decimal(d["price"]), Decimal(d["fee"]),
                      d["currency"], datetime.fromisoformat(d["executed_at"]), d["provenance"])


__all__ = ["MODEL_VERSION", "FeeSchedule", "SimulatedBroker", "load_fee_schedule"]
