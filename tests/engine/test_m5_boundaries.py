"""M5-13: retain process authority, source separation and immutable SQL routes."""
import ast
from pathlib import Path

import pytest

ROOT=Path(__file__).parents[2]/"investment_engine"


def test_core_accounting_never_imports_execution_or_reads_private_simulator_schema():
    for folder in ("core","ledger","reconciliation","oms","portfolio","reporting"):
        for path in (ROOT/folder).rglob("*.py"):
            tree=ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):
                    assert not (node.module or "").startswith("investment_engine.execution"),str(path)
                if isinstance(node,ast.Import):
                    assert not any(n.name.startswith("investment_engine.execution") for n in node.names),str(path)
                if isinstance(node,ast.Constant) and isinstance(node.value,str):
                    text=node.value.lower()
                    assert not any(x in text for x in ("from sim_broker.","into sim_broker.","update sim_broker.")),str(path)


def test_worker_cannot_post_journals_or_load_another_secret_file():
    readers=[]
    for path in ROOT.rglob("*.py"):
        tree=ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name=getattr(node.func,"attr",getattr(node.func,"id",""))
                if name=="load_worker_secrets":
                    readers.append(path.relative_to(ROOT).as_posix())
                if "execution" in path.relative_to(ROOT).parts:
                    assert name not in {"append_batch","post_fill","sync_account","activate"},str(path)
            if "execution" in path.relative_to(ROOT).parts and isinstance(node,ast.Constant) and isinstance(node.value,str):
                text=node.value.lower()
                assert not any(x in text for x in ("insert into ledger_","update ledger_","delete from ledger_")),str(path)
    assert readers==["execution/__main__.py"]


@pytest.mark.postgres
@pytest.mark.parametrize("table,key",[("ledger_batches","book_id"),("ledger_transactions","transaction_id"),
    ("ledger_entries","entry_id"),("ledger_source_receipts","source_id"),("ledger_activations","account_id")])
def test_sql_conflict_update_cannot_replace_committed_history(pg_database,table,key):
    from psycopg import Error

    from tests.engine.test_reconciliation_incidents import Env
    e=Env(pg_database)
    try:
        before=e.db.fetchone(f"SELECT count(*) FROM {table}")[0]
        # Even a no-op conflict update must hit the immutable table trigger.
        statement=f"INSERT INTO {table} SELECT * FROM {table} ON CONFLICT DO UPDATE SET {key}=EXCLUDED.{key}"
        # PostgreSQL requires a conflict target for DO UPDATE.
        target={"ledger_source_receipts":"book_id,source_id"}.get(table,key)
        statement=statement.replace("ON CONFLICT DO UPDATE",f"ON CONFLICT ({target}) DO UPDATE")
        with pytest.raises(Error),e.conn.transaction():
            e.conn.execute(statement)
        assert e.db.fetchone(f"SELECT count(*) FROM {table}")[0]==before
    finally:
        e.conn.close()
