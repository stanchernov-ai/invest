# Agent Optimization Handoff — Production Pipeline

**Status:** Active handoff for developers  
**Last updated:** May 30, 2026 (deploy batch staged — Legal Counsel QA local)  
**Owner:** Stan  
**SSOT for:** May 2026 agent audit, telemetry baseline, allocation/funding rules (shipped), and **remaining** runtime optimizations.

**Related**

| Doc | Purpose |
|-----|---------|
| [`agent_architecture.md`](agent_architecture.md) | Roster, diagrams, QA stack |
| [`qa_layers.md`](qa_layers.md) | Which QA module runs when |
| [`cursor_dev_plane_handoff.md`](cursor_dev_plane_handoff.md) | Cursor agents, ecosystem_state, post-job sync |
| [`product_principles.md`](product_principles.md) | Board in Python, fail closed |
| [`post_deliver_checklist.md`](post_deliver_checklist.md) | After each deliver |

**Evidence run (prod):** `20260529_225159` — canonical post–Action Plan sprint. Pull via  
`.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id 20260529_225159`

**Telemetry baseline run:** `20260529_152151` — pre–Tier 1 deliver token profile (~151k QA tokens).

---

## 1. Executive summary

The **debate bottleneck is largely resolved** on `vote_engine` days: chairman Pro and Markopolos LLM are skipped; debate dropped from ~287s to ~124s on comparable runs.

**Tier 1 (A1–A4) and B1 shipped** in `a64bcd9` and `748ad6c`. Deliver QA remains the main token sink (~50%+ on bypass days). **B2** (prompt_engineer skip) and **B3** (architect demote) are the next tickets.

**Do not implement Tier 2–3 tickets in this doc unless explicitly assigned** — pick from [`action_tracker.md`](action_tracker.md) open items.

---

## 2. Telemetry snapshot — run `20260529_152151`

| Metric | Value |
|--------|-------|
| `allocation_source` | `vote_engine` |
| `chairman_bypassed` | `true` |
| `compliance_source` | `python_only` |
| Debate duration | ~124s |
| Deliver duration | ~137s |
| LLM agents (merged) | 12 |
| Total tokens (est.) | ~286k (~$0.21 QA scorecard est.) |

### Debate-phase LLM agents (7 keys)

| Agent | Invocations | Tokens | Thinking tokens | Model |
|-------|-------------|--------|-----------------|-------|
| livermore | 2 | 28,045 | 6,374 | Pro |
| buffett | 2 | 27,720 | 5,579 | Pro |
| lynch | 2 | 26,930 | 4,784 | Pro |
| huang | 2 | 26,495 | 4,885 | Pro |
| simons | 2 | 25,628 | 3,643 | Pro |
| clerk | 1 | 17,789 | 986 | Flash |
| red_teamer | 1 | ~17k (est.) | — | **Flash** (B1 shipped `748ad6c`) |

**Not invoked:** `chairman`, `compliance`, Munger (buffett/huang/lynch concentration pass).

### Deliver-phase LLM agents (5 keys)

| Agent | PASS/FAIL (152151) | Tokens | Notes |
|-------|-------------------|--------|-------|
| post_mortem_qa | PASS | 24,942 | Deterministic PASS; LLM still ran |
| system_architect | FAIL (1 CRITICAL) | 23,224 | Overlaps other QA |
| prompt_engineer | FAIL (6 CRITICAL) | 24,215 | Noisy; deterministic persona pre-check exists |
| graphics_designer_qa | FAIL (3 CRITICAL) | 18,647 | Useful signal for briefing layout |
| qa_integrity_auditor | FAIL (1 CRITICAL) | 25,232 | Pro model; 90s timeout |

**QA does not block the investor briefing email** — findings go to the separate QA dashboard.

---

## 3. Shipped to prod (May 30, 2026)

Confirm on telemetry from `20260529_220253`+ runs.

### 3.1 Funding sell (`ensure_funding_sell`)

**Module:** `src/core/vote_engine.py`  
**Also called from:** `src/core/guardrails.py` → `apply_chairman_guardrails()`

**Rule**

| Condition | Action |
|-----------|--------|
| ≥1 equity Buy/Strong Buy (hedge excluded) | Require funding liquidity |
| Board **>1** portfolio sell mandate (Trim/Sell/Strong Sell) | **Skip** auto sell — board already liquidating |
| Portfolio already has any Sell/Trim/Strong Sell | **Skip** — existing sell-side is enough |
| **All** portfolio equities are Buy/Strong Buy | **Skip** — no eligible sell target |
| Else | **One Sell** on lowest `aggregate_conviction_score` |

**Candidate pool:** any portfolio equity that is **not** Buy/Strong Buy and not TLT/VXX — includes Hold, Trim, Sell, Strong Sell. Never sell a name marked Buy.

**Override marker:** `[VOTE ENGINE] Funding sell` — exempt from compliance majority-alignment (`is_funding_sell_override()` in `compliance_audit.py`).

**Tests:** `tests/test_vote_engine.py` → `TestFundingSell`

### 3.2 Liquidation cap config hook

**Module:** `src/config/settings.py` → `LIQUIDATION_CAP_PCT`  
**Default:** `0.10` via env `LIQUIDATION_CAP_PCT`  
**TODO(user-profile):** replace env with persisted user profile when available.  
**Enforcement:** `src/core/guardrails.py` → `enforce_liquidation_cap()` — caps **size**, not **selection** (selection uses conviction only).

### 3.3 Briefing enrichment (three-layer Action Plan)

**Modules:** `src/output/briefing_enrichment.py`, `src/jobs/deliver.py`  
**Agents:** Flash `briefing_strategic_context` (batched); Champion/Dissent from Round 2 JSON only  
**Render:** `src/output/reporting.py` — Strategic Context + Champion + Dissent per symbol (`N/A` when unanimous)

**Shipped:** `cfe55fd`, `380427f` — sanitizer no longer wipes `strategic_context` as “generic synthesis.”

**Known follow-up (AP-1):** When Flash output is short, fallback can duplicate Champion prose — tune in enrichment or raise Flash token budget.

**Tests:** `tests/test_briefing_enrichment.py`, `tests/test_reporting_briefing.py`

### 3.4 Vote engine bypass + Python compliance (deployed / validating)

| Signal | Meaning |
|--------|---------|
| `allocation_source=vote_engine` | `build_chairman_allocation()` — no chairman Pro |
| `compliance_source=python_only` | Markopolos LLM skipped |
| `compliance_source=python+llm` | LLM path — deathmatch/funding narrative audit |

**Engine:** `src/core/engine.py` → `execute_chairman_arbitration()`, `execute_compliance_audit()`

---

## 4. Agent → output → consumer map (production)

| Agent | Runs | Lands in | Consumer | Gap |
|-------|------|----------|----------|-----|
| 5 panelists | Every debate | `raw_verdicts`, debate log | vote_engine, briefing quotes, QA | Core — keep |
| clerk | Every debate | `boardroom_brawl` only | Executive briefing | SoTU built by Python — partial redundancy |
| chairman | Non-bypass days | Action plan JSON | Briefing, QA | Skipped most days ✓ |
| compliance LLM | `allocation_source=llm` | Gate | Blocks deliver | Skipped on bypass ✓ |
| red_teamer | After pass | Bear case, unicorn rebuttals | Briefing display only | No feedback loop |
| Munger (×3) | If `heavy_tickers` | Chairman prompt only | **Discarded on bypass** | **Waste — see Ticket A1** |
| Post-flight QA ×5 | Every deliver | QA dashboard email | Human review optional | Sequential + redundant LLM |
| Standing QA ×7 + HR | 7 AM timer | Digest email only | None automated | **Orphan — see cursor handoff Ticket C2** |
| Retrospective | End of deliver | Azure `retrospective_*.md` | Manual → action_tracker | Semi-orphan |

---

## 5. Optimization tickets

### Tier 1 — **SHIPPED** (`a64bcd9`)

#### Ticket A1 — Skip Munger when chairman will bypass — **DONE**

| Field | Detail |
|-------|--------|
| **Problem** | Munger fires 3× Pro when `heavy_tickers` set, but `munger_overrides` is only injected into chairman LLM prompt — unused on `vote_engine` days |
| **File** | `src/core/engine.py` |
| **Change** | After `execute_synthesis()`, compute `summaries = self._vote_summaries()`. Run `execute_munger_audit()` only if `self.state.heavy_tickers` **and not** `can_determine_allocation(summaries)` |
| **Optional** | Pass `summaries` into `execute_chairman_arbitration()` to avoid recomputing |
| **Telemetry** | Log `munger_skipped: true` in debate checkpoint / telemetry |
| **Tests** | New `tests/test_munger_skip.py` or extend `tests/test_vote_engine.py` — mock orchestrator with `heavy_tickers` + full panel votes → zero Munger invocations in `AGENT_ACTIVITY` |
| **Est. savings** | 0–3 Pro calls (~80k+ tokens on concentration days) |

#### Ticket A2 — Skip post_mortem LLM when deterministic PASS — **DONE**

| Field | Detail |
|-------|--------|
| **Problem** | Run `20260529_152151`: post_mortem deterministic PASS but Pro LLM still ran (~25k tokens) |
| **Files** | `src/qa_pipeline.py` → `run_post_mortem_qa()`; `src/qa/post_mortem_audit.py` → `merge_post_mortem_reports()` |
| **Change** | If `audit_post_mortem_deterministic()` returns `[]`, return merged report from `merge_post_mortem_reports([], None)` with `is_compliant=True` **without** calling Gemini |
| **Tests** | Extend `tests/test_post_mortem_audit.py` — empty violations → no `call_gemini_async` (mock) |
| **Est. savings** | ~25k tokens + ~15–20s deliver time on clean runs |

#### Ticket A3 — Parallelize post-flight QA trio — **DONE**

| Field | Detail |
|-------|--------|
| **Problem** | `run_post_flight_qa()` runs post_mortem → system_architect → prompt_engineer **serially** (only architect uses `gather` with one task) |
| **File** | `src/qa_pipeline.py` → `run_post_flight_qa()` |
| **Change** | After building shared `base_prompt` / digests, `asyncio.gather(run_post_mortem_qa(...), run_system_architect(...), run_prompt_engineer_qa(...))` — extract small wrappers if needed. Preserve report order in output list for dashboard consistency |
| **Tests** | Existing QA tests must pass; optional timing mock |
| **Est. savings** | ~30–50s deliver wall-clock (no token reduction) |

#### Ticket A4 — Default qa_integrity_auditor to Flash — **DONE**

| Field | Detail |
|-------|--------|
| **File** | `src/core/agents.py` → `qa_integrity_auditor.model` → `FAST_MODEL` |
| **Note** | `run_qa_integrity_audit()` already supports Flash + 90s timeout |
| **Tests** | Spot-check `tests/test_integrity_qa_fixtures.py` |
| **Est. savings** | ~15k tokens/run (152151 used Pro) |

---

### Tier 2 — solid payoff

#### Ticket B1 — Red team → Flash — **DONE** (`748ad6c`)

| Field | Detail |
|-------|--------|
| **File** | `src/core/agents.py` → `red_teamer.model` → `FAST_MODEL` |
| **Validate** | Spot-check bear case on `20260529_220253`+ |
| **Est. savings** | ~17k Pro-tier tokens/run |

#### Ticket B2 — Skip prompt_engineer LLM on hard deterministic FAIL

| Files | `src/qa_pipeline.py`, `src/qa/persona_audit.py` |
| **Change** | If `audit_debate_persona()` returns CRITICAL-class violations, return merged persona report without LLM (mirror post_mortem pattern) |
| **Est. savings** | ~24k tokens on noisy runs |

#### Ticket B3 — Demote or cut Systems Architect QA — **PARTIAL** (`a4dfea6`)

| **Shipped** | `src/qa/architect_audit.py` — deterministic Python checks gate LLM; skip architect when clean |
| **Options remaining** | (a) Remove from post-flight entirely; (b) weekly-only via `qa_review.py` |
| **Rationale** | Often FAIL on JSON bloat; overlaps post_mortem + integrity (~23k/run) |
| **Product call** | Stan to approve full removal vs current gated behavior |

#### Ticket B4 — Deploy local bundle — **PARTIAL**

Funding sell, briefing enrichment, Phase C, liquidation cap, Tier 1, post-job sync — on `main` through `a17792b`. **May 30 deploy batch** (Legal Counsel, INT-1, briefing UX) — **staged, not committed**. See [`action_tracker.md`](action_tracker.md).

#### Ticket B5 — Legal Counsel QA — **DONE locally (staged)**

| | |
|---|---|
| **Agents** | `legal_counsel_qa` (per deliver briefing scan), `legal_counsel_code` (daily repo scan) |
| **Files** | `src/qa/legal_audit.py`, `legal_policy.py`, `legal_delivery.py`, `src/jobs/legal_code_audit.py`, `function_app.py` (8 AM timer) |
| **Delivery** | Blob `legal_counsel_briefing_{run_id}.json` + daily `legal_code_audit_YYYYMMDD.json`; email via `notifier.send_legal_counsel_report()` |
| **Policy SSOT** | `LEGAL_COUNSEL_SAAS_POLICY` in `legal_policy.py` — endorsement trap, fake quotes, fair use |
| **Validate** | First prod run after deploy — confirm Legal Counsel email + no false positives on policy text |

---

### Tier 3 — defer (backlog)

| Item | Why defer |
|------|-----------|
| Chairman narrator-only Flash | Only non-bypass days |
| Consolidate weekly 7 QA roles | Large product decision — see `agent_architecture.md` §9 |
| Reduce panelist `thinking_budget` | Quality risk — benchmark first |
| QA failures blocking email | Product decision — currently advisory by design |

---

## 6. Dormant / orphaned (production)

| Component | Issue | Handoff |
|-----------|-------|---------|
| Standing QA 7 roles | Email only | [`cursor_dev_plane_handoff.md`](cursor_dev_plane_handoff.md) Ticket C2 |
| QA scorecard → local state | Azure only | Ticket C1 in cursor handoff |
| Retrospective → action_tracker | Manual step 6 | [`post_deliver_checklist.md`](post_deliver_checklist.md) |
| Human QA review | Azure blobs; local ledger empty | Ticket C3 in cursor handoff |

---

## 7. Validation commands

```powershell
# Pull prod artifacts (canonical)
.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id 20260529_225159 --post-job

# Agent activity summary (after fetch)
.venv\Scripts\python.exe -c "import json; from pathlib import Path; d=json.loads(Path('.cache/state/api_telemetry_20260529_225159.json').read_text()); act=d['AGENT_ACTIVITY']; print('tokens', sum(v['total_tokens'] for v in act.values())); [print(k, v['invocations'], v['total_tokens']) for k,v in sorted(act.items(), key=lambda x:-x[1]['total_tokens'])]"

# Unit tests (funding sell + vote engine)
.venv\Scripts\python.exe -m unittest tests.test_vote_engine tests.test_compliance_audit tests.test_post_mortem_audit -v

# HR utilization (after fetch)
.venv\Scripts\python.exe -m src.hr_review .cache/state/api_telemetry_20260529_152151.json
```

---

## 8. Acceptance criteria (Tier 1 — verified May 30)

On a `vote_engine` day with `heavy_tickers`:

- [x] `AGENT_ACTIVITY` shows no Munger panelist keys beyond Round 1/2 (A1)
- [x] Post-mortem deterministic PASS → no `post_mortem_qa` LLM call (A2)
- [x] Post-flight QA trio runs in parallel (A3)
- [x] `qa_integrity_auditor` uses Flash in telemetry (A4)
- [x] `red_teamer` uses Flash (B1)
- [ ] Deliver token count vs `152151` baseline — re-benchmark after B2

---

## 9. Doc updates after implementing tickets

| Ticket | Update |
|--------|--------|
| A1–A4, B1, B4 | **Done** — this file + [`action_tracker.md`](action_tracker.md) May 30 EOD handoff |
| B2 | Move to Shipped when implemented; `qa_layers.md` |
| B3 full cut | `qa_layers.md` deliver stack table |
| AP-1 Action Plan polish | `briefing_charts_handoff.md` + enrichment module docstring |
