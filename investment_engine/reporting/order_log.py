"""The order log: every order of an account, explained (architecture Part K M4; Law 18; design principles T-01 –
T-04; docs/tasks/M4-13.md rule 5).

It reads only the order store, intents, lineage, intent lineage, proposal records and snapshots: never the
simulated broker's private tables. Everything comes from stored records, so a log produced later, in another
process, says the same as one produced right after the run (Codex M4 review B11). Each order shows
its intent version and lineage id, its gate decision with every check, each transition with its time and owner, each
fill with quantity, price, fee, its executed, delivered and recorded times, timing basis, slippage and bar reference
(from the fill's provenance), its anomalies and its final state. An UNKNOWN order says "the broker had no record"
only when a recorded lookup said so, with its time; otherwise it is unconfirmed. A header gives the provider,
range, the cutoff (the latest recorded order time) and timezone, and the code, calendar, strategy, policy, limits,
fee and fill-model versions involved. A summary gives counts by final state, filled notional, fees, UNKNOWN orders
(D20), the corporate-action adjustments of the snapshot it names, and any stop, read from the stored proposal
records. Units are explicit (shares, USD). Output is plain ASCII.
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
            lines.append(f"  FINAL {o['final_state']}" + (f"  {o['unknown']}" if o.get("unknown") else ""))
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
def _unknown(anomalies) -> str:
    """What an UNKNOWN order's record supports (D20): never more than a recorded lookup said."""
    no_record = [a for a in anomalies if a.kind == "lookup_no_record"]
    if no_record:
        return f"UNRESOLVED: the broker had no record at a lookup at {_iso(no_record[-1].at)} (D20); never resent"
    return "UNCONFIRMED: the outcome is unknown; no lookup has answered yet; never resent"


def stops_from(proposals, account_id: str) -> list[str]:
    """Why proposing stopped: each stored proposal for which the provisional projection was unavailable."""
    return [f"{r.at.isoformat()}: {r.reason}" for r in proposals.for_account(account_id)
            if r.outcome.value == "PREREQUISITE_MISSING" and "snapshot" in r.missing]


def build_order_log(account_id: str, *, orders, intents, lineage, calendar, source: str, header_extra: dict,
                    stops=None, snapshots=None, at: datetime | None = None, proposals=None,
                    intent_lineage=None) -> OrderLog:
    """With `proposals` the stops are read from the stored records, the authoritative source; `stops` is used only
    without them. With `intent_lineage` the code and calendar versions are those the intents were proposed with."""
    rows, states, notional, fees, fee_versions, models = [], {}, Decimal(0), Decimal(0), set(), set()
    first = last = cutoff = None
    strategy_versions, policy_versions, limits = set(), set(), set()
    code_versions, calendar_versions, no_record = set(), set(), 0
    for order, status in orders.for_account(account_id):
        stored = intents.get(order.intent_id, order.intent_version)
        intent = stored.intent
        if intent_lineage is not None and stored.lineage_id is not None:
            record = intent_lineage.get(stored.lineage_id)
            code_versions.add(record.code_version)
            calendar_versions.add(record.calendar_version)
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
        history = orders.history(order.order_id)
        anomalies = orders.anomalies(order.order_id)
        for t in history:
            cutoff = t.at if cutoff is None else max(cutoff, t.at)
        unknown = _unknown(anomalies) if status.state is OrderState.UNKNOWN else ""
        no_record += unknown.startswith("UNRESOLVED")
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
                            for t in history],
            "fills": fills,
            "anomalies": [{"kind": a.kind, "detail": a.detail} for a in anomalies],
            "final_state": status.state.value, "unknown": unknown})
    header = {"provider (source)": source, "account": account_id, "range": f"{first} .. {last} (target sessions)" if rows else "none (no orders)",
              "cutoff (latest recorded order time)": _iso(cutoff) if cutoff is not None else "none (no orders)",
              "code version": ", ".join(sorted(code_versions)) or "not recorded",
              "calendar version": ", ".join(sorted(calendar_versions)) or "not recorded",
              "timezone": f"UTC, with exchange time {calendar.timezone}",
              "strategy versions": ", ".join(sorted(strategy_versions)) or "none",
              "decision policy": ", ".join(sorted(policy_versions)) or "none",
              "limits (risk/policy)": ", ".join(sorted(limits)) or "none",
              "fee schedule": ", ".join(sorted(fee_versions)) or "none (no fills)",
              "fill model": ", ".join(sorted(models)) or "none (no fills)", **header_extra}
    unknown = states.get(OrderState.UNKNOWN.value, 0)
    if proposals is not None:
        stops = stops_from(proposals, account_id)
    summary = {"orders": len(rows), "by final state": ", ".join(f"{k} {v}" for k, v in sorted(states.items())) or "none (no orders)",
               "filled notional (USD)": str(notional), "fees (USD)": str(fees),
               "UNKNOWN (outcome unconfirmed)": unknown,
               "UNKNOWN with no broker record at a lookup (D20)": no_record,
               "stops (projection unavailable)": "; ".join(stops) if stops is not None else "not recorded"}
    summary["stops (projection unavailable)"] = summary["stops (projection unavailable)"] or "none"
    when = cutoff if cutoff is not None else at
    latest = snapshots.latest(account_id, when) if snapshots is not None and when is not None else None
    if latest is None:
        summary["corporate-action adjustments"] = "none (no snapshot)"
    else:
        summary["corporate-action adjustments"] = f"as of the snapshot at {latest.as_of.isoformat()}: " + (", ".join(
            f"{a.kind} {a.instrument_id} {a.effective_at.date()} "
            + (f"(receivable {a.value} USD)" if a.kind == "DIVIDEND" else f"(ratio {_plain(a.value)})")
            for a in latest.adjustments or ()) or "none")
    return OrderLog(header, rows, summary)


__all__ = ["LABEL", "OrderLog", "build_order_log"]
