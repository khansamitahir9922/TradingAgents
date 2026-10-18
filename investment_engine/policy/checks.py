"""The deterministic policy checks (architecture G1 step 7; Law 3; docs/tasks/M3-10.md).

Every check runs and is reported, in a fixed order, each with a plain reason;
the decision passes only if all pass:
1. autonomy: a Level 0 (advisory) account proposes no intents;
2. promotion (D15, Law 19): a PAPER account needs an accepted promotion for its
   recipe. M4-10 passes the assessment's status in (`promotion`); without one the
   M3 text stands. Nothing is ACCEPTED in M4 (D22: no shadow evidence), so every
   PAPER intent fails, saying which part is missing.
   A RESEARCH account passes: it is replay only and can never trade;
3. instrument: ACTIVE and inside its active dates on the target session;
4. restricted: not on the rules version's restricted list (D8);
5. long_only (D2): a SELL can't exceed the shares held;
6. trading_window (D7, D12): the target session is a regular session (half-days
   allowed), the order is a DAY LIMIT order and the view is daily.

Inputs are passed in: no store or clock is read, and the same inputs give an
equal decision. Missing inputs are prerequisites the pipeline handles before
sizing (Codex B3); inconsistent ones (another account's intent, another
instrument) raise rather than decide. No external or model text enters any
reason: they are fixed templates with values filled in (Laws 3, 4).
"""

from datetime import datetime

from investment_engine.market.availability import check_utc
from investment_engine.market.candles import Timeframe
from investment_engine.market.instruments import InstrumentStatus
from investment_engine.oms.intents import OrderIntent, Side
from investment_engine.policy.accounts import LEVEL_NAMES, Account, AccountKind, AutonomySetting
from investment_engine.policy.decisions import CheckResult, PolicyDecision
from investment_engine.policy.rules import PolicyRules


def check_policy(intent: OrderIntent, *, account: Account, autonomy: AutonomySetting, rules: PolicyRules,
                 instrument, snapshot, view_lineage, calendar, at: datetime,
                 promotion: str | None = None) -> PolicyDecision:
    at = check_utc(at, "at")
    if not (intent.account_id == account.account_id == autonomy.account_id == snapshot.account_id):
        raise ValueError("the intent, account, autonomy setting and snapshot must be the same account's")
    if instrument.instrument_id != intent.instrument_id:
        raise ValueError("the instrument isn't the intent's")
    if rules.version != intent.policy_version:
        raise ValueError(f"the intent was sized under {intent.policy_version}, not {rules.version}")
    session = intent.target_session
    checks = []

    level = autonomy.level
    checks.append(CheckResult("autonomy", level > 0,
                              "advisory account (Level 0): views only, no intents" if level == 0
                              else f"Level {level} ({LEVEL_NAMES[level]})"))

    versions = ", ".join(f"{k}={v}" for k, v in sorted(dict(view_lineage.strategy_versions).items())) or "none"
    if account.kind is AccountKind.PAPER:
        if promotion is None:
            checks.append(CheckResult("promotion", False, f"PROMOTION NOT ASSESSED: strategy versions {versions} "
                                                          "have no accepted promotion (OPEN-09)"))
        else:
            checks.append(CheckResult("promotion", promotion == "ACCEPTED", promotion))
    else:
        checks.append(CheckResult("promotion", True, "research account: replay only; can never trade"))

    active = (instrument.status is InstrumentStatus.ACTIVE and instrument.active_from <= session
              and (instrument.active_to is None or session < instrument.active_to))
    checks.append(CheckResult("instrument", active,
                              f"{instrument.instrument_id} is {instrument.status} on {session}" if not active
                              else f"{instrument.instrument_id} active on {session}"))

    restricted = intent.instrument_id in rules.restricted
    checks.append(CheckResult("restricted", not restricted,
                              f"{intent.instrument_id} is on the restricted list ({rules.version})" if restricted
                              else f"not restricted ({rules.version})"))

    if intent.side is Side.SELL:
        held = snapshot.held(intent.instrument_id)
        ok = intent.quantity <= held
        checks.append(CheckResult("long_only", ok, f"sell {intent.quantity} <= held {held}" if ok
                                  else f"sell {intent.quantity} > held {held}: no short selling (D2)"))
    else:
        checks.append(CheckResult("long_only", True, "a buy is long"))

    problems = []
    if not calendar.is_session(session):
        problems.append(f"{session} is not a regular session")
    if intent.order_type != rules.order_type or intent.time_in_force != rules.time_in_force:
        problems.append(f"{intent.time_in_force} {intent.order_type} isn't allowed ({rules.time_in_force} "
                        f"{rules.order_type} only)")
    if Timeframe(intent.reference_bar.timeframe).value not in rules.view_timeframes:
        problems.append(f"{intent.reference_bar.timeframe} views aren't allowed (D12)")
    checks.append(CheckResult("trading_window", not problems, "; ".join(problems) if problems
                              else f"regular session {session}, {rules.time_in_force} {rules.order_type}, daily view"))

    return PolicyDecision(intent.intent_id, intent.version, all(c.passed for c in checks), tuple(checks),
                          rules.version, level, at)
