"""The Admin CLI's account, operator, limit and intent commands (architecture Part E; docs/tasks/M3-05 onwards).

Every change names the acting local operator (`--operator`) and a reason, and
is authorized at the real command time from a LiveClock. Commands for a
RESEARCH account act at an explicit replay time (`--effective-at`); PAPER
accounts refuse one (Codex re-review R2). Output is plain ASCII and never shows
connection details. Nothing here submits orders or touches the kill switch.

investment_engine.cli calls register(app) once; each task adds its groups to
GROUPS here. This module imports cli's helpers only inside commands, so there
is no import cycle.
"""

import getpass
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

import typer

from investment_engine.clock import LiveClock

accounts_app = typer.Typer(no_args_is_help=True, help="Accounts and their autonomy levels (Admin only).")
limits_app = typer.Typer(no_args_is_help=True, help="Versioned risk limits, policy rules and halts (Admin only).")
restricted_app = typer.Typer(no_args_is_help=True, help="The restricted list; each change is a new policy version.")
intents_app = typer.Typer(no_args_is_help=True, help="Order intents: approve, decline, expire (M3-13) and report (M3-14).")
operators_app = typer.Typer(no_args_is_help=True, help="Local named operators and their roles (Admin only).")
GROUPS: dict[str, typer.Typer] = {"accounts": accounts_app, "operators": operators_app,  # later tasks add theirs
                                  "limits": limits_app, "restricted": restricted_app,  # M3-06
                                  "intents": intents_app}  # M3-13


def register(app: typer.Typer) -> None:
    """Add every Admin CLI command group to the main app (called once by investment_engine.cli)."""
    for name, group in GROUPS.items():
        app.add_typer(group, name=name)


def _os_user() -> str | None:
    try:
        return getpass.getuser()
    except Exception:  # attribution only; never required
        return None


def _when(text: str | None) -> datetime | None:
    from investment_engine.cli import _timestamp

    return None if text is None else _timestamp(text)


def _run(command: Callable[..., None], *, limits: bool = False, database: bool = False) -> None:
    """Open the Operational Database, run `command(registry[, limit_store][, db, clock])`, print refusals plainly,
    close."""
    from investment_engine.audit.events import AuditStore
    from investment_engine.cli import _fail, _open_db
    from investment_engine.policy.accounts import AccountRegistry, NotAuthorized
    from investment_engine.risk.limits import LimitStore

    conn = None
    try:
        conn, db = _open_db(read_only=False)
        clock, audit = LiveClock(), AuditStore(db)
        registry = AccountRegistry(db, audit, clock)
        if limits and database:
            command(registry, LimitStore(db, audit, registry, clock), db, clock)
        elif limits:
            command(registry, LimitStore(db, audit, registry, clock))
        else:
            command(registry)
    except NotAuthorized as exc:
        from investment_engine.cli import _print

        _print(f"Not authorized: {exc}. Nothing was changed.")
        raise typer.Exit(1) from None
    except LookupError as exc:  # domain lookups (NoLimits, unknown ids): their text names ids, never secrets
        from investment_engine.cli import _print

        _print(f"Cannot complete command: {exc}")
        raise typer.Exit(1) from None
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc)
    finally:
        if conn is not None:
            conn.close()


def _actor(registry, operator_id: str):
    """The operator as an audit Actor, with the role the registry holds now (it is re-checked on use)."""
    from investment_engine.audit.events import Actor, ActorKind

    try:
        role = registry.operator(operator_id, registry._clock.now()).role.value
    except KeyError:
        role = "VIEWER"  # unknown operators are refused by the registry's own check
    return Actor(ActorKind.OPERATOR, operator_id, role, _os_user())


def _say(text: str) -> None:
    from investment_engine.cli import _print

    _print(text)


def _setting_line(setting, kind) -> str:
    simulated = " (simulated)" if kind == "RESEARCH" else ""
    return (f"Level {setting.level} ({setting.name}); effective {setting.effective_at.isoformat()}{simulated}; "
            f"recorded {setting.recorded_at.isoformat()}; sequence {setting.sequence}")


# ---------------------------------------------------------------- operators


@operators_app.command("bootstrap-admin")
def bootstrap_admin(operator_id: str) -> None:
    """Create the first Admin; works only while no operator exists."""
    _run(lambda r: _say(f"Operator {r.bootstrap_admin(operator_id, os_user=_os_user()).operator_id} ADMIN active "
                        "(bootstrap)"))


@operators_app.command("add")
def add_operator(operator_id: str, role: str = typer.Option(..., "--role"),
                 operator: str = typer.Option(..., "--operator"), reason: str = typer.Option(..., "--reason")) -> None:
    """Add an operator (ADMIN, TRADER or VIEWER)."""
    from investment_engine.policy.accounts import Role

    _run(lambda r: _say(f"Operator {r.add_operator(operator_id, Role(role), by=_actor(r, operator), reason=reason).operator_id} "
                        f"{role} active"))


@operators_app.command("deactivate")
def deactivate_operator(operator_id: str, operator: str = typer.Option(..., "--operator"),
                        reason: str = typer.Option(..., "--reason")) -> None:
    """Deactivate an operator; ids are never reused."""
    _run(lambda r: _say(f"Operator {r.deactivate_operator(operator_id, by=_actor(r, operator), reason=reason).operator_id} "
                        "deactivated"))


@operators_app.command("list")
def list_operators() -> None:
    """List operators with their current role and state."""
    def show(r):
        rows = r.operators()
        for o in rows:
            _say(f"{o.operator_id} {o.role} {'active' if o.active else 'inactive'} since {o.changed_at.isoformat()}")
        if not rows:
            _say("no operators; run 'operators bootstrap-admin <id>' first")
    _run(show)


# ---------------------------------------------------------------- accounts


@accounts_app.command("create")
def create_account(account_id: str, kind: str = typer.Option(..., "--kind"), currency: str = "USD",
                   operator: str = typer.Option(..., "--operator"), reason: str = typer.Option(..., "--reason"),
                   effective_at: str | None = typer.Option(None, "--effective-at")) -> None:
    """Create a RESEARCH or PAPER account at Level 0 (Advisory)."""
    def go(r):
        account = r.create_account(account_id, kind, currency, by=_actor(r, operator), reason=reason,
                                   effective_at=_when(effective_at))
        _say(f"Account {account.account_id} {account.kind} created; "
             + _setting_line(r.latest_autonomy(account.account_id), account.kind))
    _run(go)


@accounts_app.command("set-autonomy")
def set_autonomy(account_id: str, level: int = typer.Option(..., "--level"),
                 operator: str = typer.Option(..., "--operator"), reason: str = typer.Option(..., "--reason"),
                 effective_at: str | None = typer.Option(None, "--effective-at")) -> None:
    """Set an account's autonomy level (0, 1 or 2; 3 and 4 are disabled in v1)."""
    def go(r):
        setting = r.set_autonomy(account_id, level, by=_actor(r, operator), reason=reason,
                                 effective_at=_when(effective_at))
        _say(f"Account {account_id}: " + _setting_line(setting, r.account(account_id).kind))
    _run(go)


@accounts_app.command("show")
def show_account(account_id: str) -> None:
    """Show an account and its latest autonomy setting."""
    def go(r):
        account = r.account(account_id)
        _say(f"{account.account_id} {account.kind} {account.currency}; created effective "
             f"{account.effective_at.isoformat()}, recorded {account.recorded_at.isoformat()}")
        _say(_setting_line(r.latest_autonomy(account_id), account.kind))
    _run(go)


@accounts_app.command("list")
def list_accounts() -> None:
    """List accounts with their latest autonomy level."""
    def go(r):
        rows = r.accounts()
        for a in rows:
            s = r.latest_autonomy(a.account_id)
            _say(f"{a.account_id} {a.kind} Level {s.level} ({s.name})")
        if not rows:
            _say("no accounts")
    _run(go)


# ---------------------------------------------------------------- limits (M3-06)


def _limits_line(risk, policy) -> str:
    return (f"{risk.version}: position <= {risk.max_position_fraction}, gross <= {risk.max_gross_exposure_fraction}, "
            f"long only, drawdown halt at {risk.drawdown_halt_fraction}, order <= {risk.max_order_adv_fraction} of "
            f"{risk.adv_sessions}-session ADV, <= {risk.max_new_buys_per_session} new buys/session, price >= "
            f"{risk.min_price}, quantity >= {risk.min_quantity}; {policy.version}: {policy.session} "
            f"{policy.order_type} {policy.time_in_force}, band {policy.limit_band_fraction}, timeframes "
            f"{','.join(policy.view_timeframes)}, restricted {','.join(policy.restricted) or 'none'}")


@limits_app.command("publish")
def publish_limits(account_id: str, file: str | None = typer.Option(None, "--file"),
                   operator: str = typer.Option(..., "--operator"), reason: str = typer.Option(..., "--reason"),
                   effective_at: str | None = typer.Option(None, "--effective-at")) -> None:
    """Publish risk limits and policy rules from a file (default: the packaged proposed D1-D9, D13 file)."""
    from importlib.resources import files
    from pathlib import Path

    from investment_engine.risk.limits import load_limits_file

    text = (Path(file).read_text(encoding="utf-8") if file
            else files("investment_engine.risk").joinpath("proposed_limits.json").read_text(encoding="utf-8"))

    def go(registry, limits):
        risk, policy = load_limits_file(text)
        by, when = _actor(registry, operator), _when(effective_at)
        published = (limits.publish_risk(account_id, risk, by=by, reason=reason, effective_at=when),
                     limits.publish_policy(account_id, policy, by=by, reason=reason, effective_at=when))
        _say(f"Account {account_id} published " + _limits_line(*published))
    _run(go, limits=True)


@limits_app.command("show")
def show_limits(account_id: str, at: str | None = typer.Option(None, "--at")) -> None:
    """Show the limits, rules and halt state effective at a time (default: now)."""
    def go(registry, limits):
        when = _when(at) or registry._clock.now()
        _say(f"Account {account_id} at {when.isoformat()}: "
             + _limits_line(limits.risk_at(account_id, when), limits.policy_at(account_id, when)))
        halt = limits.halt_at(account_id, when)
        _say("halt: none" if halt is None else
             f"halt: {'HALTED' if halt.halted else 'cleared'} since {halt.at.isoformat()} ({halt.reason})")
    _run(go, limits=True)


@limits_app.command("clear-halt")
def clear_halt(account_id: str, operator: str = typer.Option(..., "--operator"),
               reason: str = typer.Option(..., "--reason"),
               effective_at: str | None = typer.Option(None, "--effective-at")) -> None:
    """Clear a latched drawdown halt (Admin). The account is valued at the clear time, from local data; that
    equity is recorded and the high-water mark restarts from it (D3). If it can't be valued, nothing is cleared."""
    def go(registry, limits, db, clock):
        from investment_engine.policy.accounts import AccountKind

        kind = registry.account(account_id).kind
        at = _when(effective_at) if kind is AccountKind.RESEARCH else clock.now()
        if at is None:
            raise ValueError("a RESEARCH account needs --effective-at: the replay time of the clear")
        equity = _equity_at(db, registry, clock, account_id, at)
        cleared = limits.clear_halt(account_id, by=_actor(registry, operator), reason=reason, equity_now=equity,
                                    effective_at=_when(effective_at))
        _say(f"Account {account_id}: halt cleared at {cleared.at.isoformat()} with equity {equity} USD (declared "
             "starting state, valued at the clear). The drawdown is measured from that value; if the value falls "
             "by the limit again, the halt triggers again.")
    _run(go, limits=True, database=True)


def _equity_at(db, registry, clock, account_id: str, at) -> Decimal:
    """The account's equity at `at`, from its declared start valued with local market data (no download)."""
    from investment_engine.audit.events import AuditStore
    from investment_engine.market.calendar.us_equities import load_us_equities_calendar
    from investment_engine.portfolio.reference import StoreKnowledge, Unavailable
    from investment_engine.portfolio.snapshot import PortfolioSnapshotStore, build_snapshot

    starting = PortfolioSnapshotStore(db, AuditStore(db), registry, clock).starting_state(account_id)
    calendar = load_us_equities_calendar()
    knowledge = None
    if starting.positions:  # a cash-only start needs no market data
        from investment_engine.cli import _load_store
        from investment_engine.config import market_store_dir

        reader_type, _ = _load_store()
        knowledge = StoreKnowledge(reader_type(market_store_dir()), calendar)
    built = build_snapshot(account_id, at=at, starting=starting, knowledge=knowledge, calendar=calendar,
                           coverage=None, last_clear=None, history=(), source="yfinance")
    if isinstance(built, Unavailable):
        raise ValueError(f"the halt can't be cleared: the equity at {at.isoformat()} can't be established "
                         f"({built.reason})")
    return built.equity


def _restricted(account_id: str, instrument_id: str, add: bool, operator: str, reason: str,
                effective_at: str | None) -> None:
    def go(registry, limits):
        change = limits.restrict if add else limits.unrestrict
        rules = change(account_id, instrument_id, by=_actor(registry, operator), reason=reason,
                       effective_at=_when(effective_at))
        _say(f"Account {account_id} {rules.version}: restricted {','.join(rules.restricted) or 'none'}")
    _run(go, limits=True)


@restricted_app.command("add")
def restricted_add(account_id: str, instrument_id: str, operator: str = typer.Option(..., "--operator"),
                   reason: str = typer.Option(..., "--reason"),
                   effective_at: str | None = typer.Option(None, "--effective-at")) -> None:
    """Restrict an instrument (a new policy version)."""
    _restricted(account_id, instrument_id, True, operator, reason, effective_at)


@restricted_app.command("remove")
def restricted_remove(account_id: str, instrument_id: str, operator: str = typer.Option(..., "--operator"),
                      reason: str = typer.Option(..., "--reason"),
                      effective_at: str | None = typer.Option(None, "--effective-at")) -> None:
    """Lift a restriction (a new policy version)."""
    _restricted(account_id, instrument_id, False, operator, reason, effective_at)


@accounts_app.command("declare-start")
def declare_start(account_id: str, operator: str = typer.Option(..., "--operator"),
                  reason: str = typer.Option(..., "--reason"), cash: str = "100000",
                  effective_at: str | None = typer.Option(None, "--effective-at")) -> None:
    """Declare an account's starting state (D14: cash only by default); once per account in M3."""
    from decimal import Decimal, InvalidOperation

    from investment_engine.audit.events import AuditStore
    from investment_engine.portfolio.snapshot import PortfolioSnapshotStore

    try:
        amount = Decimal(cash)
    except InvalidOperation:
        amount = None

    def go(registry):
        if amount is None:
            raise ValueError(f"cash must be a decimal number, not {cash!r}")
        store = PortfolioSnapshotStore(registry._db, AuditStore(registry._db), registry, registry._clock)
        declared = store.declare_start(account_id, by=_actor(registry, operator), reason=reason, cash=amount,
                                       effective_at=_when(effective_at))
        _say(f"Account {account_id}: DECLARED starting state {declared.cash:,.2f} USD cash, "
             f"{len(declared.positions)} positions, effective {declared.effective_at.isoformat()}; no ledger "
             "until M5")
    _run(go)


# ---------------------------------------------------------------- intents: approve, decline, expire (M3-13)


def _run_intents(command) -> None:
    """Open the Operational Database, run `command(stores, clock)`, print refusals plainly, close."""
    from investment_engine.cli import _fail, _open_db
    from investment_engine.oms.approvals import ApprovalRefused
    from investment_engine.oms.pipeline import ControlStores
    from investment_engine.policy.accounts import NotAuthorized
    from investment_engine.storage.sqlite import SqliteInstrumentRepository

    conn = None
    try:
        conn, db = _open_db(read_only=False)
        clock = LiveClock()
        command(ControlStores.open(db, clock, instruments=SqliteInstrumentRepository(db)), clock)
    except (NotAuthorized, ApprovalRefused) as exc:
        _say(f"Refused: {exc}. Nothing was approved or declined; the refusal is recorded.")
        raise typer.Exit(1) from None
    except LookupError as exc:
        _say(f"Cannot complete command: {exc}")
        raise typer.Exit(1) from None
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc)
    finally:
        if conn is not None:
            conn.close()


def _exchange(value) -> str:
    from zoneinfo import ZoneInfo

    if value is None:
        return "not set"
    return f"{value.isoformat()} ({value.astimezone(ZoneInfo('America/New_York')).isoformat()} exchange)"


def _times_for(stores, stored, at_text: str | None, clock, *, action: str, operator: str):
    """(business time, command time, label) for an intent's account (Codex re-review R2).

    The command time is read once from the LiveClock. A PAPER account acts at it, and any --at is refused,
    with the refusal audited (M3-13 rules 4 and 7). A RESEARCH account needs --at, its replay time."""
    from investment_engine.oms.approvals import ApprovalRefused, record_refusal
    from investment_engine.policy.accounts import AccountKind

    command_at = clock.now()
    kind = stores.accounts.account(stored.intent.account_id).kind
    if kind is AccountKind.PAPER:
        if at_text is not None:
            why = "a PAPER account acts at live time only; --at is refused"
            record_refusal(stores, action, stored.intent.intent_id, operator, command_at, _when(at_text), why,
                           _os_user())
            raise ApprovalRefused(why)
        return command_at, command_at, "PAPER (live time)"
    if at_text is None:
        raise ValueError("a RESEARCH account needs --at T: the replay time to act at")
    return _when(at_text), command_at, "SIMULATED (replay time)"


def _required_version(version: int | None) -> int:
    if version is None:  # checked here, not by typer, so the message stays plain ASCII
        raise ValueError("--version N is required: approval acts on one exact version (Law 12)")
    return version


def _print_version(stored, label: str) -> None:
    i = stored.intent
    _say(f"{label}: intent {i.intent_id} v{i.version}: {i.side} {i.quantity} {i.instrument_id} {i.time_in_force} "
         f"{i.order_type} limit {i.limit_price} USD; reference {i.reference_price} USD; target session "
         f"{i.target_session}" + (f"; reduced version of v{i.supersedes}" if i.supersedes else ""))
    for name, decision in (("policy", stored.policy_decision), ("risk", stored.risk_decision)):
        if decision is None or hasattr(decision, "stage"):
            _say(f"  {name}: {'not run' if decision is not None else 'not reached'}")
            continue
        outcome = getattr(decision, "outcome", None)
        _say(f"  {name}: {outcome.value if outcome is not None else ('PASSED' if decision.passed else 'FAILED')}"
             + "; " + "; ".join(f"{c.name} {'ok' if c.passed else 'FAIL'}: {c.reason}" for c in decision.checks))
    _say(f"  approval deadline {_exchange(stored.approval_deadline)}")
    _say("  No order is created in M3.")


@intents_app.command("approve")
def approve_intent(intent_id: str, version: int | None = typer.Option(None, "--version"),
                   operator: str = typer.Option(..., "--operator"), at: str | None = typer.Option(None, "--at"),
                   reason: str = typer.Option("", "--reason")) -> None:
    """Approve one exact intent version before its deadline (Admin or Trader; D11, D17)."""
    from investment_engine.market.calendar.us_equities import load_us_equities_calendar
    from investment_engine.oms.approvals import approve

    def go(stores, clock):
        stored = stores.intents.get(intent_id)
        business, command_at, label = _times_for(stores, stored, at, clock, action="intent.approve",
                                                 operator=operator)
        _print_version(stored, label)
        approved = approve(intent_id, _required_version(version), operator_id=operator, at=business, command_at=command_at,
                           stores=stores, calendar=load_us_equities_calendar(), reason=reason, os_user=_os_user())
        _say(f"APPROVED ({label}) by {approved.approved_by} at {_exchange(approved.approved_at)}; recorded "
             f"{approved.approval_recorded_at.isoformat()} (real command time); expires "
             f"{_exchange(approved.approval_expires_at)}. No order is created in M3.")
    _run_intents(go)


@intents_app.command("decline")
def decline_intent(intent_id: str, version: int | None = typer.Option(None, "--version"),
                   operator: str = typer.Option(..., "--operator"), reason: str = typer.Option("", "--reason"),
                   at: str | None = typer.Option(None, "--at")) -> None:
    """Decline one exact intent version, with a reason (Admin or Trader)."""
    from investment_engine.oms.approvals import decline

    def go(stores, clock):
        stored = stores.intents.get(intent_id)
        business, command_at, label = _times_for(stores, stored, at, clock, action="intent.decline",
                                                 operator=operator)
        _print_version(stored, label)
        decline(intent_id, _required_version(version), operator_id=operator, at=business, command_at=command_at, stores=stores,
                reason=reason, os_user=_os_user())
        _say(f"DECLINED ({label}) at {_exchange(business)}; recorded {command_at.isoformat()} (real command "
             f"time): {reason}. No order is created in M3.")
    _run_intents(go)


@intents_app.command("expire")
def expire_intents(account: str | None = typer.Option(None, "--account"), at: str | None = typer.Option(None, "--at"),
                   paper: bool = typer.Option(False, "--paper")) -> None:
    """Expire due intents of one account (RESEARCH: --at replay time) or of every PAPER account (--paper)."""
    from investment_engine.oms.pipeline import expire_due, expire_paper_due
    from investment_engine.policy.accounts import AccountKind

    def go(stores, clock):
        if paper:
            if account or at:
                raise ValueError("--paper expires every PAPER account at live time; it takes no --account or --at")
            expired = expire_paper_due(clock=clock, stores=stores)
        else:
            if not account:
                raise ValueError("name the account (--account A), or use --paper")
            kind = stores.accounts.account(account).kind
            if kind is AccountKind.PAPER and at is not None:
                raise ValueError("a PAPER account expires at live time only; --at is refused")
            if kind is AccountKind.RESEARCH and at is None:
                raise ValueError("a RESEARCH account needs --at T: its own replay time")
            expired = expire_due(account, at=_when(at), stores=stores)  # PAPER: None, the live time
        for e in expired:
            _say(f"EXPIRED intent {e.intent.intent_id} v{e.intent.version}")
        _say(f"{len(expired)} intent(s) expired")
    _run_intents(go)
