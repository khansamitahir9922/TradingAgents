"""The view pipeline (Part F; Law 5; Law 9; docs/tasks/M2-07.md).

At each BAR_CLOSED D1 event of the instrument, with T = the event's received_at:
adjusted view, features and snapshot → strategies → policy → MarketView, and a
LineageRecord appended before the view is returned with its lineage id.
CANDLE_REVISED and CORPORATE_ACTION events produce no view in M2; a later view
reads the corrected data as of its own T.

Latency can't leak through a second read: every read for a view goes through
ReplayKnowledgeReader, which holds only revisions the feed has already
delivered (equal-time events follow the feed's sequence). It is an ephemeral
projection, not a store: it never changes a stored timestamp and selects the
highest delivered revision per identity that is available by T. There's no
hidden preload: a feed that starts too late gives explicit warm-up or
unavailable views. Action coverage is versioned research evidence supplied to
the run, labelled apart from observed action events.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime

from investment_engine.decision.market_view import MarketView, decide
from investment_engine.lineage.records import LineageRecord, LineageStore
from investment_engine.market.availability import check_utc
from investment_engine.market.candles import Candle, Timeframe
from investment_engine.market.corporate_actions import ActionType, CorporateAction
from investment_engine.market.data_health import HealthThresholds, _lookback, evaluate_health
from investment_engine.market.replay import ReplayEvent, ReplayFeed
from investment_engine.quant.adjusted import VerificationEvidence, bar_ref, establish_coverage
from investment_engine.quant.snapshot import build_snapshot
from investment_engine.quant.strategies.base import RuleStrategy


class ReplayKnowledgeReader:
    """Ephemeral reader projection: only revisions actually delivered by this feed."""

    def __init__(self) -> None:
        self._candles: dict[tuple, dict[int, Candle]] = {}
        self._actions: dict[tuple, dict[int, CorporateAction]] = {}
        self._delivered_until: datetime | None = None

    def accept(self, event: ReplayEvent) -> None:
        if self._delivered_until is not None and event.received_at < self._delivered_until:
            raise ValueError("events must be accepted in delivery order")
        self._delivered_until = event.received_at
        p = event.payload
        target = self._candles if isinstance(p, Candle) else self._actions
        revisions = target.setdefault(p.identity, {})
        if p.revision in revisions and revisions[p.revision] != p:
            raise ValueError(f"two different payloads for {p.identity} revision {p.revision}")
        revisions[p.revision] = p

    def _check_at(self, at: datetime) -> datetime:
        at = check_utc(at, "at")
        if self._delivered_until is None or at > self._delivered_until:
            raise ValueError(f"T {at} is later than the last delivered event; nothing after it is known")
        return at

    def candles_visible_at(self, source: str, instrument_id: str, timeframe: Timeframe, start: datetime,
                           end: datetime, at: datetime) -> list[Candle]:
        at, timeframe = self._check_at(at), Timeframe(timeframe)
        out = []
        for (s, i, tf, start_time), revisions in self._candles.items():
            if (s, i, tf) != (source, instrument_id, timeframe) or not start <= start_time < end:
                continue
            visible = [c for c in revisions.values() if c.available_from <= at]
            if visible:
                out.append(max(visible, key=lambda c: c.revision))
        return sorted(out, key=lambda c: c.start_time)

    def actions_visible_at(self, source: str, instrument_id: str, start: date, end: date, at: datetime,
                           types=None) -> list[CorporateAction]:
        at = self._check_at(at)
        wanted = None if types is None else {ActionType(t) for t in types}
        out = []
        for (s, i, action_type, ex_date), revisions in self._actions.items():
            if (s, i) != (source, instrument_id) or not start <= ex_date < end:
                continue
            if wanted is not None and action_type not in wanted:
                continue
            visible = [a for a in revisions.values() if a.available_from <= at]
            if visible:
                out.append(max(visible, key=lambda a: a.revision))
        return sorted(out, key=lambda a: (a.ex_date, list(ActionType).index(a.action_type)))


def _features(strategies: Sequence[RuleStrategy]):
    seen, out = set(), []
    for strategy in strategies:
        for d in strategy.features:
            if d.key not in seen:
                seen.add(d.key)
                out.append(d)
    return tuple(out)


def _required(strategies: Sequence[RuleStrategy]):
    out = []
    for strategy in strategies:
        for key in strategy.required_sources:
            if key not in out:
                out.append(key)
    return out


def run_views(feed: ReplayFeed, *, instrument_id: str, source: str, strategies: Sequence[RuleStrategy],
              policy_version: str, calendar, instruments, resolver, lineage_store: LineageStore,
              coverage_evidence: Sequence[VerificationEvidence], coverage_first: date, coverage_last: date,
              coverage_reason: str, calendar_version: str, code_version: str,
              thresholds: HealthThresholds | None = None,
              config: Mapping[str, object] | None = None) -> Iterator[MarketView]:
    """One view per BAR_CLOSED D1 event of `instrument_id` from `source`, each with appended lineage."""
    strategies = tuple(strategies)
    thresholds = thresholds or HealthThresholds()
    features = _features(strategies)
    required = _required(strategies)
    action_types = sorted({t for s in strategies for t in s.required_actions}, key=list(ActionType).index)
    run_config = {
        "policy_version": policy_version,
        "strategies": tuple(f"{s.name}@{s.version}" for s in strategies),
        "features": tuple(d.key for d in features),
        "required_sources": tuple(f"{k.provider}:{k.timeframe}" for k in required),
        "coverage_reason": coverage_reason,
        **dict(config or {}),
    }
    knowledge = ReplayKnowledgeReader()
    for event in feed:
        knowledge.accept(event)
        p = event.payload
        if (event.kind != "BAR_CLOSED" or p.timeframe is not Timeframe.D1
                or (p.source, p.instrument_id) != (source, instrument_id)):
            continue
        at = event.received_at
        coverage = establish_coverage(coverage_evidence, source=source, instrument_id=instrument_id,
                                      types=action_types, first=coverage_first, last=coverage_last, as_of=at,
                                      reason=coverage_reason)
        health = evaluate_health(instrument_id, required, clock=feed.clock, reader=knowledge,
                                 instruments=instruments, resolver=resolver, calendar=calendar,
                                 thresholds=thresholds)
        snapshot = build_snapshot(instrument_id, source, features, at=at, reader=knowledge, calendar=calendar,
                                  health=health, coverage=coverage)
        signals = tuple(s.evaluate(snapshot) for s in strategies)
        view = decide(signals, snapshot, strategies, policy_version=policy_version, calendar=calendar)

        # The health inputs, read by the same explicit PIT window M1-16 uses.
        health_refs = []
        sessions = _lookback(calendar, at, thresholds.lookback_sessions)
        if sessions:
            for key in required:
                health_refs += [bar_ref(c) for c in knowledge.candles_visible_at(
                    key.provider, instrument_id, key.timeframe, sessions[0].open, at, at)]
        bar_refs = tuple(sorted(set(snapshot.input_refs) | set(health_refs),
                                key=lambda r: (r.source, r.timeframe, r.start_time, r.revision)))
        record = LineageRecord(
            instrument_id=instrument_id, generated_at=at, bar_refs=bar_refs, action_refs=snapshot.action_refs,
            action_coverage=coverage, feature_versions=snapshot.feature_versions,
            strategy_versions={s.name: s.version for s in strategies}, policy_version=policy_version,
            data_health=health, health_thresholds=thresholds, snapshot=snapshot, signals=signals, decision=view,
            config=run_config, calendar_version=calendar_version, code_version=code_version)
        lineage_store.append(record)
        yield replace(view, evidence_refs=(record.lineage_id,))
