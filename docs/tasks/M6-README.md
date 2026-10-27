# M6: TradingAgents adapter and Research Worker

| | |
|---|---|
| Status | **Done: merged into `main` at `571df21` (2026-10-27).** v0.1 was accepted for implementation by the owner on 2026-10-25 (D45–D54 as recommended; D47 = USD 0). Codex accepted the milestone at `571df21`, and the owner approved the merge. |
| Author | Claude Code (implementation lead) |
| Planning branch | `docs/m6-specs`, worktree `C:/Users/LOQ/TradingAgents-m6-specs`, from `main` `d277440` (M5 merged locally 2026-10-25, not pushed) |
| Prerequisites | M5 merged ✔; **OPEN-10 and OPEN-11 decided (D45–D48 below)**; this pack reviewed and accepted |
| Visible result | Research shown alongside the MarketView, labelled advisory (roadmap M6) |
| Complete when | Research appears next to the view and is labelled advisory; a Research Worker crash or missing research doesn't affect execution; research lineage is complete |

M6 adds the fourth process from the frozen architecture: the **Research Worker**. It runs upstream TradingAgents behind one adapter, holds only LLM and research-data keys, works from a job table under a daily budget, and saves a reconstructable `ResearchRecord` plus a typed, expiring `ResearchContext`. Research is **advisory evidence only** (Laws 1–4). It never sizes, approves, gates or places anything, and nothing on the bar-to-order path waits for it.

**No new ADR is needed.** ADR-001, ADR-002 and architecture Parts E, G6 and I already fix the design. ADR-001 leaves "the adapter, job table, budget and record schemas" to these tasks. If a task finds that it needs a new process, boundary or authority, the stop rule applies.

## What blocks implementation

1. **OPEN-10 needs a measurement, not an estimate** (PRD).
   - Every one of the request count, the tokens and the cost per TradingAgents run must be **measured** with the chosen provider and models.
   - Quotas must be read from the provider's **current** documentation and console.
   - M6-00 builds the measuring instrument offline. **One** real measured run (M6-11) needs your explicit approval to use the API key, because it makes real paid or quota-limited calls and network requests.
   - The budget numbers in D46 are provisional until that measurement.
2. **OPEN-11 (monthly budget)** is your number to set (D47).
3. **Credential separation (D48).** `GOOGLE_API_KEY` is a Windows **user** environment variable today, so the Core Engine and the Execution Worker inherit it too. ADR-002 says only the Research Worker holds LLM keys.

## Owner decisions (D45–D54, proposed)

Numbering continues from M5's D35–D44. Each is a recommendation for this prototype, not an established standard.

| ID | Decision | Recommendation |
|---|---|---|
| **D45** / OPEN-10a | Provider and models | **Google Gemini**, using the key you already have. One quick-think and one deep-think model, **pinned to exact version names** read from Google's current model list on the day of M6-11, not aliases such as "latest". The adapter stays provider-neutral through upstream's own `llm_provider` setting; other providers are a later config change, not an M6 task. |
| **D46** / OPEN-10b | Daily LLM budget | Enforced in **requests and tokens per UTC day**, with an optional USD cap once prices are verified. **Provisional:** at most **3 runs per day** and **no automatic retries**, until M6-11 measures one run. Then set `daily_requests = floor(provider daily quota × 0.8)` and the matching token cap, as a separate owner-approved budget command. Exceeding the budget **refuses new jobs** (`BUDGET_EXHAUSTED`); a run in progress is never killed mid-way just to fit. |
| **D47** / OPEN-11 | Monthly budget (data + LLM + hosting) | **Your number.** Suggest **USD 0** (free tier only) until the measurement shows whether that is realistic, with research rationed to on-demand runs (D49). Hosting is M7. |
| **D48** | Credential separation | The Research Worker reads its key only from its own secrets file, `<data dir>/secrets/research_worker.env`, mirroring the Execution Worker's D32 file. **You remove `GOOGLE_API_KEY` from the Windows user environment** (I can't, and won't print it). Core, the Execution Worker and the CLIs refuse to start research or load LLM settings. A startup check refuses to run the Research Worker if any broker-credential variable or the worker secrets file is visible to it. This is still a development convention until M7's OS-level isolation (ADR-002 §5). |
| **D49** | Cadence | **On-demand only** in M6: a Trader or Admin requests a run for one instrument and one date. No scheduler. A daily automatic run is a later, separately approved change. |
| **D50** | Which dates | **Live, current-date research only.** Upstream's tools fetch current news and fundamentals, which would leak the future into a historical "as of" run, so historical replay runs are refused. Research is shown next to the latest MarketView only; **no backtest or evaluation uses research in M6**. |
| **D51** | Validity | `valid_until` = the close of the **5th US-equity session** after `generated_at`, matching M2's five-session prediction horizon, with a Trader/Admin override that can only shorten it. Expired research is shown as **EXPIRED** (design principle E-01), never silently. |
| **D52** | Use in decisions | **Display only.** No strategy requires research, so MarketView, sizing, policy, risk, gate and ledger are unchanged, and the Decision module reads no research in M6. The "optional evidence" hook in ADR-001 §4 is deferred to a later reviewed package. |
| **D53** | Untrusted text | Raw responses, tool results and LLM-suggested price levels are stored verbatim as **untrusted**. They are escaped on display and never parsed into orders, limits or sizing. `suggested_levels` is labelled "LLM suggestion: not a price used by the system". |
| **D54** | Package | Approve M6 as one package after review: **12 tasks, about 38 h**, with focused checks per task and full suites plus fresh installs once per package. Merge and push stay separate approvals. **Jev (typed judgment) is out of scope**: it needs its own ADR and trial. |

## Tasks and dependencies

| ID | Task | Depends on | Hours |
|---|---|---|---:|
| [M6-00](M6-00.md) | Offline measurement instrument: LangChain callback counter and fake-LLM run | none | 3 |
| [M6-01](M6-01.md) | Research contracts: job, record, context, budget | 00 | 3 |
| [M6-02](M6-02.md) | Migration 0021 and append-only research store | 01 | 4 |
| [M6-03](M6-03.md) | The one upstream change: keep structured Trader/PM output | none | 2 |
| [M6-04](M6-04.md) | TradingAgents adapter and capture | 01, 03 | 5 |
| [M6-05](M6-05.md) | ResearchContext parsing, validity and warnings | 04 | 3 |
| [M6-06](M6-06.md) | Daily budget enforcement | 02 | 3 |
| [M6-07](M6-07.md) | Research Worker process: claim, lease, recover, secrets | 02, 04, 05, 06 | 4 |
| [M6-08](M6-08.md) | Request CLI and Admin budget commands | 06, 07 | 2 |
| [M6-09](M6-09.md) | Research shown alongside the MarketView, advisory | 05, 08 | 3 |
| [M6-10](M6-10.md) | Isolation and fault proofs: crash, missing research, boundaries | 07, 09 | 3 |
| [M6-11](M6-11.md) | Owner-approved measured live run, budget set, package | 10 + your key approval | 3 |
| | **Total, planning estimate** | | **38** |

This is within the roadmap's 30–40 h. M6-03 can run in parallel with 00–02.

## Shared contracts

### C1. Records (`investment_engine/research/contracts.py`)

| Record | Required content |
|---|---|
| `ResearchJob` | `job_id` (deterministic from instrument, date, requester command and settings hash), instrument, ticker mapping used, requested date, requested_by, `requested_at` (command clock), settings snapshot (provider, both model names, debate rounds, analysts, temperature, output language), state |
| Job states | `REQUESTED → CLAIMED → SUCCEEDED / FAILED / BUDGET_REFUSED / EXPIRED_UNCLAIMED`. CLAIMED carries a lease (worker ID, `lease_until`). Transitions are append-only versions with compare-and-set, as in M4. |
| `ResearchRecord` | `run_id`, `job_id`, provider/model/version, settings, upstream package version and repository code version, prompt and input snapshot (every LLM call's messages), tool calls with arguments and results, data-source snapshot references (vendor, endpoint, fetched_at), raw final state (the reports and structured objects), token and request usage per call, warnings, `started_at`/`finished_at` (injected clock), outcome |
| `ResearchContext` | `run_id`, instrument, `rating` (5-tier `PortfolioRating`, from the typed PM decision), `trader_action`, `suggested_levels` (untrusted: entry, stop, target or None), `horizon`, `generated_at`, `valid_until`, `warnings`, `source` = typed / free-text-fallback |
| `BudgetPolicy`, `BudgetUsage` | Versioned daily caps (requests, tokens, optional USD) set by Admin; per-run reservation and actual usage, appended |

Text fields are stored as received; size limits are recorded, not truncated silently. Money is Decimal. Times are aware UTC from injected clocks. Everything is registered with the lineage codec.

### C2. Storage (`0021_research.sql`, PostgreSQL only)

- Tables for jobs and versions, records, contexts, budget policies and usage.
- UPDATE, DELETE and TRUNCATE are refused on all of them, as in M5.
- A writer-role trigger lets only `research-worker` write records, contexts, usage and claim/finish transitions. Core or the CLI writes only `REQUESTED` and budget policy (Admin).
- Records and contexts commit **together** with an outbox event `research.completed`. A failed run commits its partial record with outcome FAILED; nothing is half-saved.
- Migrations 0001–0020 are unchanged.

### C3. The process boundary

- **Process.** The Research Worker is `python -m investment_engine.research`, using a new `ProcessRole.RESEARCH = "research-worker"`.
- **Imports.** It imports `tradingagents` and `investment_engine.research` plus the neutral stores. It must not import `execution`, `oms` writers, `ledger` writers, `policy` writers or the kill switch. AST boundary tests enforce this as a regression guard, not as OS isolation.
- **Communication.** The only channel is the database: jobs in, records and events out.
- **No-wait rule.** Core, the Execution Worker and the API never import `tradingagents`. No proposal, gate or ledger path reads a research table in M6 (D52), and a test proves that.

### C4. Budget

- **Before a run:** reserve the provisional per-run cost under a `budget|<UTC day>` lock. Refuse when the reservation would exceed the cap.
- **After a run:** append the actual usage from the callback counter. Measured usage replaces the reservation for the day's total.
- **Fail closed.** A missing or unreadable policy refuses the run.
- **Retries.** Upstream's `llm_max_retries` is pinned to 0, so retries can't multiply cost unseen. A provider 429 or quota error is recorded as FAILED with its reason, and is not retried automatically.

### C5. Reconstructability and honesty

Every displayed research item links to its `run_id`, record and settings. LLM output is **reconstructable, not reproducible** (ADR-001), and the display says so. Research never becomes a probability, a signal strength or a price used by the system.

## Exclusions

- Historical replay research.
- Strategy use of research.
- Scheduler.
- API or dashboard (M8).
- Jev / typed-judgment provider.
- Other LLM providers beyond config.
- Paper or live broker (M7).
- M2 strategy improvements (the deferred reminder still stands).
- Any change to M1–M5 behaviour except the listed read-only display.

## Checks

Per shared rules §6 and your 2026-10-20 cadence:
- **Per task:** focused tests, red then green, plus ruff.
- **Once per package:** full Git Bash and PowerShell suites and fresh base/engine installs. TradingAgents tests use fake LLMs and no network. The single live run (M6-11) is `integration`-marked and runs only with your approval.

## Owner acceptance record

**Owner approval, 2026-10-25** ("ok approved", answering the request to approve D45–D54 as recommended and commit the M6 plan):
- D45–D54 accepted as recommended; **D47 monthly budget = USD 0** (free tier only) until the M6-11 measurement.
- The whole package M6-00 to M6-10 is authorized for local task commits on `m6/milestone`, one commit per task.
- **Not authorized:** the M6-11 live LLM run and any use of the API key (separate approval), merge, push, M7.
- **Owner action:** remove the user-level `GOOGLE_API_KEY` (D48). It is needed before M6-11, not before the offline tasks.
- This is owner acceptance, not independent review. Codex reviews every commit of the finished milestone, and the specs with it.

**M6-00 — committed (checked), not done:** Offline usage counter for OPEN-10: a thread-safe LangChain callback handler counts every model request and tool call of one TradingAgents run, attributed to the top-level agent node (analyst sub-graphs report their own node through the checkpoint namespace). Token counts come only from provider-reported usage; one silent call makes the run's tokens unknown, never 0. Each run ID counts once even when the handler is attached at both model and graph level. Times come from the injected clock. Shared offline fakes in tests/engine/research_fakes.py drive the real upstream graph with a scripted model whose structured calls pass through the model's own invoke, so callbacks see them.

**M6-03 — committed (checked), not done:** The one planned upstream change (architecture Part I, ADR-001 §6), registered as U1 in docs/dev/upstream-changes.md: the final graph state keeps `trader_proposal_structured` and `final_decision_structured` (the parsed TraderProposal and PortfolioDecision as JSON-mode dicts, or None after a free-text fallback). The Trader inlines the same structured-then-free-text logic as `invoke_structured_or_freetext` (still used by other agents) so it can keep the parsed object. Prompts, ratings, rendered text, memory log and reports are unchanged.

**M6-01 — committed (checked), not done:** Immutable, codec-registered research records per C1: ResearchSettings (frozen provider/models/rounds/analysts; retries are not a setting), ResearchJob (job ID from instrument, ticker, date, requester, request time and settings hash; the free-text reason is provenance only), JobVersion with the job-state edge table (CLAIMED -> CLAIMED is a re-lease after expiry), CallRecord/ToolRecord/UsageTotals (unknown tokens stay None), CapturedText (verbatim untrusted text, at most 1,000,000 characters with explicit truncated count), DataSourceRef, ResearchRecord (run ID from job and attempt; FAILED requires its failure), UntrustedLevels (Decimal-or-None, labelled, no conversion to any order type), ResearchContext (VALID/EXPIRED status), BudgetPolicy and BudgetUsage. ProcessRole.RESEARCH added; it owns no order edge. Registered for audit decoding.

**M6-02 — committed (checked), not done:** Additive schema 0021 and ResearchStore. Append-only research tables (jobs, job versions, records, contexts, budget policies, budget usage); UPDATE/DELETE/TRUNCATE and conflict-update refused. Writers fixed by process role in SQL: core-engine requests, expires unclaimed jobs and sets budget policy; research-worker claims, finishes, saves records/contexts and usage. Job versions are compare-and-set (primary key per version) and the SQL trigger mirrors the contract's edge table, at most one re-claim, re-claim only after lease expiry with a new run, finish only by the current claim holder for its own run, SUCCEEDED only with its record and exactly its context. A finished run's record, context, ACTUAL usage, final version and `research.completed` event commit together. Requests are attributed to the authorizing operator's audit Actor (authorization itself is M6-08).

**M6-04 — committed (checked), not done:** TradingAgentsAdapter behind the ResearchPort: builds the upstream graph from the job's frozen settings (pinned models, llm_max_retries=0, checkpointing off, results/cache/memory under the worker's work directory) and runs the compiled graph itself with the M6-00 counter and a TextCapture handler in both model and graph config, so model and tool calls are all seen. It captures every prompt, response, tool input and tool output (verbatim untrusted text, cut beyond 1,000,000 characters with the cut recorded), the selected final state including the U1 structured objects, the upstream and repository versions and usage. Data-source references name the upstream router, since upstream picks the vendor per tool. A research date other than the current New York exchange date is refused before any model call (D50). A provider error becomes a FAILED record with no context. Loaded secrets are redacted from every captured text, the state JSON and the failure message.

**M6-05 — committed (checked), not done:** `build_context` turns a successful run into a ResearchContext. The rating comes from the parsed Portfolio Manager decision (U1, source TYPED); without one, from the 5-tier `final_rating` upstream itself parsed from the decision text (source FREE_TEXT_FALLBACK, with a warning). The research package may not call upstream's parser directly (layering), and needs not to. No valid rating, or a failed run, gives `NoResearchContext` (recorded FAILED by the worker). Action and levels come only from the parsed Trader proposal; levels convert from the number's decimal string form, and non-numbers, percentages, ranges, non-finite or non-positive values are dropped with a warning. Warnings name empty reports, failed tools, unknown token usage and the run's own warnings. Report text is never read for fields, so an injected instruction adds nothing. `valid_until` is the close of the 5th session opening after generation, on the cited exchange calendar (weekend and the Jan 19 2026 holiday tested); an override can only shorten it.

**M6-06 — committed (checked), not done:** ResearchBudget enforces D46 and fails closed. Only a current Admin sets a versioned, audited policy (operator lock, then live command-time authorization against the stored registry; Trader, Viewer and a deactivated Admin are refused). Before a run the worker reserves the policy's per-run requests and tokens under the UTC day's lock; it is refused with the numbers when the day's total would exceed a cap, and refused when no policy exists. Reservations are idempotent per run. A run's measured ACTUAL usage replaces its reservation in the day's total; unknown measured tokens count the reserved tokens, never zero. A USD cap cannot be enforced before per-run prices are measured (M6-11), so a policy with a USD cap refuses runs: D47's USD 0 monthly budget is the free-tier rule, expressed through the request/token caps, not a USD cap.

**M6-07 — committed (checked), not done:** The Research Worker process, `python -m investment_engine.research run [--once]`. Each step claims one job with a lease covering the whole bounded run (deadline plus 5 minutes), reserves the day's budget (refusal recorded BUDGET_REFUSED without running), runs the adapter in a thread outside any transaction under the deadline, builds the context, then saves record, context, ACTUAL usage, final version and event atomically and publishes. A successful run without a usable rating is saved FAILED with its reason and no context. A run past its deadline is saved FAILED ("abandoned; its reservation stays counted") and the worker starts nothing new until the stuck thread returns, as M4 does for a stalled broker call. A lost database connection keeps its type and reaches the reconnect, keeping any stall; without a reconnect it is raised. Startup (D48) refuses, before touching the database and without printing any value: a missing `research_worker.env`; a key in it that is not an LLM or research-data key; any LLM key already in the inherited environment; any broker-looking variable; or a visible Execution Worker secrets file. Keys load only into this process's environment. New layering rule: the research package imports no execution, kill-switch, ledger (except the pure identity hash in ledger.contracts), reconciliation, risk, portfolio or OMS writer modules.

**M6-08 — committed (checked), not done:** `research` command group: `research request INSTRUMENT --operator --reason --quick-model --deep-model [--provider google] [--date]` records a job for today's New York exchange date, after the operator's lock and live command-time authorization (Trader or Admin; Viewer refused); a `--date` other than today is refused (D50). The ticker comes from the existing yfinance symbol mapping. Models are explicit options, so the D45 pinned versions are named at request time. `research budget set` is Admin-only through M6-06. `research status`, `research show` (record summary, usage with UNKNOWN shown for unreported tokens, and the advisory context with VALID/EXPIRED status, its source, the untrusted-levels label and warnings) and `research budget show` open read-only connections and change nothing. Requests are recorded only; nothing runs inline. The CLI imports no TradingAgents, LangChain or adapter code (checked in a fresh interpreter).

**M6-09 — committed (checked), not done:** The visible result. `reporting/research_view.py` renders an advisory research panel, as text and escaped HTML. It shows the "ADVISORY research: not used by sizing, risk or orders" label; status in words (VALID until / EXPIRED since); rating with its source (TYPED or FREE_TEXT_FALLBACK); trader action or "unavailable"; the untrusted-levels label with exact Decimal levels or "none"; generation time and horizon; provider and both models, upstream and code versions, and run ID; warnings; and the reconstructable-not-reproducible statement. Missing research is "No research", never a default rating; a failed latest run shows its failure. `render_research_report` gained an optional `research=` keyword that inserts the panel after the latest view; without it the M2 report is byte-identical (tested on the existing report fixture). `research view INSTRUMENT` (read-only connection, in cli.py as the spec allows) prints the latest stored MarketView and, beside it, the latest research as of now.

**M6-10 — committed (checked), not done:** Isolation and fault proofs for the M6 completion criteria. (1) The full synthetic M5 order/accounting run (real proposal, Core, Execution Worker, simulated broker, ledger and reconciliation) runs on two fresh databases, one seeded with every research state (a succeeded context, an unclaimed request and a crashed claim, all inside the run window). Accounting JSON, proposal outcomes, order count and stops are byte-identical, and an SQL capture over every statement of every role during the seeded run contains no reference to a research table. (2) With the research process role set, inserts into orders, fills, gate decisions and cancel requests are refused by the existing OMS triggers (they fail closed for any role but Core/Execution). (3) A real Research Worker child process (new harness role, research fixture only) claims a job and is hard-killed inside its run. The claim remains, no record is written; after the lease, a restarted worker re-claims (attempt 2) and succeeds, with exactly one context and the crashed attempt still visible in the job history. (4) Every displayed context resolves to its record, settings and code version.

**M6-08 — committed (checked), not done:** Follow-up found by the package's full Git Bash run: `research budget show` read the system clock (`datetime.now(UTC)`), which Law 13 and the existing `tests/engine/test_no_system_clock.py` forbid outside `clock.py`. It now takes the UTC day from the injected `LiveClock`, like every other research command. No behaviour change.

**M6-02 — committed (checked), not done:** Codex review B1 (event-stream gaps), fixed. A claim appended a job version without an event, so every completion left a permanent gap: the shared Consumer reads each aggregate's versions contiguously and held `research.completed` forever. Every job version now emits its event (`research.claimed` added; requested, completed, budget-refused and expired already did). `research request` publishes its own Core outbox after the commit, so delivery doesn't depend on a running Core process. The shared Consumer is unchanged.

**M6-02 — committed (checked), not done:** Codex review B11 (bundles not bound to their job), fixed. `finish` now requires the record's settings to equal the job's frozen settings, and the context to be for the job's instrument, generated exactly when its run finished. Reads (`context`, `latest_context`) return a context only when its job recorded that run as SUCCEEDED, and re-check the binding. Additive migration 0022 enforces the same at insert in SQL: a record must be the job's current claimed run, with the matching attempt and the job's settings; a context needs its run's SUCCEEDED record, the still-current claim, the job's instrument and the run's finish time. A context added after a FAILED (or any terminal) version is therefore refused, so the invariant can't be broken later. 0021 is unchanged.

**M6-09 — committed (checked), not done:** Codex review B10 (future evidence in reports), fixed. `ResearchEvidence` now refuses a run that finished after its assessment time, a context generated after it, a context not from its own succeeded run, and a context not generated exactly when its run finished. `ResearchContext.status` refuses an assessment before generation. `render_research_report` accepts research only when assessed at the report's own `generated_at`, matching its other no-look-ahead guards. The no-research report stays byte-identical. Two older display tests used inconsistent evidence (a panel assessed at an unrelated time, a failed run assessed before it finished) and were corrected to consistent bundles.

**M6-04 — committed (checked), not done:** Codex review B3 (ambient TypeSafe key switches on excluded Jev calls) and B4 (job settings didn't pin the actual provider/endpoint), fixed together, as they share one allowlist. The adapter now sets every run-shaping upstream key explicitly: both tier providers to the job's provider, every backend URL to none, reasoning/thinking knobs and output cap to their defaults, upstream's own tool/recursion limits, no benchmark. It refuses any provider but Google (D45) before a call, and records the effective configuration (`ResearchRecord.effective_config_json`, a new field with a default). Ambient switches are refused, by name only, never value, both at worker startup and again by the adapter before any call: TypeSafe/Jev variables (on whatever the provider; D54), the Google client's Vertex AI selectors (another endpoint, project and billing), and every `TRADINGAGENTS_*` override except the three paths the adapter replaces. `GEMINI_API_KEY` (Google's fallback key name) joins the keys that may live only in `research_worker.env`. Other providers' keys and endpoints are inert once both tiers are pinned to Google, so they aren't refused; the test suite's own placeholder keys confirmed this would otherwise refuse harmless setups.

**M6-04 — committed (checked), not done:** Codex review B5 (`llm_max_retries=0` did not stop upstream's application-level retry), fixed, adapter-local, with no upstream change. A `ProviderFailureGuard` callback, placed first among the run's handlers, records the provider's first error and refuses every later model call in its start callback, before the request is sent. Upstream's structured-to-free-text fallback therefore cannot make a second paid call after a quota/429 error, and a run in which the provider failed is recorded FAILED with no context, even when upstream swallowed the error and carried on. Malformed or unsupported structured output is a parser path, not a provider error, so upstream's free-text fallback for it is unchanged (tested). The failure text now reads "provider error: <type>: <redacted message>; no further model calls were made"; one older assertion on its prefix was relaxed to the type.

**M6-04 — committed (checked), not done:** Codex review B2 (redaction missed upstream files and logs, escaped and short secrets), fixed. The `Redactor` is now one regular-expression pass over every nonempty configured secret and its JSON-escaped forms (with and without ASCII escaping), longest first, so a replacement marker can never be re-matched, and serialized text with quotes, backslashes or Unicode is covered. `deep()` redacts plain JSON-like data. The adapter hands upstream's `record_decision` (its state-log file and memory-log entry) the deep-redacted state, never the raw one, and during a run installs a log-record factory that redacts every record's message and formatted exception before any handler sees it. That covers upstream's structured-call warning that printed the exception text. The secrets loader refuses values shorter than 8 characters as too short to redact safely.

**M6-07 — committed (checked), not done:** Codex review B8 (the fixed lease could expire before the covered run finished), fixed. Before calling the adapter, after the budget reservation and job load, the worker now fences. It re-reads the job and starts only if its claim is still the current version and holder, and if the lease outlasts the whole run deadline from that moment. If the claim was taken over, it writes nothing and starts nothing. If the remaining lease is too short, it records the job FAILED ("not started: the lease … would expire before the run's deadline") with a known-zero ACTUAL usage, since no model call was made. A started run is therefore always bounded inside its own lease, and the deadline-abandoned case ends within it too. This replaces my earlier, overstated note that a running job was "never re-claimable": lock waits before the run were not counted then.

**M6-07 — committed (checked), not done:** Codex review B9 (the worker's runtime loaded other domains' writer code), fixed. Measured first: a freshly constructed Research Worker loaded the OMS pipeline and intent store, risk limits and checks, portfolio sizer/snapshot, policy accounts/rules/checks, reconciliation incidents and the kill-switch flag. Two causes: its `AuditStore` imports every registered domain module, though the worker writes no audit event; and `budget.py` imported the operator registry for the Admin policy command. The Research Worker's store is now built without an audit store (Core-side research writes still require one). The budget module keeps only the worker's reservation; the Admin policy command moved to the Core-side `research_cli.set_budget` (live command-time authorization under the operator lock, versioned and audited, unchanged in behaviour). The layering rule now also forbids policy code in the research package. A new fresh-interpreter test constructs a real worker on a migrated disposable database, runs a claimable query, and asserts no execution, kill-switch, ledger-writer, reconciliation, risk, portfolio, policy or OMS-writer module is loaded; a deliberate `AuditStore` in the worker made it fail, then was reverted.

**M6-04 — committed (checked), not done:** Codex review B6 (data-source provenance incomplete and mislabelled), fixed. The placeholder vendor `tradingagents-router` is gone. For the duration of a run, in the Research Worker's own process, the adapter's `SourceRecorder` wraps and afterwards restores: every entry of upstream's `router.VENDOR_METHODS` (looked up per call, so each vendor function that actually ran is recorded, a failed one and each fallback included); the sentiment node's direct StockTwits and Reddit fetchers; and the instrument-identity lookup made before the graph starts. Each `DataSourceRef` now carries the real vendor, the method, start and end times, the exception type when that vendor failed, and the result size (new optional fields with defaults); arguments are hashed, nothing altered. Upstream's news call from the sentiment node goes through the router and is recorded. What the records cannot distinguish is stated as a record warning rather than overclaimed: whether a vendor answered from upstream's disk cache, or the identity from the in-process cache.

**M6-10 — committed (checked), not done:** Codex review N6 and N3 (tests asserted less than claimed), tightened. N6: the usage-counter test now asserts the exact one-round table (Market, News and Fundamentals Analysts 2 requests each, every other agent 1; 15 requests) and exactly 12 tool calls, besides provider-versus-counter equality, so an extra unintended call fails it. N3: the research-role OMS probe no longer accepts a not-null error as success; a BEFORE trigger fires before NOT NULL checks, so the role refusal itself must be the failure. The ledger's lack of a database writer-role guard remains the recorded M5 residual, not a proven SQL boundary.

**M6-07 — committed (checked), not done:** Codex review N1, N2 and N4, fixed. N1: the budget reads its UTC day after taking one budget lock (no longer a per-day lock chosen before waiting), so a lock wait across midnight books the new day. The accounting policy is now stated in code: usage is booked on the reservation's UTC day even if calls continue past midnight, so the caps bound reservation-day totals, not per-call provider days; M6-11 must leave a margin when setting caps against a per-call provider quota. N2: the adapter keeps a thread-safe live view of its capture (`partial()`), so a run abandoned at its deadline saves the calls, tools, texts and data sources captured so far, with a warning that it may have continued. A run with nothing captured is marked "not measured" and `research show` prints "Usage: NOT MEASURED" instead of 0 requests. N4: the code version is asked of the package's own directory and accepted only when that checkout's top level holds this very package; launching from an unrelated directory or repository no longer records a foreign commit, and an installed copy elsewhere is "unversioned".

**M6-08 — committed (checked), not done:** Codex re-review R1 (one bounded publish could leave the request unpublished behind a larger backlog), fixed. After committing, `research request` publishes page by page, in the outbox's own per-aggregate order, until its own version-1 event is in the event log; if nothing more can be published, the command says the request is recorded but its event not yet published. `request_published(db, job_id)` is the read-only check. Nothing is skipped, published out of turn or marked for unrelated work; the shared Consumer is unchanged.

**M6-04 — committed (checked), not done:** Codex re-review R2 (memory-settlement price fetches bypassed capture; direct fetches kept only hashes and sizes), fixed. The SourceRecorder also wraps upstream's `settlement.get_closes`, which the Memory Log step calls directly (outside the router) to settle due past decisions before asking the model for a reflection. Every recorded fetch now also keeps its exact answer as an untrusted, redacted input snapshot (`CapturedText` "source-N", tool_output role): pandas frames and series in full JSON, never their abbreviated repr, and an error marker when a vendor failed. The saved run can therefore reconstruct the prices behind a reflection's return/alpha inputs, and the social and identity answers. Upstream prompts and ratings are unchanged; partial capture at abandonment includes the snapshots.

**M6-07 — committed (checked), not done:** Codex re-review R3 (the lease fence used a start time read before its final ownership read, and allowed no finish margin), fixed. The worker now reads the clock after its final ownership read and starts only if that time plus the run deadline plus a defined one-minute finish margin (for timeout handling and the terminal write) fits inside the lease; equality is allowed, one second more is not. A refused start is recorded FAILED "not started", with known-zero usage, as before.

**M6-11 — committed (checked), not done:** The live measurement is done: OPEN-10 is measured, and the owner set the final D46 caps. The full record is in `docs/reviews/m6-measurement.md`.
