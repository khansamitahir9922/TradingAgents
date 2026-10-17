"""The audit store (architecture Part F/H; docs/tasks/M3-04.md)."""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from investment_engine.audit.events import Actor, ActorKind, AuditConflict, AuditEvent, AuditStore
from investment_engine.lineage.records import register
from investment_engine.storage.database import AppendOnlyViolation, PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg

pytestmark = pytest.mark.postgres
AT = datetime(2026, 10, 16, 12, tzinfo=UTC)
ADMIN = Actor(ActorKind.OPERATOR, "owner", "ADMIN", "LOQ")
CORE = Actor(ActorKind.PROCESS, "core-engine", None, None)


@dataclass(frozen=True)
class ProbeValue:
    """A test-registered type, decoded in a fresh process through the registry."""

    name: str
    quantity: int


register(ProbeValue)


def event(**changes) -> AuditEvent:
    values = {"actor": ADMIN, "action": "limits.publish", "target_type": "account", "target_id": "R1",
              "before": None, "after": ProbeValue("risk-1", 10), "at": AT, "business_at": None,
              "reason": "proposal D1-D9", "correlation_id": "cmd-1", "idempotency_key": "k-1"}
    values.update(changes)
    return AuditEvent(**values)


@pytest.fixture
def db(pg_database):
    conn = open_operational_pg(pg_database)
    apply_pg_schema(conn)
    yield PostgresDatabase(conn)
    conn.close()


@pytest.fixture
def store(db):
    return AuditStore(db)


def total(db) -> int:
    return db.fetchone("SELECT COUNT(*) FROM audit_events")[0]


@pytest.mark.unit
def test_an_audited_change_and_its_event_commit_or_roll_back_together(db, store):
    with pytest.raises(RuntimeError, match="the change failed"), db.transaction():
        db.execute("INSERT INTO instruments VALUES ('EQ_US_X', 'EQUITY', 'USD', 'XNAS', 'UTC', 'ACTIVE', :d, NULL)",
                   {"d": AT.date()})
        store.append(event())
        raise RuntimeError("the change failed")
    assert total(db) == 0 and db.fetchone("SELECT COUNT(*) FROM instruments")[0] == 0
    with db.transaction():
        db.execute("INSERT INTO instruments VALUES ('EQ_US_X', 'EQUITY', 'USD', 'XNAS', 'UTC', 'ACTIVE', :d, NULL)",
                   {"d": AT.date()})
        store.append(event())
    assert total(db) == 1 and db.fetchone("SELECT COUNT(*) FROM instruments")[0] == 1


@pytest.mark.unit
def test_append_needs_the_callers_managed_transaction(db, store):
    with pytest.raises(RuntimeError, match="transaction"):
        store.append(event())
    assert total(db) == 0


@pytest.mark.unit
def test_an_identical_append_is_a_no_op_and_conflicting_content_raises(db, store):
    e = event()
    with db.transaction():
        store.append(e)
        store.append(e)
    assert total(db) == 1
    other = event(reason="different")  # a different event planted under e's id
    with db.transaction():
        db.execute("INSERT INTO audit_events VALUES (:id, :at, NULL, 'OPERATOR', 'owner', 'limits.publish', "
                   "'account', 'R2', 'cmd-1', :content)",
                   {"id": "aud-planted", "at": AT, "content": __import__("zlib").compress(other.content().encode())})
    planted = replace(event(), idempotency_key="k-planted")
    object.__setattr__(planted, "event_id", "aud-planted")
    with pytest.raises(AuditConflict), db.transaction():
        store.append(planted)


@pytest.mark.unit
@pytest.mark.parametrize("statement", [
    "UPDATE audit_events SET action = 'edited.action'",
    "DELETE FROM audit_events",
    "TRUNCATE audit_events",
    "INSERT INTO audit_events SELECT * FROM audit_events ON CONFLICT DO NOTHING",
    "INSERT INTO audit_events SELECT * FROM audit_events ON CONFLICT (event_id) DO UPDATE SET action = 'x.y'",
])
def test_every_route_that_changes_history_is_refused(db, store, statement):
    with db.transaction():
        store.append(event())
    with pytest.raises(AppendOnlyViolation):
        db.execute(statement)
    assert [e.reason for e in store.for_target("account", "R1")] == ["proposal D1-D9"]


@pytest.mark.unit
def test_every_field_round_trips_and_queries_are_ordered(db, store):
    later = event(at=AT.replace(hour=13), after=ProbeValue("risk-2", 8), idempotency_key="k-2",
                  business_at=datetime(2021, 1, 4, 14, 30, tzinfo=UTC), actor=CORE)
    other = event(target_id="R2", idempotency_key="k-3")
    with db.transaction():
        for e in (later, event(), other):
            store.append(e)
    assert store.for_target("account", "R1") == [event(), later]
    back = store.for_target("account", "R1")[1]
    assert back.event_id == later.event_id and back.business_at == later.business_at and back.actor == CORE
    assert store.between(AT, AT.replace(hour=13)) == [event(), other]  # half-open: 13:00 excluded
    assert store.between(AT.replace(hour=13), AT.replace(hour=14)) == [later]


@pytest.mark.unit
def test_bad_values_are_refused():
    with pytest.raises(TypeError):
        event(after=object())  # not a codec-registered type
    with pytest.raises(ValueError):
        event(at=datetime(2026, 10, 16, 12))  # naive
    with pytest.raises(ValueError):
        event(business_at=datetime(2021, 1, 4))
    with pytest.raises(ValueError):
        event(reason="x" * 1001)
    with pytest.raises(ValueError):
        event(action="Limits Publish")
    with pytest.raises(ValueError):
        Actor(ActorKind.OPERATOR, "owner", "PRESIDENT", None)
    with pytest.raises(ValueError):
        Actor(ActorKind.PROCESS, "core-engine", "ADMIN", None)


@pytest.mark.unit
def test_ids_hash_the_content():
    assert event().event_id == event().event_id and event().event_id.startswith("aud-")
    assert event(reason="other").event_id != event().event_id
    assert replace(event(), idempotency_key="k-9").event_id != event().event_id


@pytest.mark.unit
def test_configuration_secrets_never_reach_an_event(db, store, monkeypatch):
    monkeypatch.setenv("INVESTMENT_ENGINE_PG_DSN", "host=localhost dbname=x password=S3cretAudit")
    with db.transaction():
        store.append(event())
    import zlib

    content = zlib.decompress(bytes(db.fetchone("SELECT content FROM audit_events")[0])).decode()
    assert "S3cretAudit" not in content


@pytest.mark.unit
def test_audit_is_postgresql_only(tmp_path):
    from investment_engine.storage.database import SqliteDatabase
    from investment_engine.storage.sqlite import open_operational_db

    with pytest.raises(TypeError, match="PostgreSQL"):
        AuditStore(SqliteDatabase(open_operational_db(tmp_path / "op.sqlite3")))


@pytest.mark.unit
def test_a_fresh_process_decodes_events_through_the_registry(db, store, pg_database):
    with db.transaction():
        store.append(event())
    probe = (
        "import json, os, sys\n"
        "from investment_engine.audit import registry\n"
        "registry.MODULES = ('tests.engine.test_audit',)  # what a later task's registry line does\n"
        "from investment_engine.audit.events import AuditStore\n"
        "from investment_engine.storage.database import PostgresDatabase\n"
        "from investment_engine.storage.postgres import open_operational_pg\n"
        "store = AuditStore(PostgresDatabase(open_operational_pg(os.environ['IE_PROBE_DSN'])))\n"
        "(e,) = store.for_target('account', 'R1')\n"
        "print(json.dumps([e.event_id, type(e.after).__name__, e.after.name, e.after.quantity]))\n"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120,
                         cwd=Path(__file__).parents[2], env={**os.environ, "IE_PROBE_DSN": pg_database, "PYTHONPATH": str(Path(__file__).parents[2])})
    assert out.returncode == 0, out.stderr.splitlines()[-1:]
    assert json.loads(out.stdout) == [event().event_id, "ProbeValue", "risk-1", 10]


@pytest.mark.unit
def test_m2_ids_are_unchanged_with_audit_types_registered():
    from tests.engine.test_evaluation_run_store import OLD_FORMAT, record as evaluation_record
    from tests.engine.test_lineage import record as lineage_record

    fixture = json.loads(OLD_FORMAT.read_text(encoding="utf-8"))
    assert evaluation_record().record_id == fixture["record_id"]  # the 57d4316 shape still hashes the same
    assert lineage_record().lineage_id == lineage_record().lineage_id
