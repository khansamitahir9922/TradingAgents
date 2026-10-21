"""Audited RESEARCH setup requests and immutable worker-origin broker snapshots."""
import json
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal

from investment_engine.audit.events import Actor, ActorKind, AuditEvent
from investment_engine.events.envelope import EventEnvelope
from investment_engine.ledger.contracts import amount, identity
from investment_engine.lineage.records import canonical_json, decode
from investment_engine.market.availability import (
    check_instrument_id,
    check_name,
    check_provider,
    check_utc,
)
from investment_engine.oms.order_states import ProcessRole
from investment_engine.policy.accounts import AccountKind, Role
from investment_engine.reconciliation.contracts import BrokerSnapshot
from investment_engine.storage.sqlite import port

SIM_CASH_BASIS = "TRADE_DATE_CASH_EXCLUDING_UNPAID_DIVIDENDS"


@dataclass(frozen=True)
class IngestionEvidence:
    account_id: str
    snapshot_id: str
    version: int
    complete: bool
    prefix_ref: str
    recorded_at: datetime

    @property
    def observation_id(self):
        return identity((self.account_id,self.snapshot_id,self.complete,self.prefix_ref,self.recorded_at))


@dataclass(frozen=True)
class SimulatedAccountSetup:
    account_id: str
    broker_account_id: str
    starting_state_id: str
    effective_at: datetime
    cash: Decimal
    currency: str
    positions: tuple[tuple[str,Decimal],...]
    source: str
    coverage_evidence: tuple[str,...]
    command_at: datetime
    actor_id: str
    reason: str

    def __post_init__(self):
        for name in ("account_id","broker_account_id","starting_state_id","actor_id","reason"):
            check_name(getattr(self,name),name)
        check_provider(self.source)
        check_utc(self.effective_at,"effective_at")
        check_utc(self.command_at,"command_at")
        amount(self.cash,"cash")
        if self.currency!="USD":
            raise ValueError("simulator setup is USD only")
        positions=tuple(sorted(self.positions))
        if len({i for i,_ in positions})!=len(positions):
            raise ValueError("duplicate setup position")
        for instrument,quantity in positions:
            check_instrument_id(instrument)
            amount(quantity,"quantity",whole=True)
            if quantity<=0:
                raise ValueError("setup positions must be positive")
        object.__setattr__(self,"positions",positions)
        for ref in self.coverage_evidence:
            check_name(ref,"coverage evidence")
        object.__setattr__(self,"coverage_evidence",tuple(sorted(self.coverage_evidence)))

    def values(self):
        return {f.name:getattr(self,f.name) for f in fields(self)}

    @property
    def setup_id(self):
        return identity({k:v for k,v in self.values().items() if k not in ("command_at","actor_id","reason")})

    def content(self):
        return canonical_json(self.values())

    @classmethod
    def from_content(cls,text):
        return cls(**decode(json.loads(text)))


class BrokerSetupStore:
    def __init__(self,db,*,audit,accounts,states,command_clock):
        self.db=port(db)
        self.audit,self.accounts,self.states,self.clock=audit,accounts,states,command_clock
        if self.db.backend!="postgresql":
            raise TypeError("broker setup requires PostgreSQL")
        if any(getattr(store,"_db",None) is not self.db for store in (audit,accounts,states)):
            raise ValueError("setup stores must share the same database port")

    def get(self,account_id):
        row=self.db.fetchone("SELECT setup_id,content FROM broker_setup_requests WHERE account_id=:a",{"a":account_id})
        if row is None:
            raise KeyError(account_id)
        value=SimulatedAccountSetup.from_content(row[1])
        if value.setup_id!=row[0]:
            raise ValueError("setup content hash mismatch")
        return value

    def request(self,account_id,*,source,coverage_evidence,by,reason):
        check_name(reason,"reason")
        with self.db.transaction():
            self.db.lock(f"account-control|{account_id}")
            self.db.lock(f"operator|{by.actor_id}")
            now=check_utc(self.clock.now(),"command time")
            self.accounts.authorize(by,(Role.ADMIN,),now)
            if self.accounts.account(account_id).kind is not AccountKind.RESEARCH:
                raise ValueError("simulator setup requires RESEARCH")
            state=self.states.starting_state(account_id)
            value=SimulatedAccountSetup(account_id,f"sim/{account_id}",state.state_id,state.effective_at,
                                         state.cash,state.currency,state.positions,source,tuple(coverage_evidence),now,by.actor_id,reason)
            saved=self.db.fetchone("SELECT setup_id FROM broker_setup_requests WHERE account_id=:a",{"a":account_id})
            if saved is not None:
                if saved[0]!=value.setup_id:
                    raise ValueError("simulator account setup is immutable")
                return self.get(account_id)
            if self.db.fetchone("SELECT 1 FROM orders WHERE account_id=:a LIMIT 1",{"a":account_id}) is not None:
                raise ValueError("setup requires an account without prior orders")
            self.db.execute("INSERT INTO broker_setup_requests (setup_id,account_id,effective_at,command_at,content) VALUES(:id,:a,:e,:c,:p)",
                             {"id":value.setup_id,"a":account_id,"e":state.effective_at,"c":now,"p":value.content()})
            self.audit.append(AuditEvent(by,"broker.setup_request","account",account_id,None,value.values(),now,
                               state.effective_at,reason,value.setup_id,value.setup_id))
            return value


class BrokerSnapshotStore:
    def __init__(self,db,*,role,audit,outbox,clock):
        self.db=port(db)
        self.role=ProcessRole(role)
        self.audit,self.outbox,self.clock=audit,outbox,clock
        if self.db.backend!="postgresql":
            raise TypeError("broker evidence requires PostgreSQL")
        if getattr(audit,"_db",None) is not self.db or getattr(outbox,"_db",None) is not self.db:
            raise ValueError("snapshot/audit/outbox must share the same database port")

    def get(self,snapshot_id):
        row=self.db.fetchone("SELECT content FROM broker_snapshots WHERE snapshot_id=:id",{"id":snapshot_id})
        if row is None:
            raise KeyError(snapshot_id)
        value=decode(json.loads(row[0]))
        if not isinstance(value,BrokerSnapshot) or value.snapshot_id!=snapshot_id:
            raise ValueError("broker snapshot content hash mismatch")
        return value

    def latest(self,account_id,*,known_at):
        row=self.db.fetchone("SELECT snapshot_id FROM broker_snapshots WHERE account_id=:a AND received_at<=:t AND recorded_at<=:t ORDER BY version DESC LIMIT 1",
                              {"a":account_id,"t":check_utc(known_at,"known_at")})
        return None if row is None else self.get(row[0])

    def record(self,value):
        if self.role is not ProcessRole.EXECUTION:
            raise PermissionError("only the Execution Worker records broker evidence")
        if not isinstance(value,BrokerSnapshot):
            raise TypeError("BrokerSnapshot required")
        now=check_utc(self.clock.now(),"recording time")
        if value.received_at>now:
            raise ValueError("snapshot receipt cannot be after the injected recording time")
        with self.db.transaction():
            self.db.lock(f"account-control|{value.account_id}")
            self.db.execute("SELECT set_config('investment_engine.process_role',:role,true)",{"role":self.role.value})
            existing=self.db.fetchone("SELECT snapshot_id FROM broker_snapshots WHERE snapshot_id=:id",{"id":value.snapshot_id})
            if existing is not None:
                return self.get(existing[0])
            row=self.db.fetchone("SELECT coalesce(max(version),0) FROM broker_snapshots WHERE account_id=:a",{"a":value.account_id})
            version=row[0]+1
            self.db.execute("INSERT INTO broker_snapshots (snapshot_id,account_id,version,effective_at,taken_at,received_at,recorded_at,content) VALUES(:id,:a,:v,:e,:t,:r,:recorded,:p)",
                             {"id":value.snapshot_id,"a":value.account_id,"v":version,"e":value.effective_at,"t":value.taken_at,
                              "r":value.received_at,"recorded":now,"p":canonical_json(value)})
            self.audit.append(AuditEvent(Actor(ActorKind.PROCESS,"execution-worker",None,None),"broker.snapshot",
                               "broker-account",value.account_id,None,value,now,value.effective_at,
                               "broker evidence captured unchanged",value.snapshot_id,value.snapshot_id))
            self.outbox.add(EventEnvelope("broker.snapshot_captured",1,"broker-account",value.account_id,version,
                                          value.effective_at,now,value.snapshot_id,None,canonical_json(value)))
        return value

    def ingestion(self,snapshot_id,*,known_at):
        row=self.db.fetchone("SELECT observation_id,account_id,snapshot_id,version,complete,prefix_ref,recorded_at "
                              "FROM broker_ingestion_observations WHERE snapshot_id=:id AND recorded_at<=:t ORDER BY version DESC LIMIT 1",
                              {"id":snapshot_id,"t":check_utc(known_at,"known_at")})
        if row is None:
            return None
        result=IngestionEvidence(*row[1:])
        if result.observation_id!=row[0]:
            raise ValueError("ingestion evidence hash mismatch")
        return result

    def record_ingestion(self,snapshot_id,*,complete,prefix_ref):
        if self.role is not ProcessRole.EXECUTION:
            raise PermissionError("only the Execution Worker records ingestion progress")
        if not isinstance(complete,bool):
            raise TypeError("complete must be bool")
        check_name(prefix_ref,"prefix_ref")
        now=check_utc(self.clock.now(),"recording time")
        snapshot=self.get(snapshot_id)
        with self.db.transaction():
            self.db.lock(f"account-control|{snapshot.account_id}")
            self.db.execute("SELECT set_config('investment_engine.process_role',:role,true)",{"role":self.role.value})
            version=self.db.fetchone("SELECT coalesce(max(version),0) FROM broker_ingestion_observations WHERE account_id=:a",{"a":snapshot.account_id})[0]+1
            value=IngestionEvidence(snapshot.account_id,snapshot_id,version,complete,prefix_ref,now)
            existing=self.db.fetchone("SELECT account_id,snapshot_id,version,complete,prefix_ref,recorded_at FROM broker_ingestion_observations WHERE observation_id=:id",
                                       {"id":value.observation_id})
            if existing is not None:
                return IngestionEvidence(*existing)
            payload={f.name:getattr(value,f.name) for f in fields(value)}
            self.db.execute("INSERT INTO broker_ingestion_observations (observation_id,account_id,snapshot_id,version,complete,prefix_ref,recorded_at) "
                             "VALUES(:id,:a,:s,:v,:c,:p,:t)",{"id":value.observation_id,"a":value.account_id,"s":snapshot_id,
                             "v":version,"c":complete,"p":prefix_ref,"t":now})
            self.audit.append(AuditEvent(Actor(ActorKind.PROCESS,"execution-worker",None,None),"broker.ingestion",
                               "broker-ingestion",value.account_id,None,payload,now,snapshot.effective_at,
                               "worker ingestion prefix, separate from vendor values",value.observation_id,value.observation_id))
            self.outbox.add(EventEnvelope("broker.ingestion_observed",1,"broker-ingestion",value.account_id,version,
                                          snapshot.effective_at,now,value.observation_id,None,canonical_json(payload)))
            return value
