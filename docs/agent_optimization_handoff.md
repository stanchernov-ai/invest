# Agent Optimization Handoff — Production Pipeline

**Status:** Active handoff for developers  
**Last updated:** May 30, 2026  
**Owner:** Stan  
**SSOT for:** May 2026 agent audit, telemetry baseline, allocation/funding rules (shipped local), and **planned** runtime optimizations (not yet implemented).

**Related**

| Doc | Purpose |
|-----|---------|
| [`agent_architecture.md`](agent_architecture.md) | Roster, diagrams, QA stack |
| [`qa_layers.md`](qa_layers.md) | Which QA module runs when |
| [`cursor_dev_plane_handoff.md`](cursor_dev_plane_handoff.md) | Cursor agents, ecosystem_state, post-job sync |
| [`product_principles.md`](product_principles.md) | Board in Python, fail closed |
| [`post_deliver_checklist.md`](post_deliver_checklist.md) | After each deliver |

**Evidence run (prod):** `20260529_152151` — pull via  
`.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id 20260529_152151`

**Baseline comparison run:** `20260529_144833` (pre-full bypass; debate ~287s vs ~124s on 152151).

---

## 1. Executive summary

The **debate bottleneck is largely resolved** on `vote_engine` days: chairman Pro and Markopolos LLM are skipped; debate dropped from ~287s to ~124s on comparable runs.

The **new bottleneck is deliver QA**: ~53% of LLM tokens on a typical bypass day (~151k of ~286k total). Post-flight agents run **mostly sequentially** and several **run LLM passes even when deterministic Python already PASS**.

**Do not implement the Tier 1–3 tickets in this doc unless explicitly assigned** — this file is the developer handoff spec.

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
| red_teamer | 1 | 17,455 | 1,692 | Pro |

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

## 3. Shipped locally (document before deploy)

These are in the working tree; confirm prod deploy status before treating as live.

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

### 3.3 Briefing enrichment (render-time)

**Module:** `src/output/briefing_enrichment.py`  
**Wired in:** `src/output/reporting.py` → `enrich_chairman_for_briefing()`  
**Purpose:** Replace generic chairman synthesis strings with Round 2 panel quotes per symbol at HTML render time.  
**Tests:** `tests/test_briefing_enrichment.py`

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

## 5. Planned optimizations (implementation tickets)

Implement in order unless blocked. Each ticket is independent unless noted.

### Tier 1 — highest impact ÷ effort

#### Ticket A1 — Skip Munger when chairman will bypass

| Field | Detail |
|-------|--------|
| **Problem** | Munger fires 3× Pro when `heavy_tickers` set, but `munger_overrides` is only injected into chairman LLM prompt — unused on `vote_engine` days |
| **File** | `src/core/engine.py` |
| **Change** | After `execute_synthesis()`, compute `summaries = self._vote_summaries()`. Run `execute_munger_audit()` only if `self.state.heavy_tickers` **and not** `can_determine_allocation(summaries)` |
| **Optional** | Pass `summaries` into `execute_chairman_arbitration()` to avoid recomputing |
| **Telemetry** | Log `munger_skipped: true` in debate checkpoint / telemetry |
| **Tests** | New `tests/test_munger_skip.py` or extend `tests/test_vote_engine.py` — mock orchestrator with `heavy_tickers` + full panel votes → zero Munger invocations in `AGENT_ACTIVITY` |
| **Est. savings** | 0–3 Pro calls (~80k+ tokens on concentration days) |

#### Ticket A2 — Skip post_mortem LLM when deterministic PASS

| Field | Detail |
|-------|--------|
| **Problem** | Run `20260529_152151`: post_mortem deterministic PASS but Pro LLM still ran (~25k tokens) |
| **Files** | `src/qa_pipeline.py` → `run_post_mortem_qa()`; `src/qa/post_mortem_audit.py` → `merge_post_mortem_reports()` |
| **Change** | If `audit_post_mortem_deterministic()` returns `[]`, return merged report from `merge_post_mortem_reports([], None)` with `is_compliant=True` **without** calling Gemini |
| **Tests** | Extend `tests/test_post_mortem_audit.py` — empty violations → no `call_gemini_async` (mock) |
| **Est. savings** | ~25k tokens + ~15–20s deliver time on clean runs |

#### Ticket A3 — Parallelize post-flight QA trio

| Field | Detail |
|-------|--------|
| **Problem** | `run_post_flight_qa()` runs post_mortem → system_architect → prompt_engineer **serially** (only architect uses `gather` with one task) |
| **File** | `src/qa_pipeline.py` → `run_post_flight_qa()` |
| **Change** | After building shared `base_prompt` / digests, `asyncio.gather(run_post_mortem_qa(...), run_system_architect(...), run_prompt_engineer_qa(...))` — extract small wrappers if needed. Preserve report order in output list for dashboard consistency |
| **Tests** | Existing QA tests must pass; optional timing mock |
| **Est. savings** | ~30–50s deliver wall-clock (no token reduction) |

#### Ticket A4 — Default qa_integrity_auditor to Flash

| Field | Detail |
|-------|--------|
| **File** | `src/core/agents.py` → `qa_integrity_auditor.model` → `FAST_MODEL` |
| **Note** | `run_qa_integrity_audit()` already supports Flash + 90s timeout |
| **Tests** | Spot-check `tests/test_integrity_qa_fixtures.py` |
| **Est. savings** | ~15k tokens/run (152151 used Pro) |

---

### Tier 2 — solid payoff

#### Ticket B1 — Red team → Flash

| Field | Detail |
|-------|--------|
| **File** | `src/core/agents.py` → `red_teamer.model` → `FAST_MODEL` |
| **Risk** | Bear case quality — spot-check 2–3 runs before/after |
| **Est. savings** | ~17k Pro-tier tokens/run |

#### Ticket B2 — Skip prompt_engineer LLM on hard deterministic FAIL

| Files | `src/qa_pipeline.py`, `src/qa/persona_audit.py` |
| **Change** | If `audit_debate_persona()` returns CRITICAL-class violations, return merged persona report without LLM (mirror post_mortem pattern) |
| **Est. savings** | ~24k tokens on noisy runs |

#### Ticket B3 — Demote or cut Systems Architect QA

| **Options** | (a) Remove from `run_post_flight_qa` parallel list; (b) deterministic-only JSON size check; (c) run weekly only via `qa_review.py` |
| **Rationale** | Often FAIL on JSON bloat; overlaps post_mortem + integrity (~23k/run) |
| **Product call** | Stan to approve removal vs demotion |

#### Ticket B4 — Deploy local bundle

Commit + deploy: funding sell, briefing enrichment, Phase C, liquidation cap settings, any open compliance/funding tests. Validate on `20260529_152151` or fresh run.

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
# Pull prod artifacts
.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id 20260529_152151

# Agent activity summary (after fetch)
.venv\Scripts\python.exe -c "import json; from pathlib import Path; d=json.loads(Path('.cache/state/api_telemetry_20260529_152151.json').read_text()); act=d['AGENT_ACTIVITY']; print('tokens', sum(v['total_tokens'] for v in act.values())); [print(k, v['invocations'], v['total_tokens']) for k,v in sorted(act.items(), key=lambda x:-x[1]['total_tokens'])]"

# Unit tests (funding sell + vote engine)
.venv\Scripts\python.exe -m unittest tests.test_vote_engine tests.test_compliance_audit tests.test_post_mortem_audit -v

# HR utilization (after fetch)
.venv\Scripts\python.exe -m src.hr_review .cache/state/api_telemetry_20260529_152151.json
```

---

## 8. Acceptance criteria (post Tier 1)

On a `vote_engine` day with `heavy_tickers`:

- [ ] `AGENT_ACTIVITY` shows no Munger panelist keys beyond Round 1/2 (no third invocation pass)
- [ ] Post-mortem deterministic PASS → no `post_mortem_qa` LLM call (verify invocations=0 or skipped in logs)
- [ ] Deliver phase wall-clock drops vs 152151 baseline (same symbol count)
- [ ] `qa_integrity_auditor` uses Flash in telemetry
- [ ] All existing `tests/test_vote_engine.py`, `tests/test_integrity_qa_fixtures.py`, `tests/test_post_mortem_audit.py` pass

---

## 9. Doc updates after implementing tickets

| Ticket | Update |
|--------|--------|
| A1–A4 | This file → move tickets to "Shipped"; `agent_architecture.md` §10 changelog |
| Funding sell deploy | `technical_solution.md` §2.2 vote_engine / guardrails |
| B3 architect cut | `qa_layers.md` deliver stack table |
