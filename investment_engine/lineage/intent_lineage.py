"""Intent lineage: why each intent version was decided (Law 18; architecture Part H; docs/tasks/M3-12.md).

One IntentLineageRecord per intent version, superseded versions included
(Codex B3). It links the view's lineage (unchanged: M2's record describes the
view), the raw reference bar, the portfolio snapshot, the volume history used,
the autonomy setting, the policy, limit and sizer versions, and the decisions
that actually ran. A check that never ran is recorded as NotRun. Its id hashes
the canonical content without command provenance; the store is append-only
like M2-07's.
"""

import dataclasses
import hashlib
import json
import zlib
from dataclasses import dataclass, field

from investment_engine.lineage.records import canonical_json, decode, register
from investment_engine.oms.intents import IntentState
from investment_engine.policy.accounts import AutonomySetting
from investment_engine.policy.decisions import PolicyDecision
from investment_engine.quant.adjusted import BarRef
from investment_engine.risk.decisions import NotRun, RiskDecision
from investment_engine.storage.sqlite import port


@dataclass(frozen=True)
class IntentLineageRecord:
    intent_id: str
    version: int
    final_state: IntentState
    view_lineage_id: str
    snapshot_id: str
    reference_bar: BarRef
    adv_refs: tuple[BarRef, ...]
    autonomy: AutonomySetting
    policy_version: str
    risk_version: str
    sizer_version: str
    policy_decision: PolicyDecision
    risk_decision: RiskDecision | NotRun
    admitted_buys_read: int | None  # the D5 count read under the admission lock (BUYs)
    calendar_version: str
    code_version: str
    lineage_id: str = field(init=False)  # "ilin-" + SHA-256 of the canonical content

    def __post_init__(self) -> None:
        object.__setattr__(self, "final_state", IntentState(self.final_state))
        object.__setattr__(self, "adv_refs", tuple(self.adv_refs))
        object.__setattr__(self, "lineage_id", "ilin-" + hashlib.sha256(self.identity().encode()).hexdigest())

    def identity(self) -> str:
        """The hashed content. The autonomy setting counts by its deterministic `setting_id`; its provenance
        (recorded_at, set_by) is stored in the record but kept out of the id, so replay setups recreated on
        different days give the same ids (docs/tasks/M3-12.md rule 9; Codex re-review S2)."""
        content = {f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.init}
        content["autonomy"] = self.autonomy.setting_id
        return canonical_json(content)


register(IntentLineageRecord)


class IntentLineageStore:
    def __init__(self, db) -> None:
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("intent lineage is PostgreSQL only (docs/tasks/M3-12.md)")

    def append(self, record: IntentLineageRecord) -> None:
        blob = canonical_json(record)
        with self._db.transaction():
            existing = self._db.fetchone("SELECT content FROM intent_lineage_records WHERE lineage_id = :id",
                                         {"id": record.lineage_id})
            if existing is not None:
                if zlib.decompress(bytes(existing[0])).decode() != blob:
                    raise ValueError(f"{record.lineage_id} is already stored with different content")
                return
            self._db.execute("INSERT INTO intent_lineage_records VALUES (:id, :intent, :version, :content)",
                             {"id": record.lineage_id, "intent": record.intent_id, "version": record.version,
                              "content": zlib.compress(blob.encode(), 6)})

    def get(self, lineage_id: str) -> IntentLineageRecord:
        row = self._db.fetchone("SELECT content FROM intent_lineage_records WHERE lineage_id = :id",
                                {"id": lineage_id})
        if row is None:
            raise KeyError(lineage_id)
        record = decode(json.loads(zlib.decompress(bytes(row[0])).decode()))
        if record.lineage_id != lineage_id:
            raise ValueError(f"stored content for {lineage_id} hashes to {record.lineage_id}")
        return record

    def for_intent(self, intent_id: str) -> list[IntentLineageRecord]:
        rows = self._db.fetchall("SELECT lineage_id FROM intent_lineage_records WHERE intent_id = :id "
                                 "ORDER BY version", {"id": intent_id})
        return [self.get(r[0]) for r in rows]
