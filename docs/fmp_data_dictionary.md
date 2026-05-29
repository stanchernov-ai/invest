# FMP Data Dictionary — SC Invest Boardroom

**Status:** Active reference  
**Last validated:** May 28, 2026 (live probe via `tools/validate_fmp_fields.py` + production `get_fmp_advanced_metrics` path)  
**Base URL (stable):** `https://financialmodelingprep.com/stable`  
**Legacy v3 base:** `https://financialmodelingprep.com/api/v3` — **403 on Starter tier** for several paths; do not rely on v3 in production.

This document is the single source of truth for which FMP endpoints and fields the boardroom pipeline uses, which URLs are known dead, which JSON keys are wrong or always empty, and what to do next when extending market data.

---

## How to re-validate

```powershell
.venv\Scripts\python.exe tools\validate_fmp_fields.py
.venv\Scripts\python.exe tools\validate_fmp_fields.py --symbols AAPL,NVDA,PLTR,SPY,QQQ --json-out tools\fmp_field_probe_results.json
```

After code changes, confirm AAPL returns non-`Unknown` `next_earnings` and non-`N/A` `consensus`:

```powershell
.venv\Scripts\python.exe -c "import asyncio, os; from dotenv import load_dotenv; import aiohttp; load_dotenv(); from src.data.fmp_client import get_fmp_advanced_metrics; asyncio.run((lambda: None)())"
```

---

## Known bad URLs (do not call)

These return **HTTP 404** (empty list in our client) on the current Starter/stable plan. They were previously wired in `fmp_client.py` and produced **silent empty data** — not intermittent failures.

| Bad URL | HTTP | Replacement | Notes |
|---------|------|-------------|--------|
| `/stable/rating?symbol=` | 404 | `/stable/grades-consensus?symbol=` | Old field `ratingRecommendation` does not exist on stable. Use `consensus` (e.g. `"Buy"`). |
| `/stable/earning_calendar?symbol=` | 404 | `/stable/earnings?symbol=` | Underscore path is wrong. Use hyphenated `earnings`. |
| `/stable/earnings-calendar?symbol=` | 200 but **wrong shape** | `/stable/earnings?symbol=` | Returns global calendar (~4000 rows); **symbol filter does not work** (0 rows for AAPL in probe). |
| `/stable/upgrades-downgrades-consensus?symbol=` | 404 | `/stable/grades-consensus?symbol=` | — |

### Starter tier — batch endpoints blocked (402)

Validated May 29, 2026 via `tools/probe_starter_tier.py` on the live Starter API key.

| Bad URL | HTTP | Replacement | Notes |
|---------|------|-------------|--------|
| `/stable/batch-quote?symbols=TLT,VXX` | **402** | Two parallel `/stable/quote?symbol=` (already in `get_fmp_macro`) | Payment/plan gate — not available on Starter. Savings would be ~130ms even if it worked; not a timeout lever. |
| `/api/v3/quote/TLT,VXX` | **403** | Same parallel `/stable/quote` | Legacy v3 batch — deprecated for non-legacy subscribers. |

**Do not retry batch optimizations on Starter.** Re-probe only after a plan upgrade.

### v3 paths (plan-blocked — 403, not a syntax fix)

| URL | HTTP | Action |
|-----|------|--------|
| `/api/v3/rating/{symbol}` | 403 | Use stable `grades-consensus` |
| `/api/v3/earning_calendar?symbol=` | 403 | Use stable `earnings` |
| `/api/v3/stock_news` | 200 | **In use** by `news_client.py` (v3 still works for news) |
| `/api/v3/stock-screener` | 200 | **In use** by `scout.py` fallback |

---

## Endpoints in production use

| Telemetry key | Endpoint | Equities | ETFs (SPY/QQQ/…) | Consumer |
|---------------|----------|----------|------------------|----------|
| `prof` | `GET /profile?symbol=` | OK | OK | ETF flag, beta, image, sector, market cap |
| `quote` | `GET /quote?symbol=` | OK | OK | Price, 52w range, volume, MAs |
| `ratio` | `GET /ratios-ttm?symbol=` | OK | **Empty** | PE, PEG, P/S, D/E, margins |
| `met` | `GET /key-metrics-ttm?symbol=` | OK | **Empty** | ROE, FCF yield, ROIC |
| `grades_consensus` | `GET /grades-consensus?symbol=` | OK | **Empty** | Analyst consensus, FCS |
| `pt` | `GET /price-target-consensus?symbol=` | OK | **Empty** | Target, upside, FCS |
| `earn` | `GET /earnings?symbol=` | OK | **Empty** | Next earnings, estimates, FCS |
| `growth` | `GET /financial-growth?symbol=` | OK | **Empty** | Rev/EPS growth |
| `historical_metrics` | `GET /historical-price-eod/light?from=&to=` | OK | OK | 3M trend, 3Y CAGR |
| (history job) | Same EOD light, ~370d window | OK | OK | TWR in `history.py` |
| `MACRO_TLT_VXX` | `GET /quote?symbol=TLT` + VXX | OK | OK | Hedge context in prompt |
| `FUNDAMENTAL_NEWS` | `GET /api/v3/stock_news` | OK | OK | Headlines |

---

## Field dictionary by endpoint

### `GET /stable/profile?symbol=`

| JSON field | Use in pipeline | Reliability (equity) | Notes |
|------------|-----------------|----------------------|--------|
| `symbol` | — | 100% | |
| `companyName` | — | 100% | |
| `sector` | Prompt | 100% | Simons concentration |
| `industry` | — | 100% | |
| `marketCap` | Prompt | 100% | **Not** `mktCap` (always blank) |
| `beta` | Prompt | 100% | |
| `image` | HTML briefing | 100% | |
| `isEtf`, `isFund` | ETF routing | 100% | |
| `averageVolume` | — | 100% | Prefer over quote `avgVolume` (missing) |
| `changePercentage` | — | 100% | Profile has it; quote uses same name |

**Exclude (wrong or empty on stable profile):** `mktCap` — use `marketCap`.

---

### `GET /stable/quote?symbol=`

| JSON field | Use in pipeline | Reliability | Notes |
|------------|-----------------|----------------------|--------|
| `price` | Required | 100% | Fatal if missing |
| `change`, `changePercentage` | — | 100% | **Not** `changesPercentage` |
| `dayHigh`, `dayLow` | — | 100% | |
| `yearHigh`, `yearLow` | `% off 52w high` | 100% | |
| `volume` | — | 100% | |
| `marketCap` | Fallback cap | 100% | |
| `priceAvg50`, `priceAvg200` | — | 100% | |
| `open`, `previousClose` | — | 100% | |

**Exclude on quote:** `pe`, `eps`, `avgVolume` — not populated on stable quote (use ratios / profile).

---

### `GET /stable/ratios-ttm?symbol=`

| JSON field | Pipeline field | Reliability |
|------------|----------------|-------------|
| `priceToEarningsRatioTTM` | `fwd_pe` | 100% |
| `priceToEarningsGrowthRatioTTM` | `peg` | 100% |
| `priceToSalesRatioTTM` | `ps` | 100% |
| `debtToEquityRatioTTM` | `de` | 100% |
| `grossProfitMarginTTM` | — | 100% | Future KPI |
| `operatingProfitMarginTTM` | — | 100% | |
| `dividendYieldTTM` | — | 100% | |
| `returnOnEquityTTM` | — | **0%** on ratios | Use `key-metrics-ttm` for ROE |

**Exclude on ratios-ttm for ROE:** always empty — read ROE from `key-metrics-ttm`.

---

### `GET /stable/key-metrics-ttm?symbol=`

| JSON field | Pipeline field | Reliability |
|------------|----------------|-------------|
| `returnOnEquityTTM` | `roe` | 100% |
| `returnOnInvestedCapitalTTM` | — | 100% | |
| `freeCashFlowYieldTTM` | `fcf_yield` | 100% | Decimal; display as % |
| `earningsYieldTTM` | — | 100% | |
| `netDebtToEBITDATTM` | — | 100% | |
| `currentRatioTTM` | — | 100% | |

**Exclude on key-metrics-ttm:** `debtToEquityRatioTTM`, `peRatioTTM`, `priceToSalesRatioTTM`, `marketCapTTM` — empty in probe; use `ratios-ttm` / `profile` instead.

---

### `GET /stable/grades-consensus?symbol=`

| JSON field | Pipeline field | Reliability |
|------------|----------------|-------------|
| `consensus` | `consensus` | 100% | e.g. `"Buy"` |
| `strongBuy`, `buy`, `hold`, `sell`, `strongSell` | — | 100% | Optional display |

**Replaces:** `/stable/rating` + `ratingRecommendation` (dead).

---

### `GET /stable/price-target-consensus?symbol=`

| JSON field | Pipeline field | Reliability |
|------------|----------------|-------------|
| `targetConsensus` | `price_target` | 100% |
| `targetHigh` | `target_high` | 100% |
| `targetLow` | `target_low` | 100% |
| `targetMedian` | — | 100% | |

---

### `GET /stable/earnings?symbol=`

| JSON field | Pipeline field | Reliability |
|------------|----------------|-------------|
| `date` | `next_earnings` | 100% | Nearest future row |
| `epsEstimated` | `eps_estimated` | 100% | |
| `revenueEstimated` | `revenue_estimated` | 100% | Large integers |
| `epsActual`, `revenueActual` | — | Past rows only | |

**Replaces:** `/stable/earning_calendar` (dead).

---

### `GET /stable/financial-growth?symbol=`

| JSON field | Pipeline field | Reliability |
|------------|----------------|-------------|
| `revenueGrowth` | `rev_growth` | 100% | Decimal ratio (0.06 = 6%) |
| `epsgrowth` | `eps_growth` | 100% | **Lowercase** `epsgrowth`, not `epsGrowth` |
| `grossProfitGrowth` | — | 100% | |
| `operatingIncomeGrowth` | — | 100% | |

---

### `GET /stable/historical-price-eod/light`

| JSON field | Use | Reliability |
|------------|-----|-------------|
| `date` | Series keys | 100% |
| `price` | Close | 100% |
| `volume` | — | Present | |

---

### Scout / news (v3)

| Endpoint | Fields used | Notes |
|----------|-------------|--------|
| `GET /api/v3/stock_news` | `symbol`, `title` | Add `publishedDate` when extending red team |
| `GET /api/v3/stock-screener` | `symbol` only | Rich row discarded today |

---

## Pipeline metric dict (`get_fmp_advanced_metrics`)

Returned keys after May 2026 fix:

| Key | Source | In `mega_prompt` |
|-----|--------|------------------|
| `current_price` | quote | Yes |
| `fwd_pe`, `peg`, `ps`, `de` | ratios-ttm | Partial (PE only before; all after fix) |
| `roe`, `fcf_yield` | key-metrics-ttm | Yes (after fix) |
| `beta`, `sector`, `market_cap` | profile | Yes (after fix) |
| `pct_off_52w_high` | quote + price | Yes (after fix) |
| `3m_trend`, `3y_cagr` | EOD light | Yes |
| `rev_growth`, `eps_growth` | financial-growth | Yes |
| `consensus` | grades-consensus | Yes (after fix) |
| `price_target`, `target_high`, `target_low` | price-target-consensus | Partial |
| `next_earnings`, `eps_estimated`, `revenue_estimated` | earnings | Yes (after fix) |
| `fcs_score`, `fcs_rationale` | Derived | Yes |
| `image` | profile | HTML only |

---

## Fallback rules

1. **Profile missing** → `yfinance.Ticker.info`; fatal if still empty.
2. **Quote/ratios missing** → yfinance for price and valuation.
3. **Grades-consensus or earnings empty** → load yfinance **only for that field** if not already loaded (empty `[]` must not skip fallback when profile succeeded).
4. **ETFs** → skip equity fundamentals; price + EOD + beta/image only.

---

## yfinance fallback

Used when FMP profile/quote/ratios fail, or when consensus/earnings empty. Maps: `recommendationKey` → consensus, `targetMeanPrice`, `revenueGrowth`, `earningsGrowth`, etc. Full blob stored in telemetry `yfinance_fallback`.

---

## Findings & action plan

### Completed (this implementation)

- [x] Data dictionary document (this file)
- [x] Replace dead `rating` → `grades-consensus`
- [x] Replace dead `earning_calendar` → `earnings`
- [x] Parse `key-metrics-ttm` (ROE, FCF yield)
- [x] Empty-list fallback to yfinance for consensus/earnings
- [x] Extend `mega_prompt` with KPIs agents already expect (PEG, P/S, D/E, beta, consensus, sector, macro)
- [x] Market regime block (portfolio 3M vs QQQ + TLT/VXX)
- [x] `tools/validate_fmp_fields.py` probe script

### P1 — Efficiency

- [x] **Single EOD fetch per symbol** — `prefetch_eod_cache()` in prepare; `get_fmp_advanced_metrics` + `history.build_account_returns` share cache (`EOD_LOOKBACK_DAYS` = 1095, history slices to 370d)
- [x] **Dedupe SPY/QQQ** in prepare (benchmark prefetch + skip duplicate advanced-metrics fetch)
- [x] **Macro quotes (Starter)** — parallel `/stable/quote` for TLT + VXX in `get_fmp_macro` (~330ms). **`batch-quote` returns HTTP 402 on Starter — not pursued.** Revisit only after plan upgrade (`tools/probe_starter_tier.py`).
- [x] **News** — `publishedDate` / `date` on headline lines (`[SYM] (YYYY-MM-DD): title`)

### P2 — Accuracy / personas

- [ ] **Relative strength** — `rel_strength_3m_vs_qqq` per ticker in prompt (Livermore)
- [ ] **Portfolio sector weights** — aggregate `sector` × position $ (Simons)
- [ ] **Buffett deterministic guardrails** — cap conviction in code when PE>40 or P/S>10
- [x] **Mandate CAGR** — `prepare.py` passes real portfolio **12M TWR** from `account_returns["returns"]["Total"]["12m"]` into `generate_dynamic_mandate` (fallback `0.15` if missing; projection still caps at 15% inside the function)
- [ ] **Growth display** — `fmt_growth` treats decimal 0.06 as 6% in prompts

### P3 — New endpoints (not on current calls)

- [ ] 10Y Treasury / VIX for red team macro (FMP rates or index endpoint)
- [ ] Estimate revisions / short interest (tier + cost review)
- [ ] Peer-relative PEG (needs peer set + batch ratios)

### Documentation hygiene

- [ ] Update `docs/technical_solution.md` Appendix D endpoint table to match this dictionary
- [ ] On each FMP plan upgrade, re-run `tools/validate_fmp_fields.py` and update **Last validated** date

---

## Telemetry debugging

In `api_telemetry_{run_id}_prepare.json`, per symbol:

- `"rating": {"response": []}` → **legacy bug** (404 endpoint); after fix look for `grades_consensus`
- `"earn": {"response": []}` → **legacy bug**; after fix should list earnings rows
- Empty `ratio` / `quote` with populated `yfinance_fallback` → expected degradation path

---

## Changelog

| Date | Change |
|------|--------|
| 2026-05-28 | Initial dictionary from live validation; dead URL table; P0 implementation |
| 2026-05-28 | P1: shared `prefetch_eod_cache`, news `publishedDate` in headlines |
| 2026-05-29 | Starter probe: `batch-quote` = HTTP 402; macro stays parallel `/quote`. Mandate wired to real 12M TWR in prepare. |
