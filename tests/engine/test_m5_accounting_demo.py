"""Hand-verifiable SYNTHETIC accounting; no historical profitability claim."""
import json
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.events.outbox import Outbox
from investment_engine.killswitch.flag import FLAG_FILE, FlagState, encode_flag
from investment_engine.ledger.service import AccountingService, SourceSelector
from investment_engine.ledger.sources import opening_bundle
from investment_engine.ledger.store import LedgerStore
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import MarketDataWriter
from investment_engine.oms.order_states import ProcessRole
from investment_engine.portfolio.reference import StoreKnowledge
from investment_engine.reconciliation.service import capture_prefix
from investment_engine.reconciliation.snapshots import BrokerSetupStore, BrokerSnapshotStore
from investment_engine.reporting.accounting import build_report
from investment_engine.simulation.run import simulate
from tests.engine.test_intent_pipeline import CAL, NOW, OWNER, SESSIONS, Env, view_for
from tests.engine.test_ledger_actions import NVDA, coverage
from tests.engine.test_raw_reference import observation
from tests.engine.test_simulated_run import Run, action

pytestmark = pytest.mark.postgres
BUY, SPLIT, DIVIDEND, SELL, FILL = (date(2024, 5, 28), date(2024, 6, 10), date(2024, 6, 11),
                                   date(2024, 6, 11), date(2024, 6, 12))


class Demo(Run):
    def __init__(self, dsn, tmp, *, command_at=NOW, missing=()):
        root = tmp / 'market'
        records = []
        for day in SESSIONS:
            if day in missing:
                continue
            price = '120.0000' if day < SPLIT else '12.0000' if day < FILL else '13.0000'
            records.append(replace(observation(day, close=price), volume=Decimal(1000000)))
        writer = MarketDataWriter(root)
        writer.write_candles(records, import_id='synthetic-daily-v1')
        writer.write_corporate_actions([action(ActionType.SPLIT, SPLIT, ratio='10'),
            action(ActionType.DIVIDEND, DIVIDEND, amount='.10')], import_id='synthetic-actions-v1')
        self.env = Env(dsn, root, reader=MarketDataReader(root), now=command_at)
        self.env.account('R2', level=2)
        self.dsn, self.flag, self.opened = dsn, tmp / 'control' / FLAG_FILE, []
        self.flag.parent.mkdir(parents=True)
        self.flag.write_text(encode_flag(FlagState(True, 1, NOW, 'owner', True, 'synthetic test')), encoding='utf-8')
        self.views = [view_for(self.env.stores, self.env.reader, BUY, 'BULLISH', tag='synthetic-buy'),
                      view_for(self.env.stores, self.env.reader, SELL, 'BEARISH', tag='synthetic-sell')]
        at = self.views[0].generated_at
        self.clock = ReplayClock(at)
        stores = self.env.stores
        self.ledger = LedgerStore(stores.db, audit=stores.audit,
            outbox=Outbox(stores.db, writer=ProcessRole.CORE, clock=self.clock), clock=self.clock,
            command_clock=self.env.clock)
        self.ledger.activate('R2', opening_lots=(),
            source_bundle=opening_bundle(stores.snapshots.starting_state('R2'), at=at), by=OWNER,
            reason='explicit synthetic accounting demonstration')
        BrokerSetupStore(stores.db, audit=stores.audit, accounts=stores.accounts, states=stores.snapshots,
            command_clock=self.env.clock).request('R2', source='yfinance', coverage_evidence=coverage(at).evidence_refs,
                by=OWNER, reason='independent synthetic broker setup')
        self.actions = self.env.reader.actions_latest('yfinance', NVDA, date(2019, 1, 1), date(2026, 12, 31))

    def service(self, db, clock):
        selector = SourceSelector(db, clock=clock, command_clock=self.env.clock, calendar=CAL, provider='yfinance',
            coverage=lambda a, t: (coverage(t),), delivered_actions=lambda a, t: tuple((v, v.received_at) for v in self.actions),
            market_root=self.env.root)
        return AccountingService(db, clock=clock, command_clock=self.env.clock, sources=selector)

    def run(self, *, buy_only=False):
        result = simulate('R2', views=self.views[:1] if buy_only else self.views, open_db=self.open_db,
            knowledge=StoreKnowledge(self.env.reader, CAL), calendar=CAL, coverage=coverage(self.clock.now()),
            flag_path=self.flag, source='yfinance', calendar_version='us-equities-2019-2026-v1',
            code_version='m5-synthetic-accounting-v1', accounting_factory=self.service)
        payload = json.loads(result.accounting_json)
        from datetime import datetime
        self.clock.advance_to(datetime.fromisoformat(payload['effective_at']))
        return result, payload


def test_exact_buy_split_dividend_sell_and_source_linked_report(pg_database, tmp_path):
    demo = Demo(pg_database, tmp_path)
    try:
        result, payload = demo.run()
        assert not result.stops and result.orders == 2
        assert payload['complete'] and payload['reconciliation_status'] == 'MATCH'
        metrics = {k: None if v is None else Decimal(v) for k, v in payload['metrics'].items()}
        assert metrics['cash'] == Decimal('100806.88')
        assert metrics['gross_realized'] == Decimal('806.88')
        assert metrics['dividend_income'] == Decimal('82')
        assert metrics['fees'] == Decimal(0)
        assert metrics['equity'] == Decimal('100888.88')
        assert metrics['net_pnl'] == Decimal('888.88')
        assert payload['positions'] == [] and payload['receivables'] == [[NVDA, '82']]
        rows = demo.orders().for_account('R2')
        fills = [f for o, _ in rows for f in demo.orders().fills(o.order_id)]
        assert [(f.quantity, f.price) for f in sorted(fills, key=lambda f: f.executed_at)] == [
            (Decimal(82), Decimal('120.06')), (Decimal(820), Decimal('12.99'))]
        assert payload['sources'] and payload['lot_matches']
        assert payload['run']['code_version'] == 'm5-synthetic-accounting-v1'
        assert payload['run']['calendar_version'] == 'us-equities-2019-2026-v1'
        assert payload['run']['fill_provenance'] and payload['run']['unknown_orders'] == []
        assert 'SIMULATED' in payload['label'] and 'NOT PROMOTED' in payload['label']
    finally:
        demo.close()


def test_identical_fresh_runs_keep_economic_ids_and_report_content(tmp_path):
    from tests.engine.conftest import maintenance_dsn, temporary_database
    outputs = []
    commands = []
    for n in range(2):
        with temporary_database(maintenance_dsn()) as dsn:
            demo = Demo(dsn, tmp_path / str(n), command_at=NOW + timedelta(days=n))
            try:
                result, _ = demo.run()
                outputs.append(result.accounting_json)
                commands.append(demo.env.clock.now())
            finally:
                demo.close()
    assert commands[0] != commands[1] and outputs[0] == outputs[1]


def test_missing_mark_and_missing_session_are_incomplete_not_invented_zero(pg_database, tmp_path):
    demo = Demo(pg_database, tmp_path)
    try:
        _, payload = demo.run(buy_only=True)
        assert not payload['complete'] and payload['metrics']['net_pnl'] is None
        assert any('mark' in r for r in payload['reasons'])
    finally:
        demo.close()


def test_absent_target_bar_is_identified_as_incomplete(pg_database, tmp_path):
    missing = CAL.next_session(BUY).date
    demo = Demo(pg_database, tmp_path, missing=(missing,))
    try:
        _, payload = demo.run(buy_only=True)
        assert not payload['complete'] and payload['run']['missing_sessions'] == [missing.isoformat()]
        assert payload['metrics']['net_pnl'] is None
        assert payload['run']['fill_provenance'] == []
    finally:
        demo.close()


def test_seeded_broker_mismatch_and_acknowledgement_never_repair_journal(pg_database, tmp_path):
    demo = Demo(pg_database, tmp_path)
    try:
        demo.run()
        stores = demo.env.stores
        service = demo.service(stores.db, demo.clock)
        at = demo.clock.now()
        original = service.snapshots.latest('R2', known_at=at)
        from investment_engine.ledger.contracts import identity
        snapshot = replace(original, cash=original.cash + Decimal(1), raw_hash=identity('seeded-cash-discrepancy'))
        worker = BrokerSnapshotStore(stores.db, role=ProcessRole.EXECUTION, audit=stores.audit,
            outbox=Outbox(stores.db, writer=ProcessRole.EXECUTION, clock=demo.clock), clock=demo.clock)
        head = service.ledger.read_head('R2', known_at=at)
        count = stores.db.fetchone('SELECT count(*) FROM ledger_entries')[0]
        worker.record(snapshot)
        worker.record_ingestion(snapshot.snapshot_id, complete=True, prefix_ref=capture_prefix(snapshot, orders=service.orders, at=at))
        assert service.synchronize('R2', at=at).status == 'MISMATCH'
        (incident,) = service.incidents.unresolved('R2')
        service.incidents.acknowledge(incident.incident_id, expected_sequence=1, by=OWNER, reason='inspect seeded discrepancy')
        assert not service.ready('R2', at).ready
        assert service.ledger.read_head('R2', known_at=at).book_id == head.book_id
        assert stores.db.fetchone('SELECT count(*) FROM ledger_entries')[0] == count
        report = build_report('R2', effective_at=at, known_at=at, book_id=head.book_id, ledger=service.ledger,
                              calendar=CAL, source='yfinance', marks={})
        assert not report.complete and 'ACKNOWLEDGED' in report.to_json()
        assert json.loads(report.to_json())['metrics']['net_pnl'] is None
    finally:
        demo.close()
