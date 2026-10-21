"""Audited incident episodes; acknowledgement is never a financial repair."""
import json
from dataclasses import dataclass
from datetime import datetime

from investment_engine.audit.events import Actor, ActorKind, AuditEvent
from investment_engine.events.envelope import EventEnvelope
from investment_engine.ledger.contracts import identity
from investment_engine.lineage.records import canonical_json, decode, register
from investment_engine.market.availability import check_name, check_utc
from investment_engine.policy.accounts import AccountKind, Role
from investment_engine.reconciliation.contracts import IncidentTransition, ReconciliationResult
from investment_engine.storage.sqlite import port


class StaleIncident(ValueError):
    """A concurrent writer already changed this incident sequence."""


class StaleEvidence(ValueError):
    """A match cannot authorize resolution against newer/different current evidence."""


@dataclass(frozen=True)
class ReconciliationIncident:
    incident_id: str
    account_id: str
    opened_result_id: str
    opened_at: datetime


@dataclass(frozen=True)
class AccountingReadiness:
    ready: bool
    reason: str
    at: datetime
    result_id: str | None
    book_id: str | None
    snapshot_id: str | None
    oms_hash: str | None
    incident_ids: tuple[str,...]


for _type in (ReconciliationIncident,AccountingReadiness):
    register(_type)


class IncidentStore:
    def __init__(self,db,*,audit,outbox,accounts,clock,command_clock,current_evidence=None):
        self.db=port(db)
        self.audit,self.outbox,self.accounts=audit,outbox,accounts
        self.clock,self.command_clock,self.current=clock,command_clock,current_evidence
        if self.db.backend!="postgresql":
            raise TypeError("incidents require PostgreSQL")
        if any(getattr(s,"_db",None) is not self.db for s in (audit,outbox,accounts)):
            raise ValueError("incident/audit/outbox/account stores must share one database port")

    def get(self,incident_id):
        row=self.db.fetchone("SELECT incident_id,account_id,opened_result_id,opened_at FROM reconciliation_incidents WHERE incident_id=:id",{"id":incident_id})
        if row is None:
            raise KeyError(incident_id)
        return ReconciliationIncident(*row)

    def result(self,result_id):
        row=self.db.fetchone("SELECT content FROM reconciliation_results WHERE result_id=:id",{"id":result_id})
        if row is None:
            raise KeyError(result_id)
        result=decode(json.loads(row[0]))
        if not isinstance(result,ReconciliationResult) or result.result_id!=result_id:
            raise ValueError("comparison content hash mismatch")
        return result

    def latest(self,account_id):
        row=self.db.fetchone("SELECT result_id FROM reconciliation_results WHERE account_id=:a ORDER BY sequence DESC LIMIT 1",{"a":account_id})
        return None if row is None else self.result(row[0])

    def history(self,incident_id):
        self.get(incident_id)
        return tuple(decode(json.loads(row[0])) for row in self.db.fetchall("SELECT content FROM reconciliation_transitions WHERE incident_id=:id ORDER BY sequence",{"id":incident_id}))

    def state(self,incident_id):
        return self.history(incident_id)[-1]

    def unresolved(self,account_id):
        return tuple(ReconciliationIncident(*row) for row in self.db.fetchall(
            "SELECT i.incident_id,i.account_id,i.opened_result_id,i.opened_at FROM reconciliation_incidents i WHERE i.account_id=:a "
            "AND NOT EXISTS(SELECT 1 FROM reconciliation_transitions t WHERE t.incident_id=i.incident_id AND t.state='RESOLVED') ORDER BY i.opened_at,i.incident_id",{"a":account_id}))

    def _pins(self,account_id):
        book=self.db.fetchone("SELECT book_id FROM ledger_batches WHERE account_id=:a ORDER BY version DESC LIMIT 1",{"a":account_id})
        snapshot=self.db.fetchone("SELECT snapshot_id FROM broker_snapshots WHERE account_id=:a ORDER BY version DESC LIMIT 1",{"a":account_id})
        return (book[0] if book else None,snapshot[0] if snapshot else None)

    def _audit(self,actor,action,target,target_id,before,after,command_at,business_at,reason,key):
        self.audit.append(AuditEvent(actor,action,target,target_id,before,after,command_at,business_at,reason,key,key))

    def _append_transition(self,value,by):
        self.db.execute("INSERT INTO reconciliation_transitions (incident_id,sequence,state,result_id,actor_id,reason,command_at,business_at,content) "
                         "VALUES(:id,:s,:state,:r,:a,:reason,:c,:b,:p)",{"id":value.incident_id,"s":value.sequence,"state":value.state,
                         "r":value.result_id,"a":value.actor_id,"reason":value.reason,"c":value.command_at,"b":value.business_at,"p":canonical_json(value)})
        key=f"{value.incident_id}:{value.sequence}"
        self._audit(by,"incident."+value.state.lower(),"incident",value.incident_id,None,value,value.command_at,value.business_at,value.reason,key)
        self.outbox.add(EventEnvelope("incident.transitioned",1,"incident",value.incident_id,value.sequence,
                                      value.business_at,value.business_at,key,None,canonical_json(value)))

    def observe(self,result,*,force_incident=False):
        if not isinstance(result,ReconciliationResult):
            raise TypeError("ReconciliationResult required")
        with self.db.transaction():
            self.db.lock(f"account-control|{result.account_id}")
            saved=self.db.fetchone("SELECT result_id FROM reconciliation_results WHERE result_id=:id",{"id":result.result_id})
            if saved:
                if self.result(result.result_id)!=result:
                    raise ValueError("comparison identity conflict")
                linked=self.db.fetchone("SELECT incident_id FROM reconciliation_evidence WHERE result_id=:id LIMIT 1",{"id":result.result_id})
                return None if linked is None else self.get(linked[0])
            if result.at!=self.clock.now() or self._pins(result.account_id)!=(result.book_id,result.snapshot_id):
                raise StaleEvidence("comparison is not pinned to current processing evidence")
            version=self.db.fetchone("SELECT coalesce(max(sequence),0) FROM reconciliation_results WHERE account_id=:a",{"a":result.account_id})[0]+1
            self.db.execute("INSERT INTO reconciliation_results (result_id,account_id,sequence,at,recorded_at,book_id,snapshot_id,status,content) "
                             "VALUES(:id,:a,:s,:t,:t,:b,:snap,:status,:p)",{"id":result.result_id,"a":result.account_id,"s":version,"t":result.at,
                             "b":result.book_id,"snap":result.snapshot_id,"status":result.status,"p":canonical_json(result)})
            active=self.unresolved(result.account_id)
            incident=active[0] if active else None
            process=Actor(ActorKind.PROCESS,"core-engine",None,None)
            now=check_utc(self.command_clock.now(),"command time")
            if incident is None and (result.status=="MISMATCH" or force_incident):
                incident=ReconciliationIncident(identity((result.account_id,result.result_id)),result.account_id,result.result_id,result.at)
                self.db.lock(f"incident|{incident.incident_id}")
                self.db.execute("INSERT INTO reconciliation_incidents VALUES(:id,:a,:r,:t)",{"id":incident.incident_id,"a":incident.account_id,"r":result.result_id,"t":result.at})
                self._append_transition(IncidentTransition(incident.incident_id,result.account_id,1,"OPEN",result.result_id,
                                          "core-engine","observed "+result.status,now,result.at),process)
            if incident is not None:
                self.db.lock(f"incident|{incident.incident_id}")
                self.db.execute("INSERT INTO reconciliation_evidence VALUES(:i,:r,:t)",{"i":incident.incident_id,"r":result.result_id,"t":result.at})
            payload={"result":result,"incident":incident}
            self._audit(process,"reconciliation.observe","account",result.account_id,None,payload,now,result.at,"pinned comparison",result.result_id)
            self.outbox.add(EventEnvelope("reconciliation.observed",1,"reconciliation",result.account_id,version,
                                          result.at,result.at,result.result_id,None,canonical_json(payload)))
            return incident

    def _command(self,incident_id,*,expected_sequence,by,reason,business_at,to,match_id=None):
        check_name(reason,"reason")
        incident=self.get(incident_id)
        with self.db.transaction():
            self.db.lock(f"account-control|{incident.account_id}")
            self.db.lock(f"incident|{incident_id}")
            self.db.lock(f"operator|{by.actor_id}")
            now=check_utc(self.command_clock.now(),"command time")
            self.accounts.authorize(by,(Role.ADMIN,),now)
            account=self.accounts.account(incident.account_id)
            if account.kind is AccountKind.PAPER and business_at is not None:
                raise ValueError("PAPER incident commands cannot backdate business time")
            at=check_utc(self.clock.now() if business_at is None else business_at,"business time")
            previous=self.state(incident_id)
            if previous.sequence!=expected_sequence:
                raise StaleIncident("incident sequence changed")
            if previous.state=="RESOLVED" or (to=="ACKNOWLEDGED" and previous.state!="OPEN"):
                raise ValueError("incident state edge not allowed")
            result=self.latest(incident.account_id)
            if to=="RESOLVED":
                if result is None or result.result_id!=match_id or result.status!="MATCH" or result.at!=at:
                    raise StaleEvidence("resolution requires the latest complete MATCH at the business cutoff")
                opened=self.db.fetchone("SELECT sequence FROM reconciliation_results WHERE result_id=:r",{"r":incident.opened_result_id})[0]
                matched=self.db.fetchone("SELECT sequence FROM reconciliation_results WHERE result_id=:r",{"r":match_id})[0]
                if matched<=opened or self._pins(incident.account_id)!=(result.book_id,result.snapshot_id):
                    raise StaleEvidence("matching source pins are stale or not later than the discrepancy")
                if self.current is None or self.current(incident.account_id,at)!=result:
                    raise StaleEvidence("current locked evidence no longer agrees with the recorded match")
            if result is None:
                raise StaleEvidence("incident has no comparison evidence")
            changed=IncidentTransition(incident_id,incident.account_id,previous.sequence+1,to,result.result_id,by.actor_id,reason,now,at)
            self._append_transition(changed,by)
            return changed

    def acknowledge(self,incident_id,*,expected_sequence,by,reason,business_at=None):
        return self._command(incident_id,expected_sequence=expected_sequence,by=by,reason=reason,business_at=business_at,to="ACKNOWLEDGED")

    def resolve(self,incident_id,*,expected_sequence,match_id,by,reason,business_at=None):
        return self._command(incident_id,expected_sequence=expected_sequence,by=by,reason=reason,business_at=business_at,to="RESOLVED",match_id=match_id)

    def readiness(self,account_id,*,at):
        check_utc(at,"at")
        with self.db.transaction():
            self.db.lock(f"account-control|{account_id}")
            result=self.latest(account_id)
            active=self.unresolved(account_id)
            reason=""
            if result is None:
                reason="current comparison not recorded"
            elif active:
                reason="unresolved reconciliation incident"
            elif result.status!="MATCH" or result.at!=at or self._pins(account_id)!=(result.book_id,result.snapshot_id):
                reason="current evidence is incomplete/mismatched or changed"
            elif self.current is None or self.current(account_id,at)!=result:
                reason="fresh locked evidence is not verified"
            return AccountingReadiness(not reason,reason,at,result.result_id if result else None,result.book_id if result else None,
                                        result.snapshot_id if result else None,result.oms_hash if result else None,tuple(i.incident_id for i in active))
