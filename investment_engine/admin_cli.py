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

import typer

from investment_engine.clock import LiveClock

accounts_app = typer.Typer(no_args_is_help=True, help="Accounts and their autonomy levels (Admin only).")
operators_app = typer.Typer(no_args_is_help=True, help="Local named operators and their roles (Admin only).")
GROUPS: dict[str, typer.Typer] = {"accounts": accounts_app, "operators": operators_app}  # later tasks add theirs


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


def _run(command: Callable[..., None]) -> None:
    """Open the Operational Database, run `command(context)`, print refusals plainly, close."""
    from investment_engine.audit.events import AuditStore
    from investment_engine.cli import _fail, _open_db
    from investment_engine.policy.accounts import AccountRegistry, NotAuthorized

    conn = None
    try:
        conn, db = _open_db(read_only=False)
        registry = AccountRegistry(db, AuditStore(db), LiveClock())
        command(registry)
    except NotAuthorized as exc:
        from investment_engine.cli import _print

        _print(f"Not authorized: {exc}. Nothing was changed.")
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
