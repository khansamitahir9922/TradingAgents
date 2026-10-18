"""The intents report and research setup through the CLI (docs/tasks/M3-14.md)."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from investment_engine.clock import ReplayClock
from investment_engine.config import ENV_PG_DSN
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import MarketDataWriter
from investment_engine.policy.accounts import AccountKind
from investment_engine.portfolio.reference import StoreKnowledge
from tests.engine.conftest import maintenance_dsn, temporary_database
from tests.engine.test_intent_pipeline import (
    CAL,
    NOW,
    OWNER,
    SESSIONS,
    Env,
    t_of,
    view_for,
    write_bars,
)
from tests.engine.test_raw_reference import observation, stored

pytestmark = pytest.mark.postgres
RUNNER = CliRunner()


def patch_cli(monkeypatch, dsn, data, now=NOW):
    from investment_engine import admin_cli, cli, intents_cli

    monkeypatch.setenv(ENV_PG_DSN, dsn)
    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(data))
    for module in (admin_cli, intents_cli, cli):
        monkeypatch.setattr(module, "LiveClock", lambda: ReplayClock(now))
    monkeypatch.setattr(admin_cli, "_os_user", lambda: "LOQ")

    def run(*args):
        result = RUNNER.invoke(cli.app, [str(a) for a in args])
        assert all(ord(ch) < 128 for ch in result.output), result.output  # ASCII only (rule 4)
        assert dsn not in result.output and "password" not in result.output and "dbname=" not in result.output
        return result

    return run


@pytest.fixture
def outcomes(pg_database, tmp_path, monkeypatch):
    """Accounts whose proposals cover every outcome, made through the pipeline over stored views."""
    data = tmp_path / "data"
    env = Env(pg_database, data / "market")
    env.account("R1")
    env.account("R0", level=0)
    thin = write_bars(data / "thin", SESSIONS, volume="1000")
    short = write_bars(data / "short", SESSIONS[60:66])
    records = {
        "awaiting": env.propose("R1", view_for(env.stores, env.reader, SESSIONS[60])),
        "neutral": env.propose("R1", view_for(env.stores, env.reader, SESSIONS[61], "NEUTRAL")),
        "abstain": env.propose("R1", view_for(env.stores, env.reader, SESSIONS[62], "ABSTAIN")),
        "policy": env.propose("R0", view_for(env.stores, env.reader, SESSIONS[63])),
        "reduced": env.propose("R1", view_for(env.stores, thin, SESSIONS[64], tag="thin"),
                               knowledge=StoreKnowledge(thin, CAL)),
        "risk": env.propose("R1", view_for(env.stores, short, SESSIONS[65], tag="short"),
                            knowledge=StoreKnowledge(short, CAL)),
    }
    assert [r.outcome.value for r in records.values()] == [
        "AWAITING_APPROVAL", "NO_INTENT", "NO_INTENT", "POLICY_REJECTED", "AWAITING_APPROVAL", "RISK_REJECTED"]
    yield patch_cli(monkeypatch, pg_database, data), records
    env.close()


HEADER = ("ACCOUNT R1 RESEARCH", "Level 1 (Approved paper)", "RESEARCH ACCOUNT: SIMULATED / REPLAY",
          "NO ORDERS: order management arrives in M4", "KILL SWITCH: NOT BUILT (M4)",
          "PORTFOLIO: DECLARED STARTING STATE (no ledger until M5)", "risk-1, policy-1")


@pytest.mark.unit
def test_list_shows_the_safety_header_and_every_outcome_with_its_reason(outcomes):
    run, records = outcomes
    listed = run("intents", "list", "--account", "R1")
    assert listed.exit_code == 0, listed.output
    for text in (*HEADER, "AWAITING_APPROVAL", "NO_INTENT", "NEUTRAL", "ABSTAIN", "RISK_REJECTED",
                 "volume history unavailable", records["reduced"].intent_id, "NEUTRAL: hold",
                 "ABSTAIN: required data not OK"):
        assert text in listed.output, text
    # Proposed as AWAITING_APPROVAL; a later proposal on the account expired it past its deadline (D11).
    reduced = next(line for line in listed.output.splitlines() if records["reduced"].intent_id in line)
    assert "AWAITING_APPROVAL" in reduced and "now EXPIRED" in reduced
    r0 = run("intents", "list", "--account", "R0").output
    assert "POLICY_REJECTED" in r0 and "Level 0 (Advisory)" in r0
    assert run("intents", "list", "--account", "R1").output == listed.output  # deterministic
    waiting = run("intents", "list", "--account", "R1", "--state", "AWAITING_APPROVAL").output
    assert records["awaiting"].intent_id in waiting and "NO_INTENT" not in waiting


@pytest.mark.unit
def test_show_prints_every_version_its_checks_and_the_reduction(outcomes):
    run, records = outcomes
    shown = run("intents", "show", records["reduced"].intent_id)
    assert shown.exit_code == 0, shown.output
    for text in (*HEADER, "v1 SUPERSEDED", "v2 EXPIRED", "supersedes v1", "risk: REDUCE -> 10",
                 "reduction: v1 82 -> v2 10: ", "(risk-1)", "approval deadline:", "exchange)", "lineage: ilin-",
                 "raw close of"):
        assert text in shown.output, text
    assert run("intents", "show", records["reduced"].intent_id, "--version", 2).output.count("intent ") == 1
    policy = run("intents", "show", records["policy"].intent_id).output
    assert "risk: NOT RUN (policy rejected: risk not evaluated)" in policy and "FAIL autonomy" in policy


@pytest.mark.unit
def test_unavailable_values_never_print_as_zero(outcomes):
    run, records = outcomes
    shown = run("intents", "show", records["awaiting"].intent_id).output
    assert "approved: no" in shown and "approval deadline: 20" in shown
    for absent in ("ADV 0", " 0 USD", "reference 0", "limit 0", "not set"):  # a real count may be 0
        assert absent not in shown, absent
    listed = run("intents", "list", "--account", "R1").output
    risk_line = next(line for line in listed.splitlines() if "RISK_REJECTED" in line)
    assert "unavailable" in risk_line and " 0 " not in risk_line


@pytest.mark.unit
def test_a_paper_account_shows_its_intent_rejected_for_promotion(pg_database, tmp_path, monkeypatch):
    live = t_of(SESSIONS[60])
    data = tmp_path / "data"
    env = Env(pg_database, data / "market", now=live)
    try:
        env.account("P1", kind=AccountKind.PAPER)
        view_for(env.stores, env.reader, SESSIONS[60])
        run = patch_cli(monkeypatch, pg_database, data, now=live)
        refused = run("intents", "propose", "--account", "P1", "--at", live.isoformat())
        assert refused.exit_code != 0 and "live time only" in refused.output
        proposed = run("intents", "propose", "--account", "P1")
        assert proposed.exit_code == 0, proposed.output
        for text in ("ACCOUNT P1 PAPER", "PAPER MODE", "POLICY_REJECTED", "PROMOTION NOT ASSESSED"):
            assert text in proposed.output, text
        (record,) = env.stores.proposals.for_account("P1")
        assert record.at == live and "PROMOTION NOT ASSESSED" in run("intents", "show", record.intent_id).output
    finally:
        env.close()


@pytest.mark.unit
def test_views_replay_without_local_data_writes_nothing(pg_database, tmp_path, monkeypatch):
    run = patch_cli(monkeypatch, pg_database, tmp_path / "data")
    assert run("init").exit_code == 0
    result = run("views", "replay", "--from", "2024-01-02", "--to", "2024-01-31")
    assert result.exit_code != 0 and "import-yfinance" in result.output
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg

    db = PostgresDatabase(open_operational_pg(pg_database))
    try:
        assert db.fetchone("SELECT COUNT(*) FROM lineage_records")[0] == 0
    finally:
        db.connection.close()


# ---------------------------------------------------------------- setup plus replay through the CLI only (S2)


DAYS = [s.date for s in CAL.sessions_between(date(2023, 1, 3), date(2024, 3, 28))]
T0 = "2024-03-08T21:00:00Z"  # the declared replay time of every setting
LATE, PAIRED = date(2024, 3, 12), date(2024, 3, 19)


def synthetic_store(data):
    """A steady rise, a correction of LATE delivered two sessions later, and a correction of PAIRED delivered at
    exactly the same time as the next session's bar (an equal-time pair)."""
    writer = MarketDataWriter(data / "market")
    closes = [Decimal("100") + Decimal(i) / 10 for i in range(len(DAYS))]
    writer.write_candles([replace(observation(d, close=f"{c:.4f}"), volume=Decimal("100000000"))
                          for d, c in zip(DAYS, closes, strict=True)], import_id="bars")
    late_received = CAL.session(CAL.next_session(CAL.next_session(LATE).date).date).close + timedelta(minutes=1)
    paired_received = CAL.session(CAL.next_session(PAIRED).date).close  # the next bar is available at its close
    for day, received in ((LATE, late_received), (PAIRED, paired_received)):
        close = closes[DAYS.index(day)] - Decimal("0.5")
        writer.write_candles([replace(observation(day, close=f"{close:.4f}", received=received),
                                      volume=Decimal("90000000"))], import_id=f"fix-{day}")
    reader = MarketDataReader(data / "market")
    for day, received in ((LATE, late_received), (PAIRED, paired_received)):
        (_, fixed) = stored(reader, day)
        assert fixed.revision == 2 and fixed.available_from == received  # delivered late, not backdated
    (next_bar,) = stored(reader, CAL.next_session(PAIRED).date)
    assert next_bar.available_from == paired_received  # the equal-time pair


SETUP = (["init"], ["operators", "bootstrap-admin", "OWNER"],
         ["accounts", "create", "R1", "--kind", "RESEARCH", "--operator", "OWNER", "--effective-at", T0,
          "--reason", "M3 demo"],
         ["accounts", "set-autonomy", "R1", "--level", "1", "--operator", "OWNER", "--effective-at", T0,
          "--reason", "M3 demo"],
         ["accounts", "declare-start", "R1", "--operator", "OWNER", "--effective-at", T0, "--reason", "D14 default"],
         ["limits", "publish", "R1", "--operator", "OWNER", "--effective-at", T0,
          "--reason", "proposal D1-D9, D13"],
         ["views", "replay", "--instrument", "EQ_US_NVDA", "--from", "2023-01-03", "--to", "2024-03-28"])


def setup_through_cli(run):
    for args in SETUP:
        result = run(*args)
        assert result.exit_code == 0, (args, result.output)


def stored_proposals(dsn):
    from investment_engine.oms.pipeline import ProposalStore
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg

    db = PostgresDatabase(open_operational_pg(dsn))
    try:
        return ProposalStore(db).for_account("R1")
    finally:
        db.connection.close()


@pytest.mark.unit
def test_research_setup_and_replay_through_the_cli_only(tmp_path, monkeypatch):
    outputs, proposals = [], []
    for k, now in enumerate((NOW, NOW + timedelta(days=2))):  # two fresh databases, set up on different days
        data = tmp_path / f"data{k}"
        synthetic_store(data)
        with temporary_database(maintenance_dsn()) as dsn:
            run = patch_cli(monkeypatch, dsn, data, now=now)
            setup_through_cli(run)
            proposed = run("intents", "propose", "--account", "R1", "--from", "2024-03-01", "--to", "2024-03-28")
            assert proposed.exit_code == 0, proposed.output
            listed = run("intents", "list", "--account", "R1")
            outputs.append((proposed.output, listed.output))
            proposals.append(stored_proposals(dsn))
    assert outputs[0] == outputs[1]  # byte-identical, although the setups were recorded on different days
    records = proposals[0]
    assert records == proposals[1] and len(records) == len([d for d in DAYS if date(2024, 3, 1) <= d])
    before = [r for r in records if r.at < datetime.fromisoformat(T0)]
    assert before and all(r.outcome.value == "PREREQUISITE_MISSING" for r in before)  # settings start at T0
    assert all("autonomy" in r.missing for r in before)
    after = [r for r in records if r.at >= datetime.fromisoformat(T0)]
    assert after and all(r.outcome.value != "PREREQUISITE_MISSING" for r in after)
    for text in HEADER[:6]:
        assert text in outputs[0][0], text


@pytest.mark.unit
def test_cli_proposals_match_propose_over_replay_called_directly(tmp_path, monkeypatch):
    from investment_engine import intents_cli
    from investment_engine.decision.pipeline import ReplayKnowledgeReader
    from investment_engine.events.outbox import Outbox
    from investment_engine.lineage.records import LineageStore
    from investment_engine.market.candles import Timeframe
    from investment_engine.market.corporate_actions import ActionType
    from investment_engine.market.replay import ReplayFeed
    from investment_engine.market.store.reader import MarketDataReader
    from investment_engine.oms.order_states import ProcessRole
    from investment_engine.oms.order_store import OrderStore
    from investment_engine.oms.pipeline import ControlStores, propose_over_replay
    from investment_engine.quant.adjusted import establish_coverage
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg
    from investment_engine.storage.sqlite import SqliteInstrumentRepository

    results = []
    for direct in (False, True):
        data = tmp_path / f"data-{direct}"
        synthetic_store(data)
        with temporary_database(maintenance_dsn()) as dsn:
            run = patch_cli(monkeypatch, dsn, data)
            setup_through_cli(run)
            if not direct:
                assert run("intents", "propose", "--account", "R1", "--from", "2024-03-01",
                           "--to", "2024-03-28").exit_code == 0
                results.append(stored_proposals(dsn))
                continue
            db = PostgresDatabase(open_operational_pg(dsn))
            try:
                lineage = LineageStore(db)
                views = [replace(lineage.get(i).decision, evidence_refs=(i,)) for i in lineage.ids("EQ_US_NVDA")]
                views = [v for v in views if v.generated_at.date() >= date(2024, 3, 1)]
                reader = MarketDataReader(data / "market")
                start = CAL.session(DAYS[0]).open - timedelta(days=1)  # the whole store, not the CLI's window
                feed = ReplayFeed(reader, ReplayClock(start), sources=["yfinance"], instrument_ids=["EQ_US_NVDA"],
                                  timeframes=[Timeframe.D1], start=start,
                                  end=CAL.session(DAYS[-1]).close + timedelta(hours=1))
                calendar_version, code_version = intents_cli._versions()
                stores = ControlStores.open(db, ReplayClock(NOW), instruments=SqliteInstrumentRepository(db))
                # The CLI's other inputs, as M4 gives them (Codex M4 review B6): the order store and the
                # established action coverage as of its feed's end.
                orders = OrderStore(db, role=ProcessRole.CORE, audit=stores.audit,
                                    outbox=Outbox(db, writer=ProcessRole.CORE, clock=stores.clock), clock=stores.clock)
                end = max(v.generated_at for v in views) + timedelta(microseconds=1)
                evidence, first, last, reason = intents_cli._coverage(end)
                coverage = establish_coverage(evidence, source="yfinance", instrument_id="EQ_US_NVDA",
                                              types=(ActionType.SPLIT, ActionType.DIVIDEND), first=first, last=last,
                                              as_of=end, reason=reason)
                results.append(propose_over_replay("R1", views, events=feed, stores=stores,
                                                   knowledge_reader=ReplayKnowledgeReader(), calendar=CAL,
                                                   coverage=coverage, calendar_version=calendar_version,
                                                   code_version=code_version, orders=orders))
            finally:
                db.connection.close()
    cli_records, direct_records = results
    assert [r.record_id for r in cli_records] == [r.record_id for r in direct_records]
    assert any(r.intent_id for r in cli_records)  # intents were proposed, not only missing prerequisites


@pytest.mark.unit
def test_list_and_show_open_the_database_read_only(outcomes, monkeypatch):
    from investment_engine import cli

    run, records = outcomes
    real, modes = cli._open_db, []

    def spy(*, read_only):
        modes.append(read_only)
        return real(read_only=read_only)

    monkeypatch.setattr(cli, "_open_db", spy)
    assert run("intents", "list", "--account", "R1").exit_code == 0
    assert run("intents", "show", records["awaiting"].intent_id).exit_code == 0
    assert modes == [True, True]  # rule 5: only views replay and intents propose write


@pytest.mark.unit
def test_research_at_is_the_proposal_time_with_knowledge_through_it(pg_database, tmp_path, monkeypatch):
    """Codex B5: `--at T` proposed at the view's time instead of T."""
    from investment_engine.oms.intents import IntentState
    from investment_engine.oms.pipeline import ProposalOutcome

    data = tmp_path / "data"
    env = Env(pg_database, data / "market")
    try:
        env.account("R1")
        run = patch_cli(monkeypatch, pg_database, data)

        def propose_at(day, at, tag):
            view_for(env.stores, env.reader, day, tag=tag)
            result = run("intents", "propose", "--account", "R1", "--at", at.isoformat())
            assert result.exit_code == 0, result.output
            (record,) = [r for r in env.stores.proposals.for_account("R1") if r.at == at]  # recorded at T
            return record

        def deadline(day):
            return CAL.session(CAL.next_session(day).date).open

        late = propose_at(SESSIONS[40], deadline(SESSIONS[40]) + timedelta(minutes=1), "late")
        assert late.outcome is ProposalOutcome.EXPIRED_ON_ARRIVAL  # recorded at T, past the deadline
        exact = propose_at(SESSIONS[41], deadline(SESSIONS[41]), "exact")
        assert exact.outcome is ProposalOutcome.EXPIRED_ON_ARRIVAL  # >= the deadline
        early = propose_at(SESSIONS[42], deadline(SESSIONS[42]) - timedelta(minutes=1), "early")
        assert early.outcome is ProposalOutcome.AWAITING_APPROVAL
        # A correction of an earlier bar in the volume window, delivered between the view and T, is known at T.
        fixed_day, view_day = SESSIONS[42], SESSIONS[43]
        t = t_of(view_day) + timedelta(minutes=2)
        MarketDataWriter(data / "market").write_candles(
            [replace(observation(fixed_day, close="119.0000", received=t - timedelta(minutes=1)),
                     volume=Decimal("1000000"))], import_id="fix")
        corrected = propose_at(view_day, t, "fixed")
        (lineage,) = env.stores.intent_lineage.for_intent(corrected.intent_id)
        revision = {r.start_time.date(): r.revision for r in lineage.adv_refs}
        assert revision[CAL.session(fixed_day).open.date()] == 2
        # Controls are those in force at T: Level 2 from a minute after the view.
        view_day = SESSIONS[44]
        env.stores.accounts.set_autonomy("R1", 2, by=OWNER, reason="up", effective_at=t_of(view_day) + timedelta(
            minutes=1))
        approved = propose_at(view_day, t_of(view_day) + timedelta(minutes=2), "level2")
        assert approved.outcome is ProposalOutcome.APPROVED
        assert env.stores.intents.get(approved.intent_id).state is IntentState.APPROVED
    finally:
        env.close()
