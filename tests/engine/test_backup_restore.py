"""M5-12: restore only into fresh disposable local targets, with execution disabled."""

import pytest

from investment_engine.killswitch.flag import FLAG_FILE, KillSwitchReader
from investment_engine.storage.backups import BackupError, create_backup, restore_disposable
from tests.engine.test_backups import CLOCK, PG_BIN

pytestmark=pytest.mark.postgres


def test_disposable_restore_preserves_journal_audit_source_ids_and_all_table_hashes(pg_database,tmp_path):
    from tests.engine.conftest import maintenance_dsn, temporary_database
    from tests.engine.test_ledger_store import make_batch, open_store
    conn, db, ledger = open_store(pg_database)
    try:
        ledger.append_batch(make_batch())
        backup = tmp_path/"backup"
        create_backup(pg_database,destination=backup,market_root=tmp_path/"empty-market",clock=CLOCK,pg_bin=PG_BIN)
        with temporary_database(maintenance_dsn()) as target:
            control = tmp_path/"restore-control"
            result = restore_disposable(backup, target_dsn=target, clock=CLOCK, pg_bin=PG_BIN,
                                         execution_control_dir=control, confirm_disposable=True)
            assert result["status"] == "VERIFIED" and result["database_hashes_match"]
            assert not (control/FLAG_FILE).exists() and not KillSwitchReader(control/FLAG_FILE).read().enabled
    finally:
        conn.close()


@pytest.mark.parametrize("dsn",["host=evil.example dbname=ie_test_1234567890abcdef", "host=localhost dbname=postgres",
                                "host=localhost dbname=investment_engine", "host=localhost service=owner dbname=ie_test_1234567890abcdef"])
def test_restore_rejects_nonlocal_owner_or_ambient_service_targets_before_connect(tmp_path,dsn):
    with pytest.raises(BackupError):
        restore_disposable(tmp_path/"missing",target_dsn=dsn,clock=CLOCK,pg_bin=PG_BIN,
                             execution_control_dir=tmp_path/"control",confirm_disposable=True)


def test_nonempty_disposable_target_is_not_reset(pg_database,tmp_path):
    from tests.engine.test_ledger_store import open_store
    conn,db,_ = open_store(pg_database)
    try:
        backup = tmp_path/"backup"
        create_backup(pg_database,destination=backup,market_root=tmp_path/"empty",clock=CLOCK,pg_bin=PG_BIN)
        before = db.fetchone("SELECT count(*) FROM accounts")[0]
        with pytest.raises(BackupError):
            restore_disposable(backup,target_dsn=pg_database,clock=CLOCK,pg_bin=PG_BIN,
                                 execution_control_dir=tmp_path/"control",confirm_disposable=True)
        assert db.fetchone("SELECT count(*) FROM accounts")[0] == before
    finally:
        conn.close()


def test_restore_preserves_the_adr_realized_fee_and_equity_bridge(pg_database,tmp_path):
    from investment_engine.audit.events import AuditStore
    from investment_engine.events.outbox import Outbox
    from investment_engine.ledger.balances import balances
    from investment_engine.ledger.store import LedgerStore
    from investment_engine.oms.order_states import ProcessRole
    from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg
    from tests.engine.conftest import maintenance_dsn, temporary_database
    from tests.engine.test_accounting_reports import report
    from tests.engine.test_order_store import Env
    e = Env(pg_database)
    try:
        audit = AuditStore(e.db)
        e.snapshots = PortfolioSnapshotStore(e.db,audit,e.accounts,e.clock)
        e.ledger = LedgerStore(e.db,audit=audit,outbox=Outbox(e.db,writer=ProcessRole.CORE,clock=e.clock),clock=e.clock,command_clock=e.clock)
        before = report(e)
        backup = tmp_path/"backup"
        from investment_engine.config import market_store_dir
        from investment_engine.market.store.writer import MarketDataWriter
        from tests.engine.test_raw_reference import observation
        # The older sizing fixture references June 3 / import "bars". Supply
        # that actual synthetic stored bar; verification must not ignore it.
        MarketDataWriter(market_store_dir()).write_candles([observation(close="120.0000")], import_id="bars")
        create_backup(pg_database,destination=backup,market_root=market_store_dir(),clock=CLOCK,pg_bin=PG_BIN)
        with temporary_database(maintenance_dsn()) as target:
            result = restore_disposable(backup,target_dsn=target,clock=CLOCK,pg_bin=PG_BIN,
                execution_control_dir=tmp_path/"control",confirm_disposable=True)
            assert result["database_hashes_match"]
            with open_operational_pg(target) as conn:
                db = PostgresDatabase(conn)
                ledger = LedgerStore(db,audit=AuditStore(db),outbox=Outbox(db,writer=ProcessRole.CORE,clock=e.clock),clock=e.clock,command_clock=e.clock)
                value = balances("R1",effective_at=before.effective_at,known_at=before.known_at,book_id=before.book_id,ledger=ledger)
                assert (value.cash,value.gross_realized,value.fees)==(99478,80,2)
                assert value.cash + dict(value.positions)["EQ_US_NVDA"]*125-100000 == 228
                assert not db.fetchall("SELECT transaction_id,unit FROM ledger_entries GROUP BY transaction_id,unit HAVING sum(debit-credit)<>0")
    finally:
        e.close()
