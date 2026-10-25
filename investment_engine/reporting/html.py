"""The NVDA HTML research report (docs/tasks/M2-12.md; docs/design-principles.md, scaled to a static page).

Every value comes from the supplied MarketViews, their LineageRecords and the
EvaluationRecords, plus an optional split-adjusted price series (M2-00 bars as
of one stated time) for the chart. Each view's own decision close is adjusted
as of that view's T, so plotting those across a split would show a false
crash; the chart therefore uses one supplied basis and says which.

Honesty rules: unavailable numbers show their reason, never zero; strengths
are scales, never percentages or probabilities; every research run is
labelled SIMULATED and no order, fill, portfolio cash or ledger P&L is
claimed; paper execution, autonomy and trading status are stated as not
connected, not configured and unverifiable. All supplied text is escaped,
nothing is loaded from the network, and the output is deterministic for the
same inputs and generated time. Nothing is written anywhere: the caller
decides where to save the returned HTML.
"""

import html
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal

from investment_engine.decision.market_view import MarketView, ViewDirection
from investment_engine.evaluation.metrics import MetricValue
from investment_engine.evaluation.run_store import EvaluationRecord, check_fold_periods
from investment_engine.lineage.records import LineageStore
from investment_engine.market.availability import check_utc
from investment_engine.market.data_health import HealthStatus
from investment_engine.quant.adjusted import AdjustedBar, AdjustedBasis

SYMBOL = {ViewDirection.BULLISH: "▲", ViewDirection.BEARISH: "▼", ViewDirection.NEUTRAL: "●",
          ViewDirection.ABSTAIN: "✕"}
STATUS_SYMBOL = {HealthStatus.OK: "✓", HealthStatus.STALE: "⏱", HealthStatus.MISSING: "∅", HealthStatus.DEGRADED: "!"}
RATE_METRICS = {"direction_accuracy", "always_up_accuracy_matched", "always_up_accuracy_full", "positive_base_rate",
                "last_period_accuracy_matched", "direction_accuracy_on_last_period_sample"}
DIFF_METRICS = {"paired_accuracy_difference", "paired_last_period_difference"}
RETURN_METRICS = {"net_return", "max_drawdown"}
RECENT_VIEWS = 40

CSS = """
:root{--bg:#0d1117;--panel:#161b22;--line:#30363d;--text:#e6edf3;--muted:#8b949e;--bull:#3fb950;--bear:#f85149;
--neutral:#d29922;--abstain:#8b949e;--accent:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,
"Segoe UI",sans-serif}main{max-width:1180px;margin:0 auto;padding:20px 16px 48px}h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:0 0 12px}h3{font-size:14px;margin:16px 0 8px;color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px;margin:16px 0}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.chip{border:1px solid var(--line);border-radius:999px;
padding:3px 10px;font-size:12px;font-weight:600;letter-spacing:.02em}.chip.warn{border-color:var(--neutral);
color:var(--neutral)}.chip.sim{border-color:var(--accent);color:var(--accent)}
.headline{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.big{font-size:26px;font-weight:700}.muted{color:var(--muted)}.dir-BULLISH{color:var(--bull)}
.dir-BEARISH{color:var(--bear)}.dir-NEUTRAL{color:var(--neutral)}.dir-ABSTAIN{color:var(--abstain)}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:5px 8px;
text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}.scroll{overflow-x:auto}
code{font-size:12px;word-break:break-all}svg{width:100%;height:auto;display:block}ul{margin:4px 0;padding-left:20px}
"""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _metric(m: MetricValue | None) -> str:
    if m is None:
        return '<span class="muted">not computed</span>'
    if m.value is None:
        return f'<span class="muted">unavailable — {_e(m.unavailable_reason)}</span>'
    if m.key in RATE_METRICS:
        text = f"{m.value * 100:.1f}% (n={m.n})"
    elif m.key in DIFF_METRICS:
        text = f"{m.value * 100:+.1f} points (n={m.n})"
    elif m.key in RETURN_METRICS:
        text = f"{m.value * 100:+.2f}%"
    elif m.key == "information_coefficient":
        text = f"{m.value:+.3f} (n={m.n})"
    elif m.key == "sharpe_daily_annualized":
        text = f"{m.value:.2f} (n={m.n} daily returns)"
    else:
        text = f"{m.value:g}"
    return _e(text)


def _find(metrics, key) -> MetricValue | None:
    return next((m for m in metrics if m.key == key), None)


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def _chart(prices: Sequence[AdjustedBar], marks: Sequence[tuple]) -> str:
    if not prices:
        return '<p class="muted">No price series supplied: the chart is not drawn rather than invented.</p>'
    bases = {(p.basis, p.as_of) for p in prices}
    if len(bases) != 1:
        raise ValueError("the chart's price series must share one basis and one as-of time")
    (basis, as_of), = bases
    prices = sorted(prices, key=lambda p: p.session_date)
    width, height, pad = 1100, 320, 40
    lo, hi = min(p.close for p in prices), max(p.close for p in prices)
    span = hi - lo or 1.0
    index = {p.session_date: i for i, p in enumerate(prices)}

    def xy(i: int, v: float) -> tuple[float, float]:
        x = pad + (width - 2 * pad) * (i / max(len(prices) - 1, 1))
        y = height - pad - (height - 2 * pad) * ((v - lo) / span)
        return x, y

    points = " ".join("{:.1f},{:.1f}".format(*xy(i, p.close)) for i, p in enumerate(prices))
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Split-adjusted close with views">',
             f'<polyline fill="none" stroke="#58a6ff" stroke-width="1.2" points="{points}"/>',
             f'<text x="{pad}" y="20" fill="#8b949e" font-size="12">{_e(f"{hi:,.2f}")}</text>',
             f'<text x="{pad}" y="{height - 8}" fill="#8b949e" font-size="12">{_e(f"{lo:,.2f}")}</text>']
    colours = {ViewDirection.BULLISH: "#3fb950", ViewDirection.BEARISH: "#f85149", ViewDirection.NEUTRAL: "#d29922",
               ViewDirection.ABSTAIN: "#8b949e"}
    for session, direction, label in marks:
        if session not in index:
            continue
        x, y = xy(index[session], prices[index[session]].close)
        parts.append(f'<text x="{x:.1f}" y="{y - 6:.1f}" fill="{colours[direction]}" font-size="10" '
                     f'text-anchor="middle"><title>{_e(label)}</title>{SYMBOL[direction]}</text>')
    parts.append("</svg>")
    caption = (f"Split-adjusted close ({_e(basis)}), as of {_e(as_of.isoformat())}: prices before later splits are "
               f"scaled to the latest basis; raw as-traded prices stay stored unchanged. {len(prices)} sessions, "
               f"{prices[0].session_date} to {prices[-1].session_date}. Markers: ▲ BULLISH, ▼ BEARISH, ● NEUTRAL, "
               "✕ ABSTAIN.")
    return "".join(parts) + f'<p class="muted">{caption}</p>'


def render_research_report(views: Sequence[MarketView], runs: Sequence[EvaluationRecord], *,
                           lineage_store: LineageStore, generated_at: datetime, source: str, instrument_id: str,
                           calendars: Mapping[str, object], adjusted_closes: Sequence[AdjustedBar] = (),
                           research=None) -> str:
    """`research`, when given, is a reporting.research_view.ResearchEvidence: an advisory panel is added after the
    latest view (M6-09). Without it the report is exactly as before."""
    generated_at = check_utc(generated_at, "generated_at")
    entries = []
    for v in sorted(views, key=lambda v: v.generated_at):
        if not isinstance(v, MarketView) or v.instrument_id != instrument_id:
            raise ValueError("views must be MarketViews of the reported instrument")
        if len(v.evidence_refs) != 1:
            raise ValueError("every reported view needs its lineage id (M2-07)")
        record = lineage_store.get(v.evidence_refs[0])  # KeyError if the lineage isn't stored
        if record.snapshot.source != source:
            raise ValueError(f"view at {v.generated_at} was computed from {record.snapshot.source}, not the declared "
                             f"report source {source}")
        if v.generated_at > generated_at:
            raise ValueError(f"view at {v.generated_at} is after the report's generation time {generated_at}")
        if record.decision != MarketView(**{**v.__dict__, "evidence_refs": ()}):
            raise ValueError(f"view at {v.generated_at} doesn't match its stored lineage {v.evidence_refs[0]}")
        entries.append((v, record))
    for p in adjusted_closes:
        if p.as_of > generated_at:
            raise ValueError(f"the price series is as of {p.as_of}, after the report's generation time")
        if p.source != source or p.instrument_id != instrument_id or p.basis is not AdjustedBasis.SPLIT_ADJUSTED_AS_OF:
            raise ValueError("the price series must be this source's and instrument's split-adjusted view")
    for run in runs:
        if not isinstance(run, EvaluationRecord) or (run.source, run.instrument_id) != (source, instrument_id):
            raise ValueError("evaluation records must be for the reported source and instrument")
        if run.as_of > generated_at:
            raise ValueError(f"evaluation record {run.record_id} reads outcomes at {run.as_of}, after the report's "
                             "generation time")
        check_fold_periods(run, calendars)  # each fold is reported over exactly its sessions (R2)

    out = [f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width, initial-scale=1">'
           f'<title>{_e(instrument_id)} research report</title><style>{CSS}</style></head><body><main>']
    out.append(f"<h1>{_e(instrument_id)} daily research report</h1>")
    out.append(f'<p class="muted">Source <strong>{_e(source)}</strong> · generated '
               f'{_e(generated_at.isoformat())} (supplied time, not a live clock)</p>')
    out.append('<div class="chips">'
               '<span class="chip sim">◆ SIMULATED / REPLAY · historical research</span>'
               '<span class="chip warn">⏸ PAPER EXECUTION NOT CONNECTED</span>'
               '<span class="chip warn">⏸ AUTONOMY NOT CONFIGURED</span>'
               '<span class="chip warn">? TRADING STATUS CANNOT BE VERIFIED</span>'
               '<span class="chip warn">⧗ PROMOTION NOT ASSESSED: thresholds pending approval</span></div>')
    out.append('<p class="muted">Initial evaluation is not execution replay. No orders, actual fills, portfolio '
               'cash or ledger P&amp;L exist in this report. Strength is a heuristic scale from 0 to 1, not a '
               'probability.</p>')

    # ---------------------------------------------------------------- latest view
    out.append('<section class="panel"><h2>Latest view</h2>')
    if entries:
        v, record = entries[-1]
        out.append('<div class="headline">')
        out.append(f'<div><div class="muted">Direction</div><div class="big dir-{_e(v.direction)}">'
                   f'{SYMBOL[v.direction]} {_e(v.direction)}</div></div>')
        out.append(f'<div><div class="muted">Strength (scale, not a probability)</div><div class="big">'
                   f'{v.strength:.2f}</div></div>')
        out.append(f'<div><div class="muted">Session · T</div><div>{_e(record.snapshot.session_date)} · '
                   f'{_e(v.generated_at.isoformat())}</div></div>')
        out.append(f'<div><div class="muted">Valid until (assessed at that T)</div><div>'
                   f'{_e(v.valid_until.isoformat())}</div></div></div>')
        if v.abstain_reason:
            out.append(f'<p><strong>Abstain reason:</strong> {_e(v.abstain_reason)}</p>')
        out.append(f'<p class="muted">Regime: {_e(v.regime or "unavailable")} · horizon {_e(v.horizon)} · policy '
                   f'{_e(v.policy_version)} · lineage <code>{_e(record.lineage_id)}</code></p>')
        out.append("<h3>Data health at T</h3><ul>")
        if not v.data_health.applicability.applicable:
            out.append(f"<li>Not applicable: {_e(v.data_health.applicability.reason)}</li>")
        for s in v.data_health.sources:
            out.append(f"<li>{STATUS_SYMBOL[s.status]} {_e(s.source.provider)} {_e(s.source.timeframe)}: "
                       f"<strong>{_e(s.status)}</strong>{' — ' + _e(s.detail) if s.detail else ''}</li>")
        out.append("</ul>")
        if v.reasons:
            out.append("<h3>Rule explanations</h3><ul>" + "".join(f"<li>{_e(r)}</li>" for r in v.reasons) + "</ul>")
        backfill = sum(r.availability_basis.value == "BACKFILL_ASSUMED" for r in record.bar_refs)
        out.append(f'<p class="muted">Inputs: {len(record.bar_refs)} bar revisions ({backfill} BACKFILL_ASSUMED), '
                   f'{len(record.action_refs)} action revisions. Coverage: {_e(record.action_coverage.reason)}</p>')
    else:
        out.append('<p class="muted">No views supplied.</p>')
    out.append("</section>")
    if research is not None:
        from investment_engine.reporting.research_view import ResearchEvidence, panel_html

        if not isinstance(research, ResearchEvidence) or (
                research.context is not None and research.context.instrument_id != instrument_id):
            raise ValueError("research must be this instrument's ResearchEvidence")
        out.append(panel_html(research))

    # ---------------------------------------------------------------- chart and counts
    out.append('<section class="panel"><h2>Price and views</h2>')
    marks = [(record.snapshot.session_date, v.direction,
              f"{record.snapshot.session_date} {v.direction} strength {v.strength:.2f} (scale)")
             for v, record in entries]
    out.append(_chart(adjusted_closes, marks))
    counts = Counter(v.direction for v, _ in entries)
    out.append('<h3>Views by direction</h3><table><tr><th>Direction</th><th>Views</th></tr>')
    for d in ViewDirection:
        out.append(f"<tr><td>{SYMBOL[d]} {_e(d)}</td><td>{counts.get(d, 0)}</td></tr>")
    out.append("</table>")
    backfill_prices = sum(p.raw_ref.availability_basis.value == "BACKFILL_ASSUMED" for p in adjusted_closes)
    if adjusted_closes:
        out.append(f'<p class="muted">{backfill_prices} of {len(adjusted_closes)} charted bars are BACKFILL_ASSUMED: '
                   "their availability is an assumption from a historical download, not an observation.</p>")
    out.append("</section>")

    # ---------------------------------------------------------------- recent views
    out.append(f'<section class="panel"><h2>Recent views (last {min(RECENT_VIEWS, len(entries))} of {len(entries)})'
               '</h2><div class="scroll"><table><tr><th>Session</th><th>Direction</th><th>Strength (scale)</th>'
               '<th>Regime</th><th>Data health</th><th>Reason</th><th>Lineage</th></tr>')
    for v, record in entries[-RECENT_VIEWS:][::-1]:
        health = "; ".join(f"{STATUS_SYMBOL[s.status]} {s.source.provider} {s.source.timeframe} {s.status}"
                           for s in v.data_health.sources) or "not applicable"
        reason = v.abstain_reason or "; ".join(v.reasons)
        out.append(f'<tr id="{_e(record.lineage_id)}"><td>{_e(record.snapshot.session_date)}</td>'
                   f'<td class="dir-{_e(v.direction)}">{SYMBOL[v.direction]} {_e(v.direction)}</td>'
                   f"<td>{v.strength:.2f}</td><td>{_e(v.regime or '—')}</td><td>{_e(health)}</td>"
                   f"<td>{_e(reason)}</td><td><code>{_e(record.lineage_id[:16])}…</code></td></tr>")
    out.append("</table></div></section>")

    # ---------------------------------------------------------------- evaluation
    for run in runs:
        cfg, wf = run.evaluation_config, run.walk_forward_config
        out.append(f'<section class="panel" id="{_e(run.record_id)}"><h2>Walk-forward evaluation · '
                   f'{_e(cfg.costs_bps_per_side)} bps per side</h2>')
        out.append(f'<p class="muted">Record <code>{_e(run.record_id)}</code> · {_e(run.result.folds[0].run.label) if run.result.folds else "SIMULATED"}'
                   f" · costs {_e(cfg.costs_bps_per_side)} bps per side (combined research assumption) · initial "
                   f"cash {_e(_money(cfg.initial_cash))} {_e(cfg.currency)} · exposure {_e(cfg.exposure)} · "
                   f"dividends {_e(cfg.dividend_treatment)}</p>")
        out.append(f'<p class="muted">Windows: {wf.train_months} months train, {wf.test_months} test, '
                   f"{wf.step_months} step (provisional, {_e(wf.version)}) · target {_e(wf.label_config.basis)}, "
                   f"{wf.label_config.horizon_sessions} sessions ({_e(wf.label_config.version)}) · realised outcomes "
                   f"read at {_e(run.as_of.isoformat())} · code {_e(run.code_version)} · calendar "
                   f"{_e(run.calendar_version)}</p>")
        out.append(f'<p class="muted">Coverage: {_e(run.coverage_reason)}. Availability: '
                   f"{_e(run.backfill_assumption)}.</p>")
        out.append(f"<p><strong>{_e(run.result.promotion)}</strong></p>")
        for i, fr in enumerate(run.result.folds, start=1):
            f, d, r = fr.fold, fr.direction, fr.run
            hold = next((b for b in r.benchmarks if b.name == "buy_and_hold"), None)
            cash = next((b for b in r.benchmarks if b.name == "cash"), None)
            out.append(f"<h3>Fold {i}: test {_e(f.test_start.date())} to {_e(f.test_end.date())} (half-open); "
                       f"trained to {_e(f.train_cutoff.date())}</h3>")
            out.append(f'<p class="muted">{fr.test_views} test views: {d.directional_views} directional, '
                       f"{d.neutral_views} NEUTRAL, {d.abstain_views} ABSTAIN ({fr.warmup_views} warm-up), "
                       f"{d.unavailable_outcomes} unavailable outcomes · training labels {fr.train_labels_eligible} "
                       f"eligible, {fr.train_labels_purged} purged · run over sessions {_e(r.first)} to "
                       f"{_e(r.last)}, {'complete' if r.complete else 'INCOMPLETE'} · "
                       + (f"last-period sample: {len(d.last_period_sample)} paired, {len(d.last_period_excluded)} "
                          "excluded" if d.last_period_audit_recorded else
                          "last-period sample not recorded in this record (earlier format)") + "</p>")
            out.append('<div class="scroll"><table><tr><th>Metric</th><th>Value</th></tr>')
            for m in d.metrics:
                out.append(f'<tr data-metric="{_e(m.key)}"><td>{_e(m.key)}</td><td>{_metric(m)}</td></tr>')
            out.append("</table></div>")
            out.append('<div class="scroll"><table><tr><th>SIMULATED</th><th>Net return</th><th>Max drawdown</th>'
                       "<th>Sharpe (daily, annualised)</th><th>Ending equity</th></tr>")
            for name, metrics, curve in (("strategy", r.metrics, r.equity_curve),
                                         ("buy-and-hold", hold.metrics if hold else (), hold.equity_curve if hold else ()),
                                         ("cash (0% interest)", cash.metrics if cash else (),
                                          cash.equity_curve if cash else ())):
                ending = _money(curve[-1][1]) if curve else "unavailable"
                out.append(f"<tr><td>{_e(name)}</td><td>{_metric(_find(metrics, 'net_return'))}</td>"
                           f"<td>{_metric(_find(metrics, 'max_drawdown'))}</td>"
                           f"<td>{_metric(_find(metrics, 'sharpe_daily_annualized'))}</td><td>{_e(ending)}</td></tr>")
            out.append("</table></div>")
            trades = {m.key: m for m in r.metrics}
            out.append(f'<p class="muted">Simulated trades {_metric(trades.get("trades"))}, entries '
                       f'{_metric(trades.get("entries"))}, round trips {_metric(trades.get("round_trips"))}; '
                       f"{_e(r.ending_shares)} shares held at the end (not liquidated).</p>")
        out.append(f"<h3>{_e(run.result.stitched_label)}</h3><ul>")
        for start, value in run.result.stitched:
            text = "unavailable" if value is None else f"{value * 100:+.2f}%"
            out.append(f"<li>{_e(start.date())}: {_e(text)}</li>")
        out.append("</ul><h3>Limitations and disclosures</h3><ul>")
        notes = list(run.result.limitations)
        for fr in run.result.folds[:1]:
            notes += list(fr.run.limitations) + list(fr.direction.disclosures)
        for note in dict.fromkeys(notes):
            out.append(f"<li>{_e(note)}</li>")
        out.append("</ul></section>")

    out.append('<p class="muted">Static report: no network resources, no live state. Values trace to the '
               "lineage and evaluation record ids shown.</p></main></body></html>")
    return "".join(out)
