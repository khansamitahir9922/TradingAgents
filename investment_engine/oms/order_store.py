"""The order store: orders, their versions, fills, anomalies, gate decisions and cancel requests (architecture G3,
Laws 8, 10, 11, 14; ADR-004; docs/tasks/M4-00.md).

Every write to an order is one compare-and-set: `aggregate_version` moves
from the expected value to the next, or nothing is written and StaleWrite is
raised (Law 10). Each write creates exactly one version and announces it with
exactly one event (rule 7):

    create                          -> v1, order.created
    a state edge without a fill     -> order.state_changed (a gate decision is part of its NEW edge)
    a fill, with or without a state change -> order.fill_recorded, carrying the resulting state

A message that needs an edge and a fill writes them one after the other, two
versions and two events. Anomalies create no version and publish nothing:
they are append-only rows with their audit event. Cancel requests are an
aggregate of their own, versioned 1 (REQUESTED), 2, 3 ... by inserting the next
row, so their progress never moves an order's version (rule 6).

Ownership (G3): the store's role is fixed when it is built; the Core Engine
creates orders and records cancel requests, the Execution Worker writes every
other edge, fill, anomaly, gate decision and cancel progress. Each write
transaction also sets `investment_engine.process_role` with set_config(...,
true), the transaction-local form of SET LOCAL, and schema 0011's triggers
refuse a row from any other role. That is a consistency check, not
authentication (rule 2).

Fills follow the matrix of rule 4: accounting changes the totals, and the state
moves only along a G3 edge; delayed fills on CANCELLED or EXPIRED orders are
accounting only; fills on orders that never reached the broker, or were
rejected or already filled, are refused and stored as anomalies.
"""

import json
import zlib
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal

from investment_engine.audit.events import Actor, ActorKind, AuditEvent, AuditStore
from investment_engine.events.envelope import SCHEMA_VERSION, EventEnvelope, OutboxWriter
from investment_engine.lineage.records import canonical_json, decode
from investment_engine.market.availability import check_utc
from investment_engine.oms import order_states
from investment_engine.oms.intent_store import StaleWrite
from investment_engine.oms.order_states import FILL_STATES, FINAL, OrderState, ProcessRole
from investment_engine.oms.orders import (
    CANCEL_EDGES,
    CANCEL_OUTCOMES,
    Anomaly,
    CancelProgress,
    CancelRequest,
    Fill,
    FillOutcome,
    GateDecision,
    Order,
    OrderStatus,
    OrderTransition,
)
from investment_engine.policy.accounts import AccountKind
from investment_engine.risk.decisions import exact
from investment_engine.storage.sqlite import port

S = OrderState
_AVG = Context(prec=34, rounding=ROUND_HALF_EVEN)
_AVG_PLACES = Decimal("0.0000000001")
_REFUSE_FILLS = frozenset({S.NEW, S.GATE_REJECTED, S.REJECTED, S.FILLED})  # never reached the broker, or done


def _blob(value) -> bytes:
    return zlib.compress(canonical_json(value).encode(), 6)


def _value(blob):
    return decode(json.loads(zlib.decompress(bytes(blob)).decode()))


_ORDER = ("SELECT content, state, aggregate_version, filled_qty, avg_price, broker_order_id, "
          "(SELECT COUNT(*) FROM broker_anomalies b WHERE b.order_id = o.order_id) FROM orders o")


class OrderStore:
    def __init__(self, db, *, role: ProcessRole, audit: AuditStore, outbox: OutboxWriter, clock) -> None:
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("orders are PostgreSQL only (docs/tasks/M4-00.md)")
        if getattr(audit, "_db", None) is not self._db:
            raise ValueError("the audit store must share this store's database port")
        self.role = ProcessRole(role)
        self._audit, self._outbox, self._clock = audit, outbox, clock
        self._actor = Actor(ActorKind.PROCESS, self.role.value, None, None)

    # ---------------------------------------------------------------- reads

    def _status(self, row) -> tuple[Order, OrderStatus]:
        order = _value(row[0])
        return order, OrderStatus(order.order_id, S(row[1]), row[2], Decimal(row[3]),
                                  None if row[4] is None else Decimal(row[4]), row[5], row[6])

    def get(self, order_id: str) -> tuple[Order, OrderStatus]:
        row = self._db.fetchone(_ORDER + " WHERE o.order_id = :id", {"id": order_id})
        if row is None:
            raise KeyError(f"unknown order {order_id}")
        return self._status(row)

    def by_client_id(self, client_order_id: str) -> tuple[Order, OrderStatus]:
        row = self._db.fetchone(_ORDER + " WHERE o.client_order_id = :id", {"id": client_order_id})
        if row is None:
            raise KeyError(f"unknown client order id {client_order_id}")
        return self._status(row)

    def for_intent(self, intent_id: str, intent_version: int) -> tuple[Order, OrderStatus] | None:
        row = self._db.fetchone(_ORDER + " WHERE o.intent_id = :id AND o.intent_version = :v",
                                {"id": intent_id, "v": intent_version})
        return None if row is None else self._status(row)

    def in_states(self, *states: OrderState, account_id: str | None = None) -> list[tuple[Order, OrderStatus]]:
        values = sorted(S(s).value for s in states)
        if account_id is None:
            rows = self._db.fetchall(_ORDER + " WHERE o.state = ANY(:states) ORDER BY o.created_at, o.order_id",
                                     {"states": values})
        else:
            rows = self._db.fetchall(_ORDER + " WHERE o.state = ANY(:states) AND o.account_id = :account "
                                     "ORDER BY o.created_at, o.order_id", {"states": values, "account": account_id})
        return [self._status(r) for r in rows]

    def for_account(self, account_id: str) -> list[tuple[Order, OrderStatus]]:
        rows = self._db.fetchall(_ORDER + " WHERE o.account_id = :id ORDER BY o.created_at, o.order_id",
                                 {"id": account_id})
        return [self._status(r) for r in rows]

    def history(self, order_id: str) -> list[OrderTransition]:
        rows = self._db.fetchall("SELECT order_id, aggregate_version, from_state, to_state, at, recorded_at, by_role, "
                                 "reason, broker_ref FROM order_versions WHERE order_id = :id "
                                 "ORDER BY aggregate_version", {"id": order_id})
        return [OrderTransition(r[0], r[1], None if r[2] is None else S(r[2]), S(r[3]), *r[4:]) for r in rows]

    def fills(self, order_id: str) -> list[Fill]:
        rows = self._db.fetchall("SELECT order_id, quantity, price, fee, currency, executed_at, delivered_at, "
                                 "recorded_at, broker_fill_id, provenance FROM fills WHERE order_id = :id "
                                 "ORDER BY executed_at, fill_id", {"id": order_id})
        return [Fill(r[0], Decimal(r[1]), Decimal(r[2]), Decimal(r[3]), *r[4:]) for r in rows]

    def anomalies(self, order_id: str) -> list[Anomaly]:
        rows = self._db.fetchall("SELECT order_id, kind, detail, at, recorded_at, broker_ref, at_version "
                                 "FROM broker_anomalies WHERE order_id = :id ORDER BY sequence", {"id": order_id})
        return [Anomaly(*r) for r in rows]

    def gate_decisions(self, order_id: str) -> list[GateDecision]:
        rows = self._db.fetchall("SELECT order_id, attempt, passed, checks, checked_at, inputs FROM gate_decisions "
                                 "WHERE order_id = :id ORDER BY attempt", {"id": order_id})
        return [GateDecision(r[0], r[1], r[2], _value(r[3]), r[4], r[5]) for r in rows]

    def cancel(self, cancel_id: str) -> tuple[CancelRequest, CancelProgress, int, str | None]:
        row = self._db.fetchone(
            "SELECT r.content, p.progress, p.version, p.outcome FROM cancel_requests r JOIN cancel_progress p "
            "ON p.cancel_id = r.cancel_id WHERE r.cancel_id = :id ORDER BY p.version DESC LIMIT 1", {"id": cancel_id})
        if row is None:
            raise KeyError(f"unknown cancel request {cancel_id}")
        return _value(row[0]), CancelProgress(row[1]), row[2], row[3]

    def open_cancels(self) -> list[tuple[CancelRequest, CancelProgress, int]]:
        rows = self._db.fetchall(
            "SELECT r.content, p.progress, p.version FROM cancel_requests r JOIN cancel_progress p "
            "ON p.cancel_id = r.cancel_id WHERE p.version = (SELECT MAX(q.version) FROM cancel_progress q "
            "WHERE q.cancel_id = r.cancel_id) AND p.progress <> 'CLOSED' ORDER BY r.requested_at, r.cancel_id")
        return [(_value(r[0]), CancelProgress(r[1]), r[2]) for r in rows]

    def cancel_attempts(self, cancel_id: str) -> int:
        return self._db.fetchone("SELECT COALESCE(MAX(attempt), 0) FROM cancel_progress WHERE cancel_id = :id",
                                 {"id": cancel_id})[0]

    def as_of(self, account_id: str, at: datetime) -> list[tuple[Order, OrderState, Decimal]]:
        """Each order of the account as known at `at`: only versions whose recorded time is <= at (rule 10)."""
        at = check_utc(at, "at")
        rows = self._db.fetchall(
            "SELECT o.content, v.to_state, v.filled_qty FROM orders o JOIN order_versions v ON v.order_id = o.order_id "
            "WHERE o.account_id = :account AND v.aggregate_version = (SELECT MAX(w.aggregate_version) "
            "FROM order_versions w WHERE w.order_id = o.order_id AND w.recorded_at <= :at) "
            "ORDER BY o.created_at, o.order_id", {"account": account_id, "at": at})
        return [(_value(r[0]), S(r[1]), Decimal(r[2])) for r in rows]

    # ---------------------------------------------------------------- write helpers

    def _now(self) -> datetime:
        return check_utc(self._clock.now(), "now")

    def _claim_role(self) -> None:
        self._db.execute("SELECT set_config('investment_engine.process_role', :role, true)", {"role": self.role.value})

    def _require(self, owner: ProcessRole, what: str) -> None:
        if self.role is not owner:
            raise order_states.WrongProcess(f"{what} is written only by the {owner.value}, not the {self.role.value}")

    def _business(self, order: Order, at: datetime) -> datetime | None:
        return at if order.account_kind is AccountKind.RESEARCH else None

    def _event(self, event_type: str, aggregate_type: str, aggregate_id: str, version: int, at: datetime,
               now: datetime, correlation_id: str, payload: dict) -> None:
        self._outbox.add(EventEnvelope(event_type, SCHEMA_VERSION, aggregate_type, aggregate_id, version, at, now,
                                       correlation_id, None, canonical_json(payload)))

    def _audit_event(self, by: Actor, action: str, target_type: str, target_id: str, before, after, now, business,
                     reason: str, correlation_id: str, key: str) -> None:
        self._audit.append(AuditEvent(by, action, target_type, target_id, before, after, now, business, reason,
                                      correlation_id, key))

    def _log(self, order_id: str, version: int, from_state, to_state, filled: Decimal, at, now, reason: str,
             broker_ref: str | None) -> None:
        self._db.execute("INSERT INTO order_versions VALUES (:id, :v, :from_state, :to_state, :filled, :at, :now, "
                         ":role, :reason, :ref)",
                         {"id": order_id, "v": version, "from_state": None if from_state is None else S(from_state).value,
                          "to_state": S(to_state).value, "filled": filled, "at": at, "now": now,
                          "role": self.role.value, "reason": reason, "ref": broker_ref})

    def _cas(self, order_id: str, expected: int, *, state: OrderState, filled: Decimal, avg: Decimal | None,
             broker_order_id: str | None) -> None:
        moved = self._db.fetchone(
            "UPDATE orders SET aggregate_version = aggregate_version + 1, state = :state, filled_qty = :filled, "
            "avg_price = :avg, broker_order_id = COALESCE(broker_order_id, :broker) "
            "WHERE order_id = :id AND aggregate_version = :expected RETURNING aggregate_version",
            {"state": state.value, "filled": filled, "avg": avg, "broker": broker_order_id, "id": order_id,
             "expected": expected})
        if moved is None:
            raise StaleWrite(f"{order_id} changed since version {expected}; nothing was written")

    # ---------------------------------------------------------------- writes

    def create(self, order: Order, *, by: Actor, correlation_id: str) -> OrderStatus:
        """Version 1, NEW (Core Engine only). Re-creating the identical order is a no-op."""
        self._require(ProcessRole.CORE, "order creation")
        if not isinstance(order, Order):
            raise TypeError("expected an Order")
        now = self._now()
        with self._db.transaction():
            self._claim_role()
            existing = self.for_intent(order.intent_id, order.intent_version)
            if existing is not None:
                if existing[0] != order:
                    raise ValueError(f"{order.intent_id} version {order.intent_version} already has another order")
                return existing[1]
            self._db.execute(
                "INSERT INTO orders VALUES (:id, :client, :intent, :version, :content_id, :fingerprint, :account, "
                ":kind, :instrument, :side, :quantity, :type, :limit, :tif, :session, :created, :now, :content, "
                "'NEW', 1, 0, NULL, NULL)",
                {"id": order.order_id, "client": order.client_order_id, "intent": order.intent_id,
                 "version": order.intent_version, "content_id": order.intent_content_id,
                 "fingerprint": order.position_fingerprint, "account": order.account_id,
                 "kind": order.account_kind.value, "instrument": order.instrument_id, "side": order.side.value,
                 "quantity": order.quantity, "type": order.order_type, "limit": order.limit_price,
                 "tif": order.time_in_force, "session": order.target_session, "created": order.created_at,
                 "now": now, "content": _blob(order)})
            self._log(order.order_id, 1, None, S.NEW, Decimal(0), order.created_at, now, "created", None)
            self._event("order.created", "order", order.order_id, 1, order.created_at, now, correlation_id,
                        {"order": order})
            self._audit_event(by, "order.create", "order", order.order_id, None, order, now,
                              self._business(order, order.created_at), "created from the approved intent version",
                              correlation_id, f"order.create:{order.order_id}")
        return self.get(order.order_id)[1]

    def transition(self, order_id: str, to: OrderState, *, expected_aggregate_version: int, at: datetime,
                   reason: str, broker_ref: str | None = None, broker_order_id: str | None = None,
                   gate: GateDecision | None = None, correlation_id: str = "") -> OrderStatus:
        """One G3 edge without a fill (PARTIALLY_FILLED and FILLED are reached only through record_fill)."""
        to = S(to)
        at, now = check_utc(at, "at"), self._now()
        if to in FILL_STATES:
            raise order_states.IllegalTransition(f"{to} is reached only by recording a fill (rule 4)")
        with self._db.transaction():
            self._claim_role()
            order, status = self.get(order_id)
            order_states.check(status.state, to, self.role)
            from_new = status.state is S.NEW
            if from_new != (gate is not None):
                raise ValueError("leaving NEW records its gate decision, and only that edge does (M4-05)")
            if gate is not None and (gate.order_id != order_id or gate.passed != (to is S.SUBMITTING)):
                raise ValueError("the gate decision must be this order's, passed for SUBMITTING, failed otherwise")
            version = expected_aggregate_version + 1
            self._cas(order_id, expected_aggregate_version, state=to, filled=status.filled_qty,
                      avg=status.avg_price, broker_order_id=broker_order_id)
            self._log(order_id, version, status.state, to, status.filled_qty, at, now, reason, broker_ref)
            payload = {"from": status.state, "to": to, "reason": reason, "broker_ref": broker_ref}
            if gate is not None:
                attempt = self._db.fetchone("SELECT COALESCE(MAX(attempt), 0) + 1 FROM gate_decisions "
                                            "WHERE order_id = :id", {"id": order_id})[0]
                gate = GateDecision(order_id, attempt, gate.passed, gate.checks, gate.checked_at, gate.inputs)
                self._db.execute("INSERT INTO gate_decisions VALUES (:id, :attempt, :passed, :checks, :checked, "
                                 ":inputs, :v)",
                                 {"id": order_id, "attempt": attempt, "passed": gate.passed, "checks": _blob(gate.checks),
                                  "checked": gate.checked_at, "inputs": gate.inputs, "v": version})
                payload["gate"] = gate
            correlation = correlation_id or f"order:{order_id}"
            self._event("order.state_changed", "order", order_id, version, at, now, correlation, payload)
            self._audit_event(self._actor, f"order.{to.value.lower()}", "order", order_id, status.state.value,
                              to.value, now, self._business(order, at), reason, correlation,
                              f"order.version:{order_id}:{version}")
        return self.get(order_id)[1]

    def _anomaly(self, order: Order, status: OrderStatus, kind: str, detail: str, at, now, broker_ref: str) -> None:
        sequence = self._db.fetchone("SELECT COALESCE(MAX(sequence), 0) + 1 FROM broker_anomalies "
                                     "WHERE order_id = :id", {"id": order.order_id})[0]
        self._db.execute("INSERT INTO broker_anomalies VALUES (:id, :seq, :kind, :detail, :at, :now, :ref, :v)",
                         {"id": order.order_id, "seq": sequence, "kind": kind, "detail": detail, "at": at, "now": now,
                          "ref": broker_ref, "v": status.aggregate_version})
        anomaly = Anomaly(order.order_id, kind, detail, at, now, broker_ref, status.aggregate_version)
        self._audit_event(self._actor, "order.anomaly", "order", order.order_id, None, anomaly, now,
                          self._business(order, at), kind, f"order:{order.order_id}",
                          f"order.anomaly:{order.order_id}:{sequence}")

    def record_anomaly(self, order_id: str, *, kind: str, detail: str, at: datetime, broker_ref: str) -> None:
        """An observation with no legal effect (rule 4; M4-07 rule 2): no version, no event, audited."""
        self._require(ProcessRole.EXECUTION, "an anomaly")
        at, now = check_utc(at, "at"), self._now()
        with self._db.transaction():
            self._claim_role()
            order, status = self.get(order_id)
            self._anomaly(order, status, kind, detail, at, now, broker_ref)

    @exact  # one fully specified Decimal context, whatever the caller's (Codex M4 review B2)
    def record_fill(self, fill: Fill, *, expected_aggregate_version: int, correlation_id: str = "") -> FillOutcome:
        """Apply one broker fill under the rule 4 matrix (Execution Worker only)."""
        self._require(ProcessRole.EXECUTION, "a fill")
        if not isinstance(fill, Fill):
            raise TypeError("expected a Fill")
        now = self._now()
        with self._db.transaction():
            self._claim_role()
            order, status = self.get(fill.order_id)
            row = self._db.fetchone("SELECT order_id, quantity, price, fee, currency, executed_at, delivered_at, "
                                    "recorded_at, broker_fill_id, provenance FROM fills WHERE broker_fill_id = :id",
                                    {"id": fill.broker_fill_id})
            if row is not None:
                known = Fill(row[0], Decimal(row[1]), Decimal(row[2]), Decimal(row[3]), *row[4:])
                if known.same_execution(fill):
                    return FillOutcome.DUPLICATE
                self._anomaly(order, status, "conflicting_duplicate_fill",
                              f"{fill.broker_fill_id} was recorded with different content", fill.executed_at, now,
                              fill.broker_fill_id)
                return FillOutcome.CONFLICT
            if status.aggregate_version != expected_aggregate_version:
                raise StaleWrite(f"{order.order_id} changed since version {expected_aggregate_version}")
            if status.state in _REFUSE_FILLS:
                self._anomaly(order, status, "fill_refused", f"a fill on a {status.state} order is never recorded",
                              fill.executed_at, now, fill.broker_fill_id)
                return FillOutcome.REFUSED
            total = status.filled_qty + fill.quantity
            if total > order.quantity:
                self._anomaly(order, status, "overfill", f"{total} > {order.quantity}", fill.executed_at, now,
                              fill.broker_fill_id)
                return FillOutcome.REFUSED
            version, state = status.aggregate_version, status.state
            correlation = correlation_id or f"order:{order.order_id}"
            if state is S.SUBMITTING:  # a fill before the ack: SUBMITTING -> SUBMITTED first (two versions)
                order_states.check(state, S.SUBMITTED, self.role)
                self._cas(order.order_id, version, state=S.SUBMITTED, filled=status.filled_qty,
                          avg=status.avg_price, broker_order_id=None)
                version += 1
                self._log(order.order_id, version, state, S.SUBMITTED, status.filled_qty, fill.executed_at, now,
                          "fill before the acknowledgement", fill.broker_fill_id)
                self._event("order.state_changed", "order", order.order_id, version, fill.executed_at, now,
                            correlation, {"from": state, "to": S.SUBMITTED, "reason": "fill before the ack",
                                          "broker_ref": fill.broker_fill_id})
                self._audit_event(self._actor, "order.submitted", "order", order.order_id, state.value,
                                  S.SUBMITTED.value, now, self._business(order, fill.executed_at),
                                  "fill before the acknowledgement", correlation,
                                  f"order.version:{order.order_id}:{version}")
                state = S.SUBMITTED
            complete = total == order.quantity
            if state in (S.CANCELLED, S.EXPIRED):
                new_state = state  # accounting only; the state stays final
            elif complete:
                new_state = S.FILLED
            else:
                new_state = S.PARTIALLY_FILLED
            if new_state is not state:
                order_states.check(state, new_state, self.role)
            weighted = _AVG.add(_AVG.multiply(status.avg_price or Decimal(0), status.filled_qty),
                                _AVG.multiply(fill.price, fill.quantity))
            avg = _AVG.divide(weighted, total).quantize(_AVG_PLACES, context=_AVG)
            self._cas(order.order_id, version, state=new_state, filled=total, avg=avg, broker_order_id=None)
            version += 1
            self._log(order.order_id, version, state, new_state, total, fill.executed_at, now, "fill",
                      fill.broker_fill_id)
            self._db.execute("INSERT INTO fills VALUES (:fid, :id, :bid, :q, :p, :fee, :cur, :ex, :dl, :rec, :prov, :v)",
                             {"fid": fill.fill_id, "id": order.order_id, "bid": fill.broker_fill_id, "q": fill.quantity,
                              "p": fill.price, "fee": fill.fee, "cur": fill.currency, "ex": fill.executed_at,
                              "dl": fill.delivered_at, "rec": fill.recorded_at, "prov": fill.provenance, "v": version})
            self._event("order.fill_recorded", "order", order.order_id, version, fill.executed_at, now, correlation,
                        {"fill": fill, "state": new_state, "filled_qty": total})
            self._audit_event(self._actor, "order.fill", "order", order.order_id, state.value, fill, now,
                              self._business(order, fill.executed_at), "fill", correlation,
                              f"order.version:{order.order_id}:{version}")
            if state in (S.CANCELLED, S.EXPIRED) and complete:
                self._anomaly(order, OrderStatus(order.order_id, new_state, version, total, avg, None, 0),
                              "fill_after_final", f"a delayed fill completed a {state} order", fill.executed_at, now,
                              fill.broker_fill_id)
        return FillOutcome.RECORDED

    def request_cancel(self, request: CancelRequest, *, correlation_id: str) -> CancelRequest:
        """Version 1 of a cancel-request aggregate (Core Engine or a command; rule 6). No order state changes."""
        self._require(ProcessRole.CORE, "a cancel request")
        now = self._now()
        with self._db.transaction():
            self._claim_role()
            order, status = self.get(request.order_id)
            if status.state in FINAL:
                raise ValueError(f"{order.order_id} is {status.state}; there is nothing to cancel")
            if self._db.fetchone("SELECT 1 FROM cancel_requests WHERE cancel_id = :id",
                                 {"id": request.cancel_id}) is not None:
                return request
            self._db.execute("INSERT INTO cancel_requests VALUES (:id, :order, :content, :at, :now)",
                             {"id": request.cancel_id, "order": order.order_id, "content": _blob(request),
                              "at": request.requested_at, "now": now})
            self._db.execute("INSERT INTO cancel_progress VALUES (:id, 1, 'REQUESTED', 0, NULL, NULL, :at, :now)",
                             {"id": request.cancel_id, "at": request.requested_at, "now": now})
            self._event("cancel.requested", "cancel_request", request.cancel_id, 1, request.requested_at, now,
                        correlation_id, {"request": request})
            self._audit_event(request.requested_by, "cancel.request", "order", order.order_id, None, request, now,
                              self._business(order, request.requested_at), request.reason, correlation_id,
                              f"cancel.request:{request.cancel_id}")
        return request

    def cancel_progress(self, cancel_id: str, to: CancelProgress, *, expected_version: int, at: datetime,
                        outcome: str | None = None, received_at: datetime | None = None) -> int:
        """The next version of a cancel request (Execution Worker only); returns that version."""
        self._require(ProcessRole.EXECUTION, "cancel progress")
        to = CancelProgress(to)
        at, now = check_utc(at, "at"), self._now()
        if (to is CancelProgress.CLOSED) != (outcome is not None) or (outcome and outcome not in CANCEL_OUTCOMES):
            raise ValueError(f"CLOSED carries one outcome of {CANCEL_OUTCOMES}, and only CLOSED does")
        with self._db.transaction():
            self._claim_role()
            request, current, version, _ = self.cancel(cancel_id)
            if version != expected_version:
                raise StaleWrite(f"{cancel_id} changed since version {expected_version}")
            if to not in CANCEL_EDGES.get(current, frozenset()):
                raise ValueError(f"cancel progress {current} -> {to} is not allowed")
            attempt = self.cancel_attempts(cancel_id) + (1 if to is CancelProgress.SENDING else 0)
            self._db.execute("INSERT INTO cancel_progress VALUES (:id, :v, :p, :attempt, :outcome, :received, :at, "
                             ":now)", {"id": cancel_id, "v": version + 1, "p": to.value, "attempt": attempt,
                                       "outcome": outcome, "received": received_at, "at": at, "now": now})
            order, _ = self.get(request.order_id)
            self._event("cancel.progressed", "cancel_request", cancel_id, version + 1, at, now, f"cancel:{cancel_id}",
                        {"progress": to, "attempt": attempt, "outcome": outcome})
            self._audit_event(self._actor, f"cancel.{to.value.lower()}", "order", order.order_id, current.value,
                              to.value, now, self._business(order, at), outcome or to.value, f"cancel:{cancel_id}",
                              f"cancel.progress:{cancel_id}:{version + 1}")
        return version + 1


__all__ = ["OrderStore", "StaleWrite"]
