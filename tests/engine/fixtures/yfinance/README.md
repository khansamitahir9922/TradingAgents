# Recorded yfinance responses (M1-12 evidence)

Recorded once on **2026-10-12, about 08:25 UTC**, with yfinance 1.7.0, for NVDA. Unit tests read these files and never the network. The values are kept **exactly as downloaded**. Nothing in them has been repaired, filled or removed; known problems are documented below instead.

## Format
Each `*.json` file holds `{"metadata": {...}, "columns": [...], "rows": [[index, ...], ...]}`.
- **`metadata`:** the call, its parameters, request and receipt times (UTC), and the yfinance, pandas and Python versions.
- **`index`:** ISO 8601, with the exchange's UTC offset.
- **Floats:** written with `repr`, so they read back exactly.

All bar requests use `auto_adjust=False, actions=False, repair=False, back_adjust=False, prepost=False`, **except** the 2021-Q1 counterexample (`nvda_1d_2021q1_with_actions.json`), which uses `actions=True` (and no `prepost`) to show that a date-filtered request reports no later splits. `nvda_actions_max.json` also uses `actions=True`; only its action rows are kept.

| File | Call | Contents |
|---|---|---|
| `nvda_splits_before.json` | `Ticker.splits` | Full split history, fetched **before** the bar downloads: 6 splits |
| `nvda_splits_after.json` | `Ticker.splits` | The same, fetched **after**: identical to `before` |
| `nvda_dividends.json` | `Ticker.dividends` | Full dividend history: 56 |
| `nvda_actions_max.json` | `history(period="max", actions=True)` | Action rows only (dividends and splits): 62 |
| `nvda_1d_2019_2026.json` | `history(start="2019-01-01", end="2026-10-10", interval="1d")` | Daily bars, 2019-01-02 – 2026-10-09: 1954 |
| `nvda_1h_730d.json` | `history(period="730d", interval="1h")` | Hourly bars, 2023-11-10 – 2026-10-09: 5054 |
| `nvda_1d_2021q1_with_actions.json` | `history(start="2021-01-04", end="2021-03-31", interval="1d", actions=True)` | A date-filtered request: **0 split events**, although splits followed in 2021 and 2024 |

The recorder was a one-off script. In implementation it becomes the `integration` recorder (M1-12), using the same calls.

## Known gaps in the hourly download (35 bar starts)
These are expected bar starts (session open plus whole hours, before the close, per the cited US equities calendar) that are **absent** from `nvda_1h_730d.json`. There are no bars on non-session days.

| Kind | Missing bar starts (America/New_York) |
|---|---|
| **Half-day closing bar** (12:30–13:00), missing on **every** half-day in coverage | 2023-11-24, 2024-07-03, 2024-11-29, 2024-12-24, 2025-07-03, 2025-11-28, 2025-12-24 (7) |
| **Partial day** | 2026-01-30: 11:30 – 15:30 (5); 2026-02-02: 09:30 – 12:30 (4) |
| **Partial or whole days** | 2026-07-10: 11:30 – 15:30 (5); 2026-07-13 and 2026-07-14: all 7 bars each (14) |

The daily file has a bar for every one of these sessions.

## Hourly against daily, on the 728 overlapping sessions
Recorded as evidence for P-H (M1-12); **not yet explained**. Hourly prices stay pending until the differences are investigated.

**Units.** Unless stated, the counts below are in **Yahoo's reported (split-adjusted) units**: **169 sessions** differ in high or low by more than $0.01. Under the split-reconstruction hypothesis, multiplying both sides by `F(d)` (10 before 2024-06-10, 1 after) and then applying $0.01 in **as-traded units** gives **181 sessions** (reproduced by Codex and Claude Code, 2026-10-12).

| Comparison | Sessions beyond $0.01 |
|---|---|
| Hourly maximum high against daily high | 93 |
| Hourly minimum low against daily low | 88 |
| First hourly open against daily open | 454 (expected to differ: the daily open is the official opening price) |
| Last hourly close against daily close | 530 (expected to differ: the daily close is the official closing price) |

The high and low differences cover **169 sessions**; 3 sessions are in both groups below. Each difference is measured beyond $0.01, from the exact stored floats.
- **An hourly extreme falls inside the daily range on 164 sessions** (173 extremes). The hourly bars miss part of the day's range: median $0.050, 90th percentile $0.66, largest $3.86.
- **An hourly extreme falls outside the daily range on 8 sessions.** Each is a single bar whose high or low stands far from its own open and close:

  | Session | Bar | Hourly | Daily | Difference |
  |---|---|---|---|---|
  | 2023-12-11 | 12:30 | low 45.588 | low 45.830 | −0.242 |
  | 2024-04-22 | 10:30 | low 76.200 | low 76.400 | −0.200 |
  | 2024-05-06 | 10:30 | low 88.789 | low 89.055 | −0.266 |
  | 2025-02-06 | 14:30 | low 124.830 | low 125.210 | −0.380 |
  | 2025-03-25 | 12:30 | high 121.410 | high 121.290 | +0.120 |
  | 2026-02-09 | 14:30 | high **198.725** (O 191.005, C 189.900) | high 193.660 | **+5.065** |
  | 2026-07-16 | 11:30 | high 212.500 | high 211.080 | +1.420 |
  | 2026-08-25 | 13:30 | low 208.480 | low 210.110 | −1.630 |

### Investigation (2026-10-12, for M1-12 v0.3.2)
Read from the saved files only; the downloaded values are unchanged.
- **Auction prints explain few inside differences.** Of the 173 inside extremes, only **7** sit on a daily extreme equal to the official open or close (5 highs, 2 lows), where the hourly bars could have missed an auction print.
- **Missing bars explain 7 sessions:** 2023-11-24, 2024-12-24, 2025-11-28, 2025-12-24, 2026-01-30, 2026-02-02 and 2026-07-10 (see "Known gaps").
- **About 150 inside sessions remain unexplained.** The largest are 2025-04-10 (low, $3.86), 2024-09-04 (high, $3.28), 2025-02-07 (low, $2.60) and 2025-01-10 (high, $2.245), all with 7 bars present.
- **The 8 outside extremes are isolated spikes**, none on a session with missing bars. In each, one bar's high or low stands well away from its own open and close and from the official daily range.
- **2026-02-09 14:30** (high 198.725, open 191.005, close 189.900, volume 12,988,392; daily high 193.660): no independent intraday source was found. The Internet Archive holds no quote page captured after that session's close (the nearest are Nasdaq on 2026-02-10 and CNBC on 2026-02-12, both intraday), and a news search found no dated report of the day's range.

**Conclusion:** the differences are recorded but **not explained**. Plausible causes, such as trades included in intraday bars that don't update the official high and low, can't be confirmed without an independent hourly source. P-H stays **pending** and hourly volume stays **blocked**.
