"""Promotion assessment against the OPEN-09 thresholds (Law 19; architecture Part K; PRD UC-11; D21, D22;
docs/tasks/M4-10.md).

An assessment is of **one stored EvaluationRecord** (by `record_id`) and of **the decision recipe it evaluated**.
The recipe isn't in the record's `evaluation_config`, which holds only execution and cost settings. It is derived
from the decision lineage of every fold's run: `policy_version`, `strategy_versions`, `feature_versions`, `config`
and `health_thresholds`, normalized and hashed into the recipe identity. Session-specific fields never enter it, so
a later view of the same recipe has the same identity. Missing, empty or mixed lineage, or lineage for another
instrument or provider, refuses the assessment. The evidence context (record id, source, instrument, costs,
walk-forward settings, code and calendar versions) is pinned beside the recipe, not inside it.

The formulas, across the out-of-sample folds, after costs:
- **Sharpe**: each fold's daily returns from its own equity curve, starting from its initial cash (M2-10 B4),
  concatenated in fold order; mean over sample standard deviation x sqrt(252), zero risk-free rate (M2's daily
  convention, never from six-month fold returns).
- **Maximum drawdown**: on equity chained from that series, against buy-and-hold chained the same way from each
  fold's `buy_and_hold` benchmark curve over the same sessions; it passes when no worse.
- **Trades**: the total number of simulated executions across all folds, not per fold.
- **Positive folds**: the share of folds with a net return above zero.

An incomplete fold, an unavailable stitched value, or costs below the thresholds' minimum refuse the assessment.
A PASSED assessment satisfies D21 only. A PAPER account also needs shadow evidence (D22), whose comparison band
isn't specified yet, so the PAPER promotion check still fails in M4 and says which part is missing. Nothing here is
a permission.
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from importlib.resources import files

from investment_engine.lineage.records import canonical_json, register
from investment_engine.market.availability import check_utc

PASSED, FAILED, REFUSED = "PASSED", "FAILED", "REFUSED"
ACCEPTED = "ACCEPTED"  # what the gate and the policy check need; never produced in M4 (D22)


@dataclass(frozen=True)
class Thresholds:
    version: str
    min_sharpe: Decimal
    min_trades: int
    min_positive_fold_share: Decimal
    min_cost_bps_per_side: Decimal


@dataclass(frozen=True)
class Criterion:
    name: str
    value: str
    threshold: str
    passed: bool


@dataclass(frozen=True)
class Assessment:
    record_id: str
    recipe_id: str | None
    evidence: tuple[tuple[str, str], ...]  # the pinned evidence context
    thresholds_version: str
    status: str  # PASSED | FAILED | REFUSED
    criteria: tuple[Criterion, ...]
    reasons: tuple[str, ...]  # why refused or failed
    as_of: datetime
    assessment_id: str = field(init=False)

    def __post_init__(self) -> None:
        check_utc(self.as_of, "as_of")
        content = canonical_json({"record": self.record_id, "recipe": self.recipe_id, "evidence": self.evidence,
                                  "thresholds": self.thresholds_version, "status": self.status,
                                  "criteria": self.criteria, "reasons": self.reasons})
        object.__setattr__(self, "assessment_id", "pas-" + hashlib.sha256(content.encode()).hexdigest())


for _cls in (Thresholds, Criterion, Assessment):
    register(_cls)


def load_proposed_thresholds() -> dict:
    """D21 as shipped: a proposal that an Admin must publish explicitly."""
    data = json.loads(files("investment_engine.evaluation").joinpath("proposed_thresholds.json").read_text("utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def thresholds_from(version: str, values: dict) -> Thresholds:
    return Thresholds(version, Decimal(str(values["min_sharpe"])), int(values["min_trades"]),
                      Decimal(str(values["min_positive_fold_share"])), Decimal(str(values["min_cost_bps_per_side"])))


def recipe_of(lineage) -> str:
    """The recipe identity of one decision lineage record: its recipe fields only, never session data."""
    content = canonical_json({"policy_version": lineage.policy_version, "strategy_versions": lineage.strategy_versions,
                              "feature_versions": lineage.feature_versions, "config": lineage.config,
                              "health_thresholds": lineage.health_thresholds})
    return "rcp-" + hashlib.sha256(content.encode()).hexdigest()


def _daily_returns(curve, initial: Decimal) -> list[float]:
    values = [float(initial)] + [float(v) for _, v in curve]
    return [b / a - 1.0 for a, b in zip(values, values[1:], strict=False) if a]


def _max_drawdown(returns: list[float]) -> float:
    equity, peak, worst = 1.0, 1.0, 0.0
    for r in returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        worst = max(worst, 1.0 - equity / peak)
    return worst


def _sharpe(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return None if var == 0 else mean / math.sqrt(var) * math.sqrt(252)


def assess(record, *, lineage_store, thresholds: Thresholds, as_of: datetime) -> Assessment:
    folds = record.result.folds
    config = record.evaluation_config
    evidence = (("record_id", record.record_id), ("source", record.source), ("instrument", record.instrument_id),
                ("evaluation_config", config.version), ("costs_bps_per_side", str(config.costs_bps_per_side)),
                ("walk_forward", canonical_json(record.walk_forward_config)), ("code_version", record.code_version),
                ("calendar_version", record.calendar_version))
    refusals, recipes = [], set()

    def refused():
        return Assessment(record.record_id, None, evidence, thresholds.version, REFUSED, (), tuple(refusals), as_of)

    if not folds:
        refusals.append("the record has no folds")
    for n, fold in enumerate(folds, 1):
        run = fold.run
        if not run.complete:
            refusals.append(f"fold {n} is incomplete")
        if not run.lineage_refs:
            refusals.append(f"fold {n}'s run has no decision lineage")
        for ref in run.lineage_refs:
            try:
                lineage = lineage_store.get(ref)
            except KeyError:
                refusals.append(f"lineage {ref} is missing")
                continue
            if lineage.instrument_id != record.instrument_id:
                refusals.append(f"lineage {ref} is for {lineage.instrument_id}, not {record.instrument_id}")
            if lineage.snapshot.source != record.source:
                refusals.append(f"lineage {ref} is from {lineage.snapshot.source}, not {record.source}")
            recipes.add(recipe_of(lineage))
    if any(value is None for _, value in record.result.stitched):
        refusals.append("a stitched fold value is unavailable")
    if config.costs_bps_per_side < thresholds.min_cost_bps_per_side:
        refusals.append(f"costs {config.costs_bps_per_side} bps per side are below the minimum "
                        f"{thresholds.min_cost_bps_per_side}")
    if len(recipes) > 1:
        refusals.append(f"the evidence mixes {len(recipes)} recipes")
    if refusals:
        return refused()
    (recipe,) = recipes

    returns, hold_returns, trades, positive = [], [], 0, 0
    for fold in folds:
        run = fold.run
        initial = config.initial_cash
        returns += _daily_returns(run.equity_curve, initial)
        hold = next((b for b in run.benchmarks if b.name == "buy_and_hold"), None)
        if hold is None:
            refusals.append("a fold has no buy-and-hold benchmark")
            return refused()
        hold_returns += _daily_returns(hold.equity_curve, initial)
        trades += len(run.trades)
        positive += run.equity_curve[-1][1] > initial if run.equity_curve else 0
    sharpe = _sharpe(returns)
    drawdown, hold_drawdown = _max_drawdown(returns), _max_drawdown(hold_returns)
    share = Decimal(positive) / Decimal(len(folds))
    criteria = (
        Criterion("sharpe", "unavailable" if sharpe is None else f"{sharpe:.4f}", f">= {thresholds.min_sharpe}",
                  sharpe is not None and Decimal(repr(sharpe)) >= thresholds.min_sharpe),
        Criterion("max_drawdown", f"{drawdown:.4f}", f"<= buy-and-hold {hold_drawdown:.4f}", drawdown <= hold_drawdown),
        Criterion("trades", str(trades), f">= {thresholds.min_trades}", trades >= thresholds.min_trades),
        Criterion("positive_folds", f"{share:.4f}", f">= {thresholds.min_positive_fold_share}",
                  share >= thresholds.min_positive_fold_share),
    )
    failed = tuple(f"{c.name}: {c.value} (needs {c.threshold})" for c in criteria if not c.passed)
    return Assessment(record.record_id, recipe, evidence, thresholds.version, FAILED if failed else PASSED,
                      criteria, failed, as_of)


def paper_promotion_status(assessment: Assessment | None) -> str:
    """What the PAPER promotion check reports: never ACCEPTED in M4, because shadow evidence (D22) doesn't exist."""
    if assessment is None:
        return "PROMOTION NOT ASSESSED: no walk-forward assessment for this recipe (OPEN-09)"
    if assessment.status != PASSED:
        return f"walk-forward {assessment.status}: " + "; ".join(assessment.reasons)
    return "walk-forward PASSED; shadow evidence missing (D22): the shadow period and band aren't set"


class PromotionStore:
    """Published threshold versions and recorded assessments, append-only and audited (PostgreSQL, schema 0014)."""

    def __init__(self, db, audit) -> None:
        from investment_engine.storage.sqlite import port

        self._db, self._audit = port(db), audit

    def publish(self, values: dict, *, by, reason: str, at: datetime) -> Thresholds:
        from investment_engine.audit.events import AuditEvent

        at = check_utc(at, "at")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("publishing thresholds needs a reason")
        with self._db.transaction():
            self._db.lock("promotion-thresholds")
            n = self._db.fetchone("SELECT COALESCE(MAX(sequence), 0) + 1 FROM promotion_thresholds")[0]
            thresholds = thresholds_from(f"thresholds-{n}", values)
            self._db.execute("INSERT INTO promotion_thresholds VALUES (:v, :n, :content, :at, :by, :reason)",
                             {"v": thresholds.version, "n": n, "content": canonical_json(thresholds), "at": at,
                              "by": by.actor_id, "reason": reason})
            self._audit.append(AuditEvent(by, "promotion.thresholds_publish", "promotion_thresholds",
                                          thresholds.version, None, thresholds, at, None, reason,
                                          f"promotion:{thresholds.version}", f"promotion.thresholds:{n}"))
        return thresholds

    def current(self) -> Thresholds | None:
        row = self._db.fetchone("SELECT content FROM promotion_thresholds ORDER BY sequence DESC LIMIT 1")
        return None if row is None else _decode(row[0])

    def record(self, assessment: Assessment, *, by) -> Assessment:
        from investment_engine.audit.events import AuditEvent

        with self._db.transaction():
            if self._db.fetchone("SELECT 1 FROM promotion_assessments WHERE assessment_id = :id",
                                 {"id": assessment.assessment_id}) is None:
                evidence = dict(assessment.evidence)
                self._db.execute(
                    "INSERT INTO promotion_assessments VALUES (:id, :record, :recipe, :source, :instrument, "
                    ":thresholds, :status, :content, :at)",
                    {"id": assessment.assessment_id, "record": assessment.record_id, "recipe": assessment.recipe_id,
                     "source": evidence["source"], "instrument": evidence["instrument"],
                     "thresholds": assessment.thresholds_version, "status": assessment.status,
                     "content": canonical_json(assessment), "at": assessment.as_of})
                self._audit.append(AuditEvent(by, "promotion.assess", "evaluation_record", assessment.record_id,
                                              None, assessment, assessment.as_of, None, assessment.status,
                                              f"promotion:{assessment.assessment_id}",
                                              f"promotion.assess:{assessment.assessment_id}"))
        return assessment

    def for_recipe(self, recipe_id: str, *, source: str, instrument_id: str) -> Assessment | None:
        row = self._db.fetchone(
            "SELECT content FROM promotion_assessments WHERE recipe_id = :r AND source = :s AND instrument_id = :i "
            "ORDER BY assessed_at DESC, assessment_id DESC LIMIT 1", {"r": recipe_id, "s": source, "i": instrument_id})
        return None if row is None else _decode(row[0])


def _decode(text: str):
    from investment_engine.lineage.records import decode

    return decode(json.loads(text))


__all__ = ["ACCEPTED", "FAILED", "PASSED", "REFUSED", "Assessment", "Criterion", "PromotionStore", "Thresholds", "assess",
           "load_proposed_thresholds", "paper_promotion_status", "recipe_of", "thresholds_from"]
