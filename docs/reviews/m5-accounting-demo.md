# M5 accounting demonstration

**SYNTHETIC | SIMULATED | REPLAY | RESEARCH | NOT PROMOTED.** Hand-constructed daily bars, views and actions under the `EQ_US_NVDA` instrument identity. These are accounting acceptance numbers, not an NVDA historical result, strategy evaluation or evidence of profitability. No provider requests, API keys or PAPER execution.

The executable scenario is `tests/engine/test_m5_accounting_demo.py`. It uses the real proposal, risk, approval, Core conversion, Execution Worker gate, independent simulated broker, outbox consumer, journal, FIFO and reconciliation path, with separate database connections. All databases are generated disposable local test databases.

## Hand calculation

Starting capital: USD 100,000; no holdings or invented opening cost. A synthetic bullish view on 2024-05-28 references a raw close of USD 120. The accepted 10% position cap and 1% limit band size `floor(10000 / 121.20) = 82` shares. The next opening fill is USD 120.06 (5 bps adverse slippage, cent rounding), zero commission.

| Fact | Cash change (USD) | Shares | Held cost (USD) | Unpaid receivable (USD) |
|---|---:|---:|---:|---:|
| Opening declaration | 100000 | 0 | 0 | 0 |
| BUY 82 at 120.06 | -9844.92 | 82 | 9844.92 | 0 |
| 10-for-1 split at 2024-06-10 open | 0 | 820 | 9844.92 | 0 |
| Synthetic dividend 0.10 per entitled share, 2024-06-11 | 0 | 820 | 9844.92 | 82 |
| SELL 820 at 12.99, 2024-06-12 open | 10651.80 | 0 | 0 | 82 |

Final cash **100806.88**; gross realized P&L **806.88**; dividend income/receivable **82**; explicit fees **0**; equity **100888.88**; net P&L **888.88**. Receivables contribute to equity but never spendable cash. Slippage is already in fill prices and is not subtracted again. Currency and security journals balance separately; the full disposal exhausts the exact FIFO cost.

## Reproducibility and missing evidence

- Two fresh databases with identical business inputs and different actual Admin command dates must produce identical economic IDs and byte-identical accounting JSON. Real command times remain in original audit/setup provenance.
- The independent broker derives its evidence from its own seed, requests, executions and actions; Core does not read private simulator tables or obtain ledger balances from the broker.
- A USD 1 seeded broker discrepancy opens an incident. Admin acknowledgement leaves the account blocked, the original evidence intact, the journal entry count unchanged and the book ID unchanged. Reported confirmed net P&L becomes unavailable.
- A held position without explicit raw mark/delivery evidence is visibly INCOMPLETE, with null valuation/P&L rather than zero. The compact simulation result deliberately infers no mark-delivery time. The separate accounting report accepts explicit `(raw Candle, actual delivery)` pairs.
- A missing target-session bar expires the order without a fill and marks the accounting run INCOMPLETE. The result names the missing session and does not present a confirmed zero return.
- Run metadata contains provider, calendar/code/policy versions, view lineage, strategy/feature versions, action revisions/content hashes, recorded fill-model/fee provenance, source references, E/K cutoffs, rejected/UNKNOWN orders and reconciliation results.
- The larger saved historical NVDA range is **not run** for M5: the accepted task makes it optional. No profitability claim is made from this small synthetic verification.

## Evidence state

Task tests and package-check results are recorded in `PROGRESS.md` and the milestone review package. Local review artifacts are captured under `C:/Users/LOQ/TradingAgents-proposals/m5-accounting-demo/` by the external `capture_demo.py` evidence helper. The final package records their measured size/hash after capture. No daily backup schedule is installed; a tested backup/restore capability is not a claim of scheduled operation.

Captured from committed code `b7e1c13d66fc555be2fc7f563a5fe76dda2ba77e`:

- `accounting-demo.json`: **9,540 bytes**, SHA-256 `0e4a6db39a54e7beb4b9952add0a406a2e519e74901ac0796bb5717f019dfbf0`. Includes explicit `demonstration.synthetic`, hand-constructed data and hand-authored view labels.
- `accounting-demo.html`: accessible escaped rendering with the synthetic-data warning above the full payload.
- Pinned book: `e76677af49e40bb28b16df055530d75802339891d322c278e2df0763af10f9b6`.
- Query: `b222cb6e7138ed3750c3156d3c60b7575c7eff57237c9f7020c289a0afdad7dd`.
- Captured report: complete, reconciliation MATCH. The adjacent manifest pins production/test file hashes and the retained synthetic source directory. These artifacts contain no credentials; the test database was disposed after capture.

The unannotated product accounting JSON was 9,239 bytes, SHA-256 `aede1c009d62b43df56730854ee454eadbd5b1c9679836b89a1fde8ff02f8ea3`. Removing only the demo's provenance annotation exactly reproduces that hash; no financial values or economic IDs were changed. The annotation is an artifact wrapper, not a production report API change.

The adjacent manifest also hashes every retained synthetic Parquet file and the actual packaged calendar/fee resources. Logical version labels in this test fixture are accompanied by those concrete byte hashes; they are not a claim of a separately versioned production calendar registry. The final evidence check verifies these input hashes again.
