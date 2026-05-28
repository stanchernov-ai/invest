# SC Invest Boardroom — Agent Guardrails

**Status:** Active
**Last Updated:** May 28, 2026
**Owner:** Stan

This document is the single source of truth for the **guardrails** that constrain the
multi-agent investment boardroom: what each agent is and isn't allowed to do, where each
rule is enforced, and where the gaps are. It doubles as an **audit** — every guardrail is
tagged with how it's currently enforced:

| Tag | Meaning |
|-----|---------|
| 🟢 **Code-enforced** | Deterministic Python logic; the LLM cannot violate it. |
| 🟡 **Prompt-only** | Stated in a system prompt; the LLM is *trusted* to comply (not verified). |
| 🔴 **Gap** | Identified, not yet implemented (or implemented but not enforced). |

> **Guiding principle — Defense in depth.** Any guardrail that protects money or data
> integrity should ultimately be 🟢 code-enforced. Prompts shape *behavior*; they must not
> be the *only* thing standing between a hallucination and a trade instruction.

---

## 1. Guardrail layers

The pipeline applies guardrails in six layers, outermost (cheapest to fail) first:

1. **Environment / config** — required secrets present before any work begins.
2. **Data integrity (pre-flight)** — no garbage data reaches the LLMs.
3. **Schema** — every structured LLM output is bound to a Pydantic contract.
4. **Agent behavior (persona prompts)** — each agent stays in its lane.
5. **Post-processing / compliance** — financial limits and procedural audits.
6. **Infrastructure** — concurrency, retries, idempotency, timeouts.

---

## 2. Current guardrails catalog

### Layer 1 — Environment / config
| Guardrail | Where | Status |
|-----------|-------|--------|
| Required env vars present (`GEMINI_API_KEY`, `FMP_API_KEY`, `AZURE_STORAGE_CONNECTION_STRING`, `SENDER_EMAIL`) | `settings.validate()` + `main_batch()` abort | 🟢 **Fixed (2026-05-28)** — `main_batch()` now aborts (`FATAL ABORT`) if `settings.validate()` returns `False`. Previously the return value was ignored. |

### Layer 2 — Data integrity (pre-flight)
| Guardrail | Where | Status |
|-----------|-------|--------|
| Advanced-metrics fetch corruption kills the run before any LLM call | `main.py` "FATAL ABORT" on exception in metrics gather | 🟢 |
| `FatalDataError` raised when all data sources (FMP + yfinance) are exhausted for a symbol | `fmp_client.get_fmp_advanced_metrics` | 🟢 |
| **Pre-Flight Data Oracle** kill switch — any asset with `$0.00` price ⇒ `is_valid=false` ⇒ hard abort ("DATA ORACLE SECURITY ABORT TRIGGERED") | `engine.execute_data_oracle` + `main.py` stream guard | 🟢 (LLM decides `is_valid`, but the **abort is code-enforced** and fails safe: any Oracle error ⇒ invalid) |
| Oracle must ignore `N/A` secondary metrics (only `$0.00` price trips it) | `data_oracle` prompt | 🟡 |
| Single bad ticker aborts the whole FMP fetch (fail-fast during active dev) | `main.py` | 🟢 (intentional; see backlog) |

### Layer 3 — Schema
| Guardrail | Where | Status |
|-----------|-------|--------|
| Every structured agent output bound to a Pydantic model (verdicts, synthesis, oracle, etc.) | `core/schemas.py`, `engine._run_agent` | 🟢 |
| Debate narrative must be 3 newline-separated paragraphs | `ChiefOfStaffSynthesis.boardroom_brawl` description | 🟡 (prompt/schema description; rendering splits on `\n`) |

### Layer 4 — Agent behavior (see §3 for per-agent detail)
Cross-cutting `META_DIRECTIVE` applied to all voting members:
| Guardrail | Status |
|-----------|--------|
| Adversarial debate (no sycophancy; dissent encouraged) | 🟡 |
| **Wash-sale avoidance** — no sell on assets held < 30 days | 🟡 (prompt-only for both panelists *and* Chairman) |
| No "naked lists" — explicit written rationale per asset | 🟡 |

### Layer 5 — Post-processing / compliance
| Guardrail | Where | Status |
|-----------|-------|--------|
| **MAX 3 BUYS / day** | Chairman prompt | 🟡 **prompt-only** (the LLM is trusted to count) |
| **10% liquidation cap** (with fractional trims) | Chairman prompt + scratchpad math | 🟡 **prompt-only** (LLM does the arithmetic; see Action Tracker 2.1) |
| Reallocation Deathmatch (fund every buy with a sell/trim) | Chairman prompt; audited by Compliance | 🟡 |
| Mandatory macro hedge (TLT/VXX) | Chairman prompt | 🟡 |
| Democratic majority rule; no hallucinated ties | Chairman prompt | 🟡 (no deterministic tie-break — see §4) |
| Compliance audit (originator, top-3, deathmatch, alpha-pick) ⇒ PASS/FAIL | `compliance` agent | 🟡 (hedge exemption is a **hardcoded prompt string** — brittle) |
| Post-flight QA (post-mortem, system architect, prompt engineer) | `run_post_flight_qa` | 🟡 (advisory; reviews a single run) |

### Layer 6 — Infrastructure
| Guardrail | Where | Status |
|-----------|-------|--------|
| Gemini concurrency cap (`API_SEMAPHORE = 15`) | `agents.py` | 🟢 |
| Gemini retry w/ exponential backoff (3 attempts) | `call_gemini_async` | 🟢 |
| FMP retry/backoff + rate-limit handling (`tenacity`, 5 attempts) | `fmp_client.fetch_json_endpoint` | 🟢 |
| History engine is non-fatal & concurrency-capped (5) | `history.build_account_returns` | 🟢 |
| Blob-lease distributed lock (idempotent single run) | `storage_client` / `function_app` | 🟢 (lease-duration hardening pending — Action Tracker 1.1) |

---

## 3. Per-agent behavioral guardrails

| Agent | Role | Key constraints | Notable gap |
|-------|------|-----------------|-------------|
| **Buffett** | Deep value | Conviction **≤ 7/10** if P/E > 40 or P/S > 10; value-based reason required to upgrade Hold→Buy; Hold/Pass on $0/null data | Cap is 🟡 prompt-only; drifts toward growth (e.g., MNDY) — see §4 |
| **Lynch** | Growth (GARP) | No static PEG cutoff; relative valuation vs peers | 🟡 |
| **Livermore** | Momentum / tape | Primacy of the tape; forbidden from fundamental justification; sell on broken 3M trend | 🔴 **No null-data guard** → sells everything if momentum reads 0 (see §4) |
| **Huang** | Tech moat | Accelerated-compute lens; dismiss legacy/component models | 🟡 |
| **Simons** | Quant | **Null/zero/invalid data ⇒ Hold/Pass only**; Kelly sizing; size→0% on negative alpha/FCS | 🟡 (good model for Livermore to copy) |
| **Clerk (Ray Dalio)** | Chief of Staff / synthesis | Radical transparency; 3-paragraph brawl; exact star-rating format | 🟡 (synthesis contradiction bug — see §4) |
| **Chairman (Druckenmiller)** | Aggregator | Majority rule; 3-buy cap; 10% cap; wash-sale; hedge mandate; anti-hallucination; scratchpad math | 🟡 financial limits are prompt-only; no deterministic tie-break |
| **Data Oracle** | Pre-flight | $0.00 price kill switch; ignore N/A | 🟢 abort / 🟡 decision |
| **Red Teamer** | Adversary | Must weaponize real news; isolated (no echoing the board) | 🟡 |
| **Compliance (Markopolos)** | Auditor | Originator/top-3/deathmatch/alpha-pick ⇒ PASS/FAIL | 🟡 hardcoded hedge exemption |
| **QA trio** | Post-flight | Procedural, technical, and behavioral-drift review | 🟡 advisory |

---

## 4. Gaps & recommended improvements (prioritized)

### P0 — Money/data integrity (promote 🟡 → 🟢)
1. ~~**Enforce env-var validation.**~~ ✅ **Done (2026-05-28)** — `main_batch()` now aborts if `settings.validate()` fails.
2. **Move the financial limits into deterministic Python.** Today MAX 3 BUYS, the 10% liquidation cap, and wash-sale avoidance are *prompt-only* — the LLM does the arithmetic and we hope it's right. Add a post-Chairman validation pass that:
   - counts buys and rejects/truncates beyond 3,
   - sums trim/sell dollar value and rejects/scales anything over 10% of portfolio value,
   - blocks any sell on a position held < 30 days (we already parse purchase dates).
   This is the single biggest robustness upgrade. *(Ties to Action Tracker 2.1.)*

### P1 — Agent resilience
3. **Livermore "Stand Aside" protocol.** Give Livermore the same null-data guard Simons has: if the 3M trend / momentum is missing or zero, he must abstain (Hold/Pass) rather than sell the book. Defense-in-depth even though the FMP momentum fix removed the common trigger.
4. **Deterministic tie-break protocol.** Replace the Chairman's "don't hallucinate ties" prompt with a hardcoded hierarchy for genuine splits (e.g., conviction-weighted score → analyst implied upside → status-quo Hold). Encode it in Python so the outcome is reproducible.
5. **Fix the synthesis contradiction.** The Clerk occasionally pairs a Buy verdict with a *dissenter's* negative quote as the "Champion." Validate in post-processing that the champion quote's sentiment/author matches the winning side — now more visible because the new verdict pills surface champion quotes prominently.

### P2 — Brittleness / maintainability
6. **De-hardcode the compliance hedge exemption.** The TLT/VXX exemption is a literal prompt string. Drive "what counts as a hedge" from a small config list referenced by both the Chairman and Compliance, so risk-control changes don't require a prompt rewrite + redeploy.
7. **Buffett value anchor enforcement.** The conviction-cap (≤7 for rich multiples) is prompt-only; consider clamping it in code, or at least surfacing violations in the QA digest.

### P3 — Systemic
8. **yfinance / Yahoo failover risk.** yfinance is still the fundamentals fallback; Azure IPs get blocked by Yahoo. Decide between (a) removing the dependency and hard-failing cleanly, or (b) a paid backup source.
9. **Azure 10-min execution ceiling.** Gemini/FMP backoff + the new ~33s history engine eat into the budget. Track worst-case runtime; consider the cache-warmer idea.
10. **Context-window saturation.** Growing debate logs/ledgers fed back to the models risk attention drift; add round-summarization if token usage climbs.

---

## 5. How to extend this

When you add or change a guardrail:
1. Decide the **layer** (§1) and prefer 🟢 code-enforcement for anything protecting money or data.
2. Add/update the row in §2 (and §3 if it's persona-specific) with its enforcement tag and file location.
3. If it starts life as 🟡 prompt-only, log a P0/P1 follow-up in §4 to promote it to 🟢.
