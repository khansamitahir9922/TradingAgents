"""The order log: every order of an account, explained (architecture Part K M4; Law 18; design principles T-01 –
T-04; docs/tasks/M4-13.md rule 5).

It reads only the order store, intents and lineage: never the simulated broker's private tables. Each order shows
its intent version and lineage id, its gate decision with every check, each transition with its time and owner, each
fill with quantity, price, fee, its executed, delivered and recorded times, timing basis, slippage and bar reference
(from the fill's provenance), its anomalies and its final state. A header gives the provider, instrument, range,
cutoff and timezone and the versions involved. A summary gives counts by final state, filled notional, fees,
unresolved UNKNOWN orders (D20), corporate-action adjustments and any stop. Units are explicit (shares, USD).
Output is plain ASCII.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from investment_engine.oms.order_states import OrderState
from investment_engine.risk.decisions import exact

LABEL = "SIMULATED | RESEARCH | NOT PROMOTED | PROVISIONAL POSITIONS"


@dataclass(frozen=True)
class OrderLog:
    header: dict
    orders: list
    summary: dict

    def to_json(self) -> str:
        return json.dumps({"label": LABEL, "header": self.header, "orders": self.orders, "summary": self.summary},
                          sort_keys=True, indent=1, default=str)

    def to_text(self) -> str:
        lines = [LABEL, ""]
        for key in sorted(self.header):
            lines.append(f"{key}: {self.header[key]}")
        for o in self.orders:
            lines += ["", f"ORDER {o['order_id']} ({o['side']} {o['quantity']} shares {o['instrument']} LIMIT "
                      f"{o['limit_price']} USD DAY, target session {o['target_session']})",
                      f"  intent {o['intent_id']} v{o['intent_version']}; lineage {o['lineage_id']}"]
            for g in o["gate"]:
                lines.append(f"  gate attempt {g['attempt']}: {'PASSED' if g['passed'] else 'FAILED'} at {g['at']}")
                for name, passed, reason in g["checks"]:
                    lines.append(f"    {'ok  ' if passed else 'FAIL'} {name}: {reason}")
            for t in o["transitions"]:
                lines.append(f"  v{t['version']} {t['from'] or '-'} -> {t['to']} at {t['at']} by {t['by']}: {t['reason']}")
            for f in o["fills"]:
                lines.append(f"  fill {f['quantity']} shares at {f['price']} USD, fee {f['fee']} USD; executed "
                             f"{f['executed_at']} ({f['timing']}), delivered {f['delivered_at']}, recorded "
                             f"{f['recorded_at']}; slippage {f['slippage_bps']} bps; bar {f['bar']}")
            for a in o["anomalies"]:
                lines.append(f"  anomaly {a['kind']}: {a['detail']}")
            lines.append(f"  FINAL {o['final_state']}" + ("  UNRESOLVED: broker has no record (D20)"
                                                          if o["final_state"] == "UNKNOWN" else ""))
        lines += ["", "SUMMARY"]
        for key in sorted(self.summary):
            lines.append(f"{key}: {self.summary[key]}")
        lines += ["", "P&L here is provisional, from fills (D29). The ledger and reconciliation arrive in M5."]
        text = "\n".join(lines)
        return text.encode("ascii", "replace").decode("ascii")


def _plain(value: Decimal) -> str:
    """A ratio without the storage scale: 4.000000000000 -> 4, 1.5 stays 1.5."""
    return format(value.normalize(), "f")


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


@exact  # one fully specified Decimal context, whatever the caller's (Codex M4 review B2)
def build_order_log(account_id: str, *, orders, intents, lineage, calendar, source: str, header_extra: dict,
                    stops=(), snapshots=None, at: datetime | None = None) -> OrderLog:
    rows, states, notional, fees, fee_versions, models = [], {}, Decimal(0), Decimal(0), set(), set()
    first = last = None
    strategy_versions, policy_versions, limits = set(), set(), set()
    for order, status in orders.for_account(account_id):
        intent = intents.get(order.intent_id, order.intent_version).intent
        strategy = lineage.get(intent.view_lineage_id)
        strategy_versions |= {f"{k}={v}" for k, v in dict(strategy.strategy_versions).items()}
        policy_versions.add(strategy.policy_version)
        limits.add(f"{intent.risk_version}/{intent.policy_version}")
        first = order.target_session if first is None else min(first, order.target_session)
        last = order.target_session if last is None else max(last, order.target_session)
        fills = []
        for f in orders.fills(order.order_id):
            p = json.loads(f.provenance) if f.provenance.startswith("{") else {}
            fee_versions.add(p.get("fees", "unknown"))
            models.add(p.get("model", "unknown"))
            bar = p.get("bar", {})
            fills.append({"quantity": str(f.quantity), "price": str(f.price), "fee": str(f.fee),
                          "executed_at": _iso(f.executed_at), "delivered_at": _iso(f.delivered_at),
                          "recorded_at": _iso(f.recorded_at), "timing": p.get("timing", "unknown"),
                          "slippage_bps": p.get("slippage_bps", "unknown"),
                          "bar": f"{bar.get('provider')} {bar.get('instrument')} {bar.get('timeframe')} "
                                 f"{bar.get('start')} r{bar.get('revision')}" if bar else "unknown"})
            notional += f.quantity * f.price
            fees += f.fee
        states[status.state.value] = states.get(status.state.value, 0) + 1
        rows.append({
            "order_id": order.order_id, "side": order.side.value, "quantity": str(order.quantity),
            "instrument": order.instrument_id, "limit_price": str(order.limit_price),
            "target_session": str(order.target_session), "intent_id": order.intent_id,
            "intent_version": order.intent_version, "lineage_id": intent.view_lineage_id,
            "gate": [{"attempt": g.attempt, "passed": g.passed, "at": _iso(g.checked_at),
                      "checks": [(c.name, c.passed, c.reason) for c in g.checks]}
                     for g in orders.gate_decisions(order.order_id)],
            "transitions": [{"version": t.aggregate_version, "from": None if t.from_state is None else t.from_state.value,
                             "to": t.to_state.value, "at": _iso(t.at), "by": t.by, "reason": t.reason}
                            for t in orders.history(order.order_id)],
            "fills": fills,
            "anomalies": [{"kind": a.kind, "detail": a.detail} for a in orders.anomalies(order.order_id)],
            "final_state": status.state.value})
    header = {"provider (source)": source, "account": account_id, "range": f"{first} .. {last} (target sessions)" if rows else "none (no orders)",
              "timezone": f"UTC, with exchange time {calendar.timezone}",
              "strategy versions": ", ".join(sorted(strategy_versions)) or "none",
              "decision policy": ", ".join(sorted(policy_versions)) or "none",
              "limits (risk/policy)": ", ".join(sorted(limits)) or "none",
              "fee schedule": ", ".join(sorted(fee_versions)) or "none (no fills)",
              "fill model": ", ".join(sorted(models)) or "none (no fills)", **header_extra}
    unknown = states.get(OrderState.UNKNOWN.value, 0)
    summary = {"orders": len(rows), "by final state": ", ".join(f"{k} {v}" for k, v in sorted(states.items())) or "none (no orders)",
               "filled notional (USD)": str(notional), "fees (USD)": str(fees),
               "UNRESOLVED (UNKNOWN, broker has no record)": unknown,
               "stops (projection unavailable)": "; ".join(stops) or "none"}
    adjustments = []
    if snapshots is not None and at is not None:
        latest = snapshots.latest(account_id, at)
        adjustments = list(getattr(latest, "adjustments", None) or ())
    summary["corporate-action adjustments"] = ", ".join(
        f"{a.kind} {a.instrument_id} {a.effective_at.date()} "
        + (f"(receivable {a.value} USD)" if a.kind == "DIVIDEND" else f"(ratio {_plain(a.value)})")
        for a in adjustments) or "none"
    return OrderLog(header, rows, summary)


__all__ = ["LABEL", "OrderLog", "build_order_log"]
