"""Pure reconciliation at a proven common cutoff; never executes or repairs."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from fractions import Fraction

from investment_engine.ledger.contracts import LedgerBalances, amount, identity
from investment_engine.ledger.lots import exact_decimal
from investment_engine.market.availability import check_name, check_utc
from investment_engine.oms.order_states import OrderState as S
from investment_engine.oms.orders import Fill, Order
from investment_engine.reconciliation.contracts import (
    BrokerSnapshot,
    Difference,
    ReconciliationResult,
)
from investment_engine.reconciliation.snapshots import SIM_CASH_BASIS


@dataclass(frozen=True)
class InternalOrders:
    account_id: str
    effective_at: datetime
    known_at: datetime
    broker_account_id: str
    snapshot_id: str
    prefix_ref: str
    prefix_complete: bool
    complete_through: datetime
    rows: tuple[tuple[Order,S,Decimal,tuple[Fill,...]],...]
    delivery_gaps: tuple[str,...] = ()

    def __post_init__(self):
        for name in ("account_id","broker_account_id","snapshot_id","prefix_ref"):
            check_name(getattr(self,name),name)
        for name in ("effective_at","known_at","complete_through"):
            check_utc(getattr(self,name),name)
        if not isinstance(self.prefix_complete,bool):
            raise TypeError("prefix_complete must be bool")
        rows=[]
        for order,state,filled,fills in self.rows:
            if not isinstance(order,Order) or not all(isinstance(f,Fill) for f in fills):
                raise TypeError("immutable OMS Order and Fill records required")
            amount(filled,"filled quantity",whole=True)
            if order.account_id!=self.account_id or filled>order.quantity:
                raise ValueError("OMS evidence account/quantity mismatch")
            rows.append((order,S(state),filled,tuple(fills)))
        if len({o.order_id for o,_,_,_ in rows})!=len(rows):
            raise ValueError("duplicate OMS order")
        object.__setattr__(self,"rows",tuple(sorted(rows,key=lambda r:r[0].order_id)))
        object.__setattr__(self,"delivery_gaps",tuple(self.delivery_gaps))


def _normalise(evidence):
    resting={}
    known=[]
    reasons=[]
    semantic=[]
    for order,state,filled,fills in evidence.rows:
        selected=[f for f in fills if max(f.executed_at,f.delivered_at,f.recorded_at)<=evidence.known_at
                  and f.executed_at<=evidence.effective_at]
        if any(f.order_id!=order.order_id for f in selected):
            reasons.append("accepted fill belongs to another order")
        if sum((Fraction(f.quantity) for f in selected),Fraction())!=Fraction(filled):
            reasons.append(f"OMS filled quantity lacks matching known fill details: {order.order_id}")
        known.extend(selected)
        if state in (S.UNKNOWN,S.SUBMITTING):
            reasons.append(f"unresolved order {order.order_id}: {state}")
            semantic.append((order.order_id,order.client_order_id,state.value,order.quantity,filled))
        elif state in (S.SUBMITTED,S.PARTIALLY_FILLED,S.CANCEL_PENDING):
            remaining=exact_decimal(Fraction(order.quantity)-Fraction(filled))
            if remaining<=0:
                reasons.append(f"resting order has no remaining quantity: {order.order_id}")
            normalized=(order.order_id,order.instrument_id,order.side.value,state.value,remaining)
            resting[order.client_order_id]=normalized
            semantic.append((order.client_order_id,*normalized))
        elif state is S.NEW and selected:
            reasons.append("NEW order cannot have accepted broker fills")
    if len({f.broker_fill_id for f in known})!=len(known):
        reasons.append("duplicate accepted broker fill identity")
    content=(tuple(sorted(semantic)),tuple(sorted((f.broker_fill_id,identity(f)) for f in known)))
    return resting,tuple(known),tuple(reasons),identity(content)


def oms_fingerprint(internal_orders):
    """NEW is unsubmitted; accepted execution facts and unresolved orders still count."""
    if not isinstance(internal_orders,InternalOrders):
        raise TypeError("InternalOrders required")
    return _normalise(internal_orders)[3]


def compare(account_id,*,snapshot,ledger_balances,internal_orders,known_at):
    check_utc(known_at,"known_at")
    if not isinstance(snapshot,BrokerSnapshot) or not isinstance(ledger_balances,LedgerBalances) or not isinstance(internal_orders,InternalOrders):
        raise TypeError("pinned BrokerSnapshot, LedgerBalances and InternalOrders required")
    ledger=ledger_balances
    evidence=internal_orders
    resting,fills,normalisation_reasons,oms_hash=_normalise(evidence)
    reasons=list(normalisation_reasons)
    if account_id!=snapshot.account_id or account_id!=ledger.query.account_id or account_id!=evidence.account_id:
        reasons.append("investment account identities differ")
    if snapshot.broker_account_id!=evidence.broker_account_id or snapshot.broker!="simulated" or snapshot.source!="simulated":
        reasons.append("broker/account identity is not the declared M5 simulator account")
    if snapshot.cash_basis!=SIM_CASH_BASIS or snapshot.currency!=ledger.currency:
        reasons.append("cash basis/currency is not comparable; receivables/buying power are not cash")
    if not (snapshot.effective_at==ledger.query.effective_at==evidence.effective_at==known_at
            and ledger.query.known_at==evidence.known_at==known_at and evidence.complete_through==known_at):
        reasons.append("stale or unequal economic/knowledge/source horizons")
    if snapshot.taken_at>known_at or snapshot.received_at>known_at:
        reasons.append("snapshot was not yet taken/received at cutoff")
    if evidence.snapshot_id!=snapshot.snapshot_id:
        reasons.append("worker prefix describes a different broker capture")
    if snapshot.complete is not True:
        reasons.extend(snapshot.reasons or ("broker coverage is incomplete",))
    if ledger.complete is not True:
        reasons.extend(ledger.reasons or ("accounting coverage is incomplete",))
    if not evidence.prefix_complete or evidence.delivery_gaps:
        reasons.extend(evidence.delivery_gaps or (f"worker ingestion prefix incomplete: {evidence.prefix_ref}",))
    if any(not isinstance(ref,str) or not ref for ref in snapshot.execution_refs) or len(set(snapshot.execution_refs))!=len(snapshot.execution_refs):
        reasons.append("invalid/duplicate broker execution references")
    posted={r.stored_record_id for r in ledger.sources if r.kind=="fill"}
    if any(f.fill_id not in posted for f in fills):
        reasons.append("accepted OMS fills are not yet covered by the selected ledger book")
    if reasons:
        return ReconciliationResult(account_id,known_at,ledger.query.book_id,snapshot.snapshot_id,oms_hash,
                                     "INCOMPLETE",(),tuple(dict.fromkeys(reasons)))
    differences=[]
    links=f"book {ledger.query.book_id}; snapshot {snapshot.snapshot_id}; prefix {evidence.prefix_ref}"
    if ledger.cash!=snapshot.cash:
        differences.append(Difference("cash",ledger.currency,ledger.cash,snapshot.cash,links))
    held={i:q for i,q in ledger.positions if q}
    reported={p.instrument_id:p.quantity for p in snapshot.positions if p.quantity}
    for instrument in sorted(held.keys()|reported.keys()):
        ours,theirs=held.get(instrument,Decimal(0)),reported.get(instrument,Decimal(0))
        if ours!=theirs:
            differences.append(Difference(f"position:{instrument}",f"SECURITY:{instrument}",ours,theirs,links))
    broker_orders={o.client_order_id:o for o in snapshot.open_orders}
    for client in sorted(resting.keys()|broker_orders.keys()):
        ours,theirs=resting.get(client),broker_orders.get(client)
        compatible=False
        if ours is not None and theirs is not None:
            oid,instrument,side,status,remaining=ours
            compatible=(oid,instrument,side,remaining)==(theirs.order_id,theirs.instrument_id,theirs.side,theirs.remaining)
            compatible=compatible and (theirs.status=="OPEN" or status==S.CANCEL_PENDING.value)
        if not compatible:
            differences.append(Difference(f"order:{client}","ORDER",ours,theirs,links))
    accepted={f.broker_fill_id for f in fills}
    if accepted!=set(snapshot.execution_refs):
        differences.append(Difference("executions","BROKER_FILL_ID",tuple(sorted(accepted)),tuple(sorted(snapshot.execution_refs)),links))
    return ReconciliationResult(account_id,known_at,ledger.query.book_id,snapshot.snapshot_id,oms_hash,
                                 "MISMATCH" if differences else "MATCH",tuple(differences),())
