# SC Invest Boardroom — Action Tracker

**Status:** Active  
**Last Updated:** May 30, 2026 (agent optimization handoffs — implementation deferred)

**Purpose:** Current session pickup and prioritized backlog. Historical handoffs and Phase 0–6 specs live in [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md). Maintenance rules: [`doc_hygiene.md`](doc_hygiene.md). Doc map: [`DOCUMENTATION.md`](DOCUMENTATION.md).

**Product principles (enforce in every PR):** [`product_principles.md`](product_principles.md)

---

## Session Handoff — May 30, 2026 (**pick up here**)

**Theme:** Post-job agents automated; Tier 1 runtime optimizations shipped locally.

| Shipped (local / pending deploy) | Note |
|----------------------------------|------|
| **Post-job sync** | `fetch --post-job` / `wait_for_run --post-job` → api_audit, data_insights, supervisor_summaries |
| **Tier 1 A1–A4** | Munger skip, post_mortem LLM skip, parallel QA trio, integrity Flash |
| **C1/C3/C4** | sync_ecosystem, human review → retrospective refresh, post_job_sync.py |
| **C2** | qa_digest blob persisted from standing QA |

| Deliverable | Doc |
|-------------|-----|
| Production audit, telemetry baseline, funding sell spec, tickets A1–B4 | [`agent_optimization_handoff.md`](agent_optimization_handoff.md) |
| Cursor agents, ecosystem_state sync, standing QA digest, tickets C1–C5 | [`cursor_dev_plane_handoff.md`](cursor_dev_plane_handoff.md) |

| Shipped (local / pending deploy) | Note |
|----------------------------------|------|
| Funding sell | `ensure_funding_sell()` — see handoff §3.1 |
| Briefing enrichment | Round 2 quotes at render — handoff §3.3 |
| Liquidation cap env | `LIQUIDATION_CAP_PCT` — handoff §3.2 |
| Phase B/C vote engine | Commits `285d70a` + local; validate on `152151` |

| Gate | Action |
|------|--------|
| **Commit + deploy** | Tier 1 + post-job automation bundle |
| **Validate** | After prod run: `fetch --run-id X --post-job` then `ecosystem_state.py show --last 3` |
| **Baseline** | Compare telemetry vs `20260529_152151` — expect fewer deliver tokens |

**Pull artifacts:** `.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id 20260529_152151`

### Open items (from handoff docs — not started)

| Pri | ID | Effort | Item | Doc |
|-----|-----|--------|------|-----|
| **P1** | A1 | S | ~~Skip Munger when `can_determine_allocation()`~~ **DONE** (local) | optimization §5 |
| **P1** | A2 | S | ~~Skip post_mortem LLM on deterministic PASS~~ **DONE** (local) | optimization §5 |
| **P1** | A3 | S | ~~Parallelize post-flight QA trio~~ **DONE** (local) | optimization §5 |
| **P1** | A4 | S | ~~qa_integrity_auditor → Flash default~~ **DONE** (local) | optimization §5 |
| **P1** | B4 | S | Commit + prod validate local bundle | optimization §5 |
| **P2** | C1 | M | ~~`fetch_azure_reports --sync-ecosystem`~~ **DONE** (local) | cursor §4 |
| **P2** | C2 | M | ~~Persist standing QA digest blob~~ **DONE** (local) | cursor §4 |
| **P2** | C3 | M | ~~Human review → retrospective refresh~~ **DONE** (local) | cursor §4 |
| **P2** | C4 | M | ~~`post_job_sync.py` deterministic audit~~ **DONE** (local) | cursor §4 |
| **P2** | C5 | — | ~~Supervisor automate vs checklist-only~~ **DONE** — Option A (C1+C4) | cursor §4 |
| **P2** | B3 | — | Systems Architect QA demote/cut (product call) | optimization §5 |

### First steps (when resuming implementation)

1. Commit + deploy local bundle; re-validate `152151`.
2. Implement A1–A4 per [`agent_optimization_handoff.md`](agent_optimization_handoff.md) §5–§8.
3. Optionally wire C1 fetch sync before standing QA digest work.

---

## Session Handoff — May 29, 2026 (superseded)

**Theme:** Product-grade pipeline — board votes in Python, fail closed, no LLM gate repair.

| Shipped (local / pending push) | Note |
|--------------------------------|------|
| `285d70a` | Phase B — `vote_engine` allocation on 3/5 majority days |
| Uncommitted | No LLM debate retry; Python-only compliance on `vote_engine` days; `debate_review_*` blobs; [`product_principles.md`](product_principles.md) |

| Gate | Action |
|------|--------|
| **Commit + deploy** | Cleanup bundle (principles + no-retry + python-only compliance) |
| **Validate** | `/api/debate?run_id=20260529_152151` → expect `allocation_source=vote_engine`, debate success |
| **Then** | Run Review UI (P2); chairman narrator-only (P2) |

**Pull artifacts:** `.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id 20260529_152151`

### First steps

1. Commit + push cleanup; confirm deploy.
2. Re-run debate on `152151` — should bypass chairman Pro + skip Markopolos if Python passes.
3. If fail: inspect `debate_review_{run_id}.json` (expert queue — no retry).

### Open items (principles-driven)

| Pri | Effort | Item | Principle |
|-----|--------|------|-----------|
| **P1** | M | ~~Phase C binary mandate votes~~ **DONE** (local) — Strong Buy/Sell schema, buy_side/sell_side counts |
| **P1** | S | Commit + prod validate Phase B/C on `152151` | §1, §3 |
| **P1** | S | ~~Skip Markopolos when `allocation_source=vote_engine`~~ **DONE** (local) | §3 |
| **P1** | M | Round 2 rebuttal quality — verbatim R1 in R2 | §5 |
| **P1** | M | Post Mortem vote verification vs `raw_verdicts` | §5 |
| **P2** | M | **Run Review UI** — one page per run_id (votes → allocation → gate) | §6 |
| **P2** | M | Chairman **narrator-only** Flash pass (no verdict fields) | §4 |
| **P2** | S | Expert-review weekly digest from `debate_review_*` blobs | §5 |
| **P2** | L | Split `reporting.py` + extract prompts from `agents.py` | — |
| **P3** | — | **Freeze agent roster** until prod pass rate stable | §7 |

### Documentation

| Pri | ID | Effort | Item |
|-----|-----|--------|------|
| ~~**P1**~~ | — | — | ~~Product principles SSOT~~ **DONE** — `product_principles.md` |
| **P2** | DOC-1 | M | Sync `technical_solution.md` to three-phase Azure + principles |
| **P2** | DOC-5 | S | **Recurring (monthly):** tracker trim when > ~200 lines |

**Vote engine:** Phase A `6107539`; Phase B `285d70a` — see [`technical_solution.md`](technical_solution.md) §2.2.

---

## SaaS / multi-tenant roadmap (**blocked — stabilize first**)

**Do not start SaaS implementation until the current single-tenant pipeline is stabilized and simplified.** Building multi-tenant layers on an unstable base compounds rework.

| Pri | ID | Effort | Item | Gate |
|-----|-----|--------|------|------|
| — | SAAS-0 | — | **Design SSOT** — [`saas_technical_solution.md`](saas_technical_solution.md) | **DONE** (May 29) |
| **P2** | SAAS-1 | L | **SaaS foundation** — `PortfolioSource`, Postgres entities, `market_sync`, per-user tenancy (phases 1–4 in doc) | **Blocked on:** P1 commit/deploy + prod validate; core flow simplification (current session handoff complete) |

Phases and data model: [`saas_technical_solution.md`](saas_technical_solution.md) §4–10. Not deferred long-term — **queued immediately after stabilization**, not in parallel with it.

---

## Recently shipped (last 7 days)

| Area | Commit(s) | Run / note |
|------|-----------|------------|
| **Handoff docs** | (local) | [`agent_optimization_handoff.md`](agent_optimization_handoff.md), [`cursor_dev_plane_handoff.md`](cursor_dev_plane_handoff.md) |
| Funding sell (local) | uncommitted | `ensure_funding_sell()` — handoff §3.1 |
| Vote engine Phase B | `285d70a` | Deterministic 3/5 allocation, max-3, alpha from executed buys |
| P1 rebuttal + post-mortem | `ba8df67` | Round 2 prompts, 3/5 buy mandate |
| Doc hygiene | `6825f56` | Lean tracker, `doc_hygiene.md` |
| Briefing charts | `ce577bf`–`b1707c7` | Graphics QA PASS on `152151` deliver |
| Vote engine Phase A | `6107539` | `144833` validation |

---

## Deferred (intentional — revisit when mature)

- **Single bad ticker abort** — fail-fast during active dev; graceful degradation later.
- **Mega-prompt summarization** — only if token cost forces it.
- **QuickChart → local charts** — acceptable external dependency for now.

---

## References (do not duplicate here)

| Topic | Doc |
|-------|-----|
| **Product principles** | [`product_principles.md`](product_principles.md) |
| **Agent audit + runtime optimizations** | [`agent_optimization_handoff.md`](agent_optimization_handoff.md) |
| **Cursor dev plane + ecosystem_state** | [`cursor_dev_plane_handoff.md`](cursor_dev_plane_handoff.md) |
| Charts / QuickChart | [`briefing_charts_handoff.md`](briefing_charts_handoff.md) |
| QA modules | [`qa_layers.md`](qa_layers.md) |
| Pipeline timers | [`technical_solution.md`](technical_solution.md) §1.4 |
| SaaS / multi-tenant target architecture | [`saas_technical_solution.md`](saas_technical_solution.md) |
| May 2026 history | [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md) |
