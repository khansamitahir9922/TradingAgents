# Yahoo research-data provenance

Verified on **2026-10-12**, for **EQ_US_NVDA**, using **yfinance 1.7.0** (pandas 3.0.6, Python 3.11.9). This is research data, never a production feed. The record is `YAHOO_VERIFICATION` in `investment_engine/market/importers/yahoo_semantics.py`. A different installed yfinance version is refused until verified.

`verified_from = 2019-01-01`. The exact cited split history in this range is **2021-07-20 × 4**, **2024-06-10 × 10**. Imports cannot cover earlier dates. A new, missing, moved or differently valued in-range split stops imports until citations are reviewed. Pre-range actions are excluded, not silently treated as verified. The recorded history contains four excluded splits and 25 excluded dividends.

## Requests and recorded evidence

The original responses and their metadata are in `tests/engine/fixtures/yfinance/`; reference IDs, links, publication dates and retrieval details are in `tests/engine/fixtures/reference/nvda_reference.json`. Values are preserved as downloaded. No runtime import depends on these repository fixtures.

| Recorded call | Parameters | Receipt (UTC, 2026-10-12) |
|---|---|---|
| `Ticker('NVDA').splits`, before | Full-history property, no start/end | 08:25:49 |
| `Ticker('NVDA').dividends` | Full-history property, no start/end | 08:25:50 |
| `Ticker('NVDA').history` | start 2019-01-01, end 2026-10-10 (exclusive), interval 1d | 08:25:51 |
| `Ticker('NVDA').history` | period 730d, interval 1h | See original metadata |
| `Ticker('NVDA').splits`, after | Full-history property, no start/end | 08:25:53 |
| `Ticker('NVDA').history` | period max, actions True; action rows retained | See original metadata |
| Q1 counterexample `Ticker('NVDA').history` | start 2021-01-04, end 2021-03-31, interval 1d, actions True | See original metadata |

The daily and hourly bar calls use `auto_adjust=False, actions=False, repair=False, back_adjust=False, prepost=False`. The Q1 counterexample uses `actions=True` and no explicit `prepost`; it reports zero splits because later events fall outside the request. It must never supply reconstruction history. Full-history action properties use the vendor library's property calls; the pinned version and fixture comparisons establish their delivered action values. Each operational import uses fresh before/after split requests and checks equality **inside the verified range**.

Yahoo defines adjusted close as: “the closing price after adjustments for all applicable splits and dividend distributions.” [Yahoo Help, retrieved 2026-10-12](https://help.yahoo.com/kb/SLN28256.html). This definition does not establish volume semantics. `auto_adjust=False` also does not prove that delivered OHLC are as traded.

## Field decisions

| Field | Semantics | Transformation | Maximum measured error / limit |
|---|---|---|---|
| `SPLIT_RATIO` | `UNADJUSTED` | `IDENTITY` | 0; cited ratios and ex-dates agree |
| `D1_PRICE` | `SPLIT_ADJUSTED_AS_OF_DOWNLOAD` | `SPLIT_RECONSTRUCTION` | $0.0029 after quantization; $0.01 tolerance |
| `D1_VOLUME` | `SPLIT_ADJUSTED_AS_OF_DOWNLOAD` | `SPLIT_RECONSTRUCTION` | 1.6915% decisive reference error; 3% tolerance |
| `H1_PRICE` | `UNDETERMINED` | `BLOCKED` | Unexplained hourly/daily differences |
| `H1_VOLUME` | `UNDETERMINED` | `BLOCKED` | No comparable independent hourly reference |
| `DIVIDEND_AMOUNT` | `SPLIT_ADJUSTED_AS_OF_DOWNLOAD` | `SPLIT_RECONSTRUCTION` | 0 after quantization |

Blocked hourly fields cannot be written, even where the split factor is 1. This prevents an apparent absence of later splits from being mistaken for verification. **M1 and batch 3 are not complete.**

## Splits and dividend anchors

The [NVIDIA 2021 split announcement](https://www.sec.gov/Archives/edgar/data/1045810/000104581021000056/pr-may2021.htm) establishes 4:1, adjusted trading from July 20 (`NVDA-8K-2021-05-21`). The [2024 filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581024000113/nvda-20240522.htm) establishes 10:1, adjusted trading from June 10 (`NVDA-8K-2024-05-22`). Earlier historical events remain in the evidence files but do not enter imports.

| Ex-date | Yahoo dividend | Later factor | Reconstructed declared amount | Reference |
|---|---|---|---|---|
| 2021-06-09 | 0.004 | 40 | $0.16 | [NVIDIA results, record date June 10](https://www.sec.gov/Archives/edgar/data/1045810/000104581021000063/q1fy22pr.htm), `NVDA-8K-2021-05-26` |
| 2024-03-05 | 0.004 | 10 | $0.04 | [NVIDIA results, record date March 6](https://www.sec.gov/Archives/edgar/data/1045810/000104581024000028/q4fy24pr.htm), `NVDA-8K-2024-02-21` |
| 2024-06-11 | 0.01 | 1 | $0.01 | 2024 split filing above |
| 2026-06-04 | 0.25 | 1 | $0.25 | [NVIDIA quarterly filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000052/nvda-20260426.htm), `NVDA-10Q-2026-04-26` |

Record dates in company publications and vendor ex-dates are recorded separately; they are not interchangeable. The two pre-split anchors distinguish adjusted from unadjusted amounts; factor-1 controls do not. These anchors establish the observed basis, not independent validation of every historical dividend date or amount.

## Daily price anchors

| Session / field | Reconstructed Yahoo | As-traded reference | Absolute error after quantization |
|---|---|---|---|
| 2021-07-19 close | 751.1900 | 751.19 | 0 |
| 2024-06-06 close | 1209.9800 | 1209.98 | 0 |
| 2024-06-07 close | 1208.8800 | 1208.88 | 0 |
| 2024-06-07 high | 1216.9200 | 1216.9171 | 0.0029 |
| 2024-06-10 close | 121.7900 | 121.79 | 0 |
| 2024-06-11 close | 120.9100 | 120.91 | 0 |

The July close comes from the dated [Motley Fool publication](https://www.fool.com/investing/2021/07/20/is-nvidia-stock-a-buy-now-after-the-4-for-1-stock/) (`FOOL-2021-07-20`). The 2024 explicitly unadjusted bars come from [Massive's dated split API article](https://massive.com/blog/using-the-split-api-endpoint-to-handle-the-nvidia-stock-split) (`MASSIVE-BLOG-2024-06-11`), an independent vendor. At least one anchor covers each split epoch (factor 40, 10 and 1). Close differs from Adj Close around dividends; Adj Close is never imported as a raw price.

Three archived MarketWatch closes retained by Claude are supporting material only. The approved July acceptance window and primary decision do not depend on them.

## Daily volume anchors

| Session | Role | Yahoo shares / factor | Massive shares | Relative error | Identity error |
|---|---|---|---|---|---|
| 2024-06-06 | Decisive, factor 10 | 66,469,600 | 65,723,115 | 1.1358% | 911.3580% |
| 2024-06-07 | Decisive, factor 10 | 41,238,600 | 40,552,650 | 1.6915% | 916.9150% |
| 2024-06-10 | Control, factor 1 | 313,434,100 | 307,078,688 | 2.0696% | Same value |
| 2024-06-11 | Control, factor 1 | 222,551,200 | 218,971,550 | 1.6348% | Same value |

All selected decisive references satisfy 3% under reconstruction and fail by at least 50% under identity. Post-split controls measure a vendor-to-reference gap but do not distinguish bases. Venue coverage and late-trade handling are possible explanations, not established causes. Volumes are never rescaled to force agreement. The old 0.5% rule would accept neither interpretation and was explicitly replaced in M1-12. `max_error = 0.0169` in the record is the decisive relative maximum rounded to four decimals.

Dollar-volume continuity is supporting only. The synthetic 4:1 counterexample has identity dollar volume continuous despite being wrong by fourfold. Its test remains blocked without a primary anchor.

## Hourly investigation and coverage

The saved hourly response has 5,054 bars across 728 overlapping sessions, beginning 2023-11-10. This is a measured snapshot, not a promised retention window. **35 expected hourly starts are absent**, including every half-day's final bar and two whole sessions. Detailed dates and comparisons are in the fixtures README.

At a $0.01 threshold, high/low differences affect **169 sessions in vendor units**, or **181 under the split-reconstruction hypothesis in as-traded units**. The largest outward difference is February 9, 2026: hourly high 198.725006 versus daily high 193.660004. Neither auction-print hypotheses nor missing bars explain the full pattern. Prices remain pending.

Hourly volume sums are 0.967 and 0.954 of Massive's daily unadjusted volume on June 6–7, 2024 (supporting only). Different session boundaries, auctions and eligible trades can change aggregates. No like-for-like independent hourly anchor or explicit Yahoo intraday-volume statement exists in the reviewed evidence. Hourly volume remains blocked. A verification-only external source needs compatible coverage and history; an account alone does not guarantee usable evidence.

## Reconstruction, precision and availability

For exchange date d, `F(d)` multiplies all cited ratios with `d < ex_date <= download date`, including splits after the requested window. Price and dividend are multiplied by F; volume is divided by F. Floats cross through M1-02 `from_float64` at the delivered representation's quantum **before** reconstruction, then final values use half-even rounding to price 0.0001 and shares 1. Integers and Decimal inputs stay exact.

Delivered floats often carry 15–17 decimal digits in their round-tripping representation; those digits are not a guarantee of market accuracy. Typical quoted historical price increments are about 0.001 in split-adjusted units, with narrower increments in some fields. If a vendor rounds with unit u, reconstruction amplifies that rounding uncertainty to at most approximately F × u (or F × u / 2 for a known nearest-rounding rule). Yahoo does not establish a single fixed rounding rule for every field, so there is no universal error bound inferred from float digits. The measured anchor maximum is $0.0029 after quantization; the float-level June 7 high discrepancy before quantization is about $0.00291343. A stored quantum finer than this uncertainty adds no information.

Reconstructed shares are rounded to whole shares; fractional pre-rounding quotients can lose at most half a share to that rounding. Inter-vendor coverage differences are separate and remain visible. Declared dividend anchors match at 0.0001, not necessarily at the original binary representation.

History remains append-only. First-seen actions are `BACKFILL_ASSUMED` from exchange-local ex-date midnight; corrections are `OBSERVED` from receipt, never backdated. Bars use session end plus explicit nonnegative backfill latency. `received_at` and `processed_at` come only from the injected Clock. Providers never share revisions.
