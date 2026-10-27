# M6-11 measurement: live TradingAgents runs

| | |
|---|---|
| Dates | 2026-10-26 and 2026-10-27 (UTC); NVDA (`EQ_US_NVDA`); research date 2026-10-26 for all three runs |
| Code | `m6/milestone` at `5e13b97` (recorded `code_version`); upstream TradingAgents 0.6.0 |
| Database | Dedicated local PostgreSQL database `ie_m6_live` (owner's choice), kept as evidence. It holds only these runs and their budget policies. |
| Status | **Measured.** Three owner-approved single attempts. The first two failed on Google 503 UNAVAILABLE at the first deep-model call. The third succeeded end to end: 21 requests, 132,246 / 12,078 tokens, 17 tool calls, 8 min 39 s. **The owner chose about 8 runs per day. That is enforced through the request and token caps of budget policy v5; there is no run counter** (see the end of this document). |
| Snapshot precision | Input snapshots use pandas `to_json` at its default of 10 decimal places. They are not a lossless copy (Codex re-review note). |

## Owner approvals and setup

- Owner approved one M6-11 run with their Google key and confirmed it is a free-tier key (D47 = USD 0).
- The user-level `GOOGLE_API_KEY` and `GEMINI_API_KEY` were deleted by the owner. The key now lives only in `research_worker.env`, checked by the worker's own loader without printing it.
- The first launch was refused by the D48 startup check: a user-level `ANTHROPIC_API_KEY` was visible. Nothing was claimed. Owner decision: keep that Windows variable, and strip it from the Research Worker's process environment only. Both runs below were launched that way.
- After the first attempt failed, the owner approved **one more attempt the same day with deep model `gemini-3.6-flash`**, plus the Admin budget change needed for it.
- One-attempt control (agreed with Codex): before each launch I confirmed that no Python or Research Worker process was running and that the intended job was the only claimable job (the worker's own claimable query). Each attempt was one `python -m investment_engine.research run --once` step. The budget is a secondary safeguard, not an attempt counter.

## Budget policies set (Admin `owner`)

| Version | Daily requests | Daily tokens | Per-run reservation | Reason |
|---|---|---|---|---|
| v1 | 60 | 1,500,000 | 60 requests, 1,500,000 tokens | One measured run only |
| v2 | 120 | 3,000,000 | 60 requests, 1,500,000 tokens | Owner-approved second attempt today; room for exactly one more run |

Day total after both attempts: 31 requests, 3,000,000 tokens. Each failed request has unknown tokens, so each run counts its full token reservation, never 0. The budget therefore refuses any further run on 2026-10-26.

## Provider information as read on 2026-10-26

- Models ([models page](https://ai.google.dev/gemini-api/docs/models)): `gemini-3.8-flash`, `gemini-3.6-flash` and `gemini-3.5-flash-lite` are listed as Stable. `gemini-3.6-flash` is not in upstream's own model list, so upstream warned and continued.
- Prices ([pricing page](https://ai.google.dev/gemini-api/docs/pricing), last updated 2026-10-22): all three are free of charge on the free tier. On the free tier, content is used to improve Google's products. Paid input/output per 1M tokens: 3.8 and 3.6 Flash USD 0.75 / 3.75 through 2026-12-31; 3.5 Flash-Lite USD 0.30 / 2.50.
- Quotas ([rate-limits page](https://ai.google.dev/gemini-api/docs/rate-limits), last updated 2026-10-15): free-tier limits are not published there. They are shown per project in AI Studio, apply per project, and daily quotas reset at midnight Pacific time.
- **Project limits from the owner's AI Studio rate-limit screen** (https://aistudio.google.com/rate-limit, screenshot shared 2026-10-26, after both attempts):

  | Model | RPM (peak used / limit) | TPM (peak used / limit) | RPD (used / limit) |
  |---|---|---|---|
  | Gemini 3.1 Flash Lite | 15 / 15 | 76.16K / 250K | 62 / 500 |
  | Gemini 3.5 Flash Lite | 14 / 15 | 111.92K / 250K | 29 / 500 |
  | Gemini 3.8 Flash | 4 / 5 | 9.55K / 250K | 9 / 20 |
  | Gemini 3.6 Flash | 1 / 5 | 2.4K / 250K | 1 / 20 |

  The 3.5 Flash-Lite (29) and 3.6 Flash (1) counts match these runs exactly. **3.1 Flash Lite (62) and 8 of the 9 Gemini 3.8 Flash requests did not come from M6 runs**: something else is using this project, and it shares the same per-project quotas.
- **Limits that matter:**
  - The quick model's peak of 14 requests per minute is one below its 15 RPM limit. M6 enforces daily caps only, with no per-minute limiter, so the next run could hit a 429. The guard would then fail that run without retrying.
  - `gemini-3.8-flash` allows only 20 requests per day and 5 per minute, shared with the other usage.

## Measured results (from the stored ResearchRecords)

| | Attempt 1 | Attempt 2 |
|---|---|---|
| Job / run | `rjb-2509ec09…` / `rrn-65e9fc6b…` | `rjb-5e97f638…` / `rrn-e77cdcd5…` |
| Models (quick / deep) | `gemini-3.5-flash-lite` / `gemini-3.8-flash` | `gemini-3.5-flash-lite` / `gemini-3.6-flash` |
| Outcome | FAILED (attempt 1 of its job) | FAILED (attempt 1 of its job) |
| Run wall time | 45.3 s (07:28:13–07:28:58 UTC) | 47.6 s |
| Model requests | 16: 15 quick succeeded, 1 deep failed | 15: 14 quick succeeded, 1 deep failed |
| Tokens, successful requests | 85,655 in / 8,042 out | 111,690 in / 7,179 out |
| Tokens, failed request | UNKNOWN (not reported) | UNKNOWN (not reported) |
| Requests by agent | Market 5, News 5, Fundamentals 2, Sentiment 1, Bull 1, Bear 1, Research Manager 1 | Market 7, Fundamentals 2, News 2, Sentiment 1, Bull 1, Bear 1, Research Manager 1 |
| Tool calls | 13 | 16 |
| Data fetches recorded | 16; only error: FRED `get_macro_indicators` (no FRED key; optional) | 19; FRED errors ×2 (same reason) |
| 429 / quota response | None | None |
| Provider error | Research Manager structured call: **503 UNAVAILABLE**, "This model is currently experiencing high demand… usually temporary" (after 14.2 s) | Same 503 on `gemini-3.6-flash` (after 21.0 s) |
| Retry behaviour | Upstream tried its free-text fallback; `ProviderFailureGuard` refused it. No further model call; no research context. | Same |

Measured so far: the four analysts and the bull/bear debate take 14–15 quick-model requests and about 94,000–119,000 tokens per run. The number of tool rounds varies between runs (13 vs 16 tools). **Not measured:** Research Manager, Trader, the risk debate and the Portfolio Manager. These include every deep-model stage.

## Next (owner decision, 2026-10-26)

One more single attempt after the UTC day resets, preferably off-peak, with the originally pinned models: quick `gemini-3.5-flash-lite`, deep `gemini-3.8-flash`. The existing budget policy v2 allows it with no change. The same pre-launch checks and one `--once` step apply. If it returns 503 again, stop and ask the owner; no automatic rerun.

**Revised by the owner, 2026-10-26** ("yes up to 3 tries"):
- **Schedule:** up to three single attempts on 2026-10-27, unattended, at about 05:07, 07:07 and 09:07 local time (UTC+5).
- **Each attempt:** a new request with the same models. It runs only after the pre-launch checks pass, as one `--once` step.
- **When an attempt runs:** attempts 2 and 3 run only if the previous attempt ended with a provider 503 UNAVAILABLE. Any success, or any other failure, ends the series.
- **Budget:** policy v3 (180 requests and 4,500,000 tokens per UTC day; the per-run reservation is unchanged) is set before attempt 1. That gives room for exactly three runs that day.

## Scheduled attempt 1 of 3 (2026-10-27): SUCCEEDED

Setup and launch:
- UTC date confirmed as 2026-10-27. Budget policy v3 was set (180 requests and 4,500,000 tokens per UTC day; reservation of 60 requests and 1,500,000 tokens).
- Request `rjb-1b9f8ad6…`: NVDA, quick `gemini-3.5-flash-lite`, deep `gemini-3.8-flash`, research date 2026-10-26 (the New York exchange date at 20:21 ET).
- Pre-launch: zero `python.exe` processes, and this job was the only claimable one. One `--once` step ran.
- Because the run succeeded, attempts 2 and 3 were cancelled before they ran.

| | Attempt 3 (scheduled 1 of 3) |
|---|---|
| Run | `rrn-8f8641c8…`, SUCCEEDED, attempt 1 of its job |
| Run wall time | **8 min 39 s** (00:22:14–00:30:53 UTC) |
| Model requests | **21**: 19 on `gemini-3.5-flash-lite`, 2 on `gemini-3.8-flash`; no errors, no 429 or 503 |
| Tokens | **132,246 in / 12,078 out** (all reported). Quick model: 126,921 / 9,406. Deep model: 5,325 / 2,672. |
| Requests by agent | Market 8, Fundamentals 2, News 2, Sentiment 1, Bull 1, Bear 1, Research Manager 1 (deep), Trader 1, Aggressive 1, Conservative 1, Neutral 1, Portfolio Manager 1 (deep) |
| Slowest calls | Research Manager 245.7 s and Portfolio Manager 229.0 s (both deep). Every other call took under 7 s. |
| Tool calls | 17 (get_indicators ×5, get_macro_indicators ×2, one each of the rest) |
| Data fetches | 20; the only errors were FRED `get_macro_indicators` ×2 (no FRED key; optional) |
| Budget day after | 21 requests, 144,324 tokens (measured usage replaced the reservation) |
| Context | Built and shown by `research show`: ADVISORY, **VALID until 2026-11-02T21:00Z** (5th session close, D51); rating Overweight (typed); trader action Buy; LLM levels shown under "LLM suggestion: not a price used by the system" (entry 210.96, stop 198.0) |

Observations:
- The deep-model stages now work end to end with real structured output. U1 typed output was parsed into a context, and the label and validity were applied.
- The two deep calls took about 4 minutes each. That is within the 30-minute deadline, but it dominates wall time.
- yfinance had no close yet for the 2026-10-26 bar, so upstream used 2026-10-23 as the latest close. The research is dated 2026-10-26 but rests on the prior close; that is upstream data behaviour, recorded here as is.
- `research show` prints the cache-origin warning twice: once from the record and once from the context. This is cosmetic and recorded for a follow-up.

## D46 caps: proposal, then owner decision

- **Per run (measured once):** 21 requests (19 quick, 2 deep) and about 144,000 tokens. The analyst stages vary between runs: 14–15 quick requests before the debate in the failed attempts, 19 in this complete run.
- **Binding provider limits** (AI Studio, per project, shared with the other usage seen there):
  - `gemini-3.8-flash`: 20 requests per day. At 2 deep calls per run, 80% of 20 is 16 calls, which is **8 runs**.
  - `gemini-3.5-flash-lite`: 500 per day. 80% is 400, which at about 19–25 per run is 16 or more runs.
  - The quick model peaked at 14 of its 15 requests per minute; this is not enforced by M6.
- **Proposed reservation per run:** 30 requests and 250,000 tokens. That is about 1.4× the measured run, leaving headroom for more tool rounds.
- **Proposed daily caps:** 8 runs, so **240 requests and 2,000,000 tokens per UTC day** (8 × 250,000). This assumes nothing else uses the 3.8 Flash daily quota; the other usage seen in AI Studio makes this optimistic. A more cautious choice is 4 runs (120 requests, 1,000,000 tokens).
- These are free-tier Gemini numbers (D47 = USD 0). They must be re-measured if the provider changes.

**Owner decision (2026-10-27): "8 runs".** It was first set as budget policy v4 at 2026-10-27T00:48:47Z: 240 requests and 2,000,000 tokens per UTC day, with a reservation of 30 requests and 250,000 tokens per run.

**Correction (Codex M6-11 review B2).** v4 did not enforce 8 runs. The budget has no run counter. It reserves 30 requests and 250,000 tokens per run, then **replaces the reservation with the measured usage** when the run finishes. At the measured 21 requests and 144,324 tokens per run, v4 admits 11 runs: run 11 sees 10 × 21 + 30 = 240 requests. The owner chose to keep request and token caps sized for **about 8 runs at measured usage**, with no new code. That is **budget policy v5**, set at 2026-10-27T01:52:58Z: **180 requests and 1,400,000 tokens per UTC day**, with the same reservation of 30 requests and 250,000 tokens.

| At measured usage (21 requests, 144,324 tokens per run) | Requests seen at admission | Tokens seen at admission | Result |
|---|---|---|---|
| Run 8 | 7 × 21 + 30 = 177 ≤ 180 | 7 × 144,324 + 250,000 = 1,260,268 ≤ 1,400,000 | admitted |
| Run 9 | 8 × 21 + 30 = 198 > 180 | 8 × 144,324 + 250,000 = 1,404,592 > 1,400,000 | refused |

**This is not an exact run limit.** If runs use fewer requests or tokens than measured, a ninth (or later) run can be admitted. An exact count would need a reviewed run-count field in the budget, which the owner did not choose. Google's own limit on `gemini-3.8-flash` (20 requests per day per project, 2 per run, shared with other usage) remains a separate, provider-side bound.

The owner's own CLI database (`INVESTMENT_ENGINE_PG_DSN`) is not set up yet. When it is, the same `research budget set` command (v5 values) must be run there; a budget does not carry between databases.

## Checks

Run from `C:/Users/LOQ/TradingAgents-m6` with `C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe` (shown as `python`). Environment variables are named; their values are never recorded.

| Command | Result |
|---|---|
| `python -m pytest -q -p no:cacheprovider tests/engine/test_research_live.py` (default selection) | The 2 integration tests are deselected. At `1cedac2`, this file alone selected nothing, so pytest exited 5. Now the 2 canary tests run: **2 passed, 2 deselected**. |
| Same, with `-m integration`, `INVESTMENT_ENGINE_PG_DSN` set to the `ie_m6_live` DSN (the driver strips `ANTHROPIC_API_KEY`) and `INVESTMENT_ENGINE_M6_LIVE_RUN_ID=rrn-8f8641c8c23457563742f75dd10cf9b1b5e0c5449acebabc6e5e6e3c3b3f6a00` | **2 passed, 2 deselected**: the worker refuses without `research_worker.env`, and this document matches the stored record. |
| Same integration selection of `::test_the_measurement_document_matches_the_stored_record`, with `INVESTMENT_ENGINE_M6_LIVE_RUN_ID` set to the failed attempt-2 run `rrn-e77cdcd5…` (red check) | 1 failed |
| B1 canary regression `::test_a_failing_evidence_connection_never_prints_the_password` (default and `-l --tb=long -rA`), before the fix | **2 failed**: the canary password appeared in the driver's normalized connection text |
| Same, after the fix | **2 passed** |
| `python -m ruff check .` | All checks passed |

## Not established

- Whether the 503s reflect general demand or free-tier deprioritization. Both deep-model calls failed the same way within four minutes; no more calls were made to find out.
- The project's free-tier quotas were read from the owner's AI Studio screen, not from a signed-in check of our own. They are attributed to the owner's observation.
