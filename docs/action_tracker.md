# SC Invest Boardroom — Action Tracker

**Status:** Active  
**Last Updated:** May 30, 2026 (EOD — briefing sprint + prod validation)

**Purpose:** Current session pickup and prioritized backlog. Historical handoffs and Phase 0–6 specs live in [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md). Maintenance rules: [`doc_hygiene.md`](doc_hygiene.md). Doc map: [`DOCUMENTATION.md`](DOCUMENTATION.md).

**Product principles (enforce in every PR):** [`product_principles.md`](product_principles.md)

---

## Session Handoff — May 30, 2026 EOD (**pick up here**)

**Theme:** Briefing quality sprint **deployed and validated on prod** — debate completeness, three-layer Action Plan, layout cleanup, Tier 1/B1 optimizations, post-job automation.

| Canonical run | Pipeline | Use for |
|---------------|----------|---------|
| **`20260529_225159`** | **SUCCESS** | **Action Plan** — 8/8 blocks with Strategic Context + Champion + Dissent; no placeholder synthesis |
| `20260529_201848` | SUCCESS | Debate fix — 3 complete paragraphs, brawl validation |
| `20260529_220253` | SUCCESS | Post B1 (`red_teamer` → Flash) |
| `20260529_214609` | Supervisor BLOCKED | Pre-layout baseline; Integrity TSM false positive (R1 vs R2 digest) |

**Kickoff:** `GET /api/prepare?code=<function-key>` — hostname in [`engineering_playbook.md`](engineering_playbook.md).

### Shipped to prod (`main`)

| Area | Commit(s) | Note |
|------|-----------|------|
| Persona audit + section order | `e044bde` | Pies before SoTU; SoTU before Action Plan |
| Post-mortem vote verification | `bf17114` | Ground truth vs `raw_verdicts` + debate prose |
| Truncated Debate fix | `4b8ee56` | Slim clerk digest, retry/fallback, completeness gate |
| **B1** red_teamer → Flash | `748ad6c` | ~17k Pro tokens saved/run |
| Briefing layout | `04af83d` | Removed Symbol/Action summary table + TWR **table** (charts/mandate still use returns) |
| Three-layer Action Plan | `cfe55fd`, `380427f` | Flash `briefing_strategic_context` + R2 Champion/Dissent; sanitizer fix |
| Tier 1 QA + funding sell | `a64bcd9` | Munger skip, post_mortem LLM skip, parallel QA trio, integrity Flash |
| Post-job blobs | `e889940` | `fetch --post-job` / `wait_for_run --post-job` |
| Architect QA gate | `a4dfea6` | Deterministic Python checks before Systems Architect LLM |
| Deliver perf | `c8ac45d`, `7acc97a`, `ff91ffe` | Parallel chart I/O, single HTML render, reuse probe bytes for Graphics QA |

**Deep dives:** [`briefing_charts_handoff.md`](briefing_charts_handoff.md) (layout/charts), [`agent_optimization_handoff.md`](agent_optimization_handoff.md) (telemetry/tickets).

### Validate after deploy

```powershell
.venv\Scripts\python.exe scripts/wait_for_run.py --run-id YYYYMMDD_HHMMSS --timeout 2700 --post-job
.venv\Scripts\python.exe tools/fetch_azure_reports.py --run-id YYYYMMDD_HHMMSS --post-job
.venv\Scripts\python.exe -m pytest tests/test_briefing_enrichment.py tests/test_reporting_briefing.py -v
```

Deliver-only re-render: `GET /api/deliver?run_id=<run_id>&code=<function-key>`.

### Open items (prioritized)

| Pri | ID | Effort | Item | Notes |
|-----|-----|--------|------|-------|
| **P1** | AP-1 | S | Flash Strategic Context quality | On `225159`, some blocks duplicate Champion when Flash output is short; tune token budget, fallback dedupe, or per-symbol retry |
| **P1** | INT-1 | M | Integrity auditor R2-only ground truth | TSM lesson (`214609`): compare digest to Round 2 JSON, not R1 panelist |
| **P1** | GFX-1 | M | Bar chart Y-axis / legend | Recurring Graphics CRITICAL — see [`briefing_charts_handoff.md`](briefing_charts_handoff.md) |
| **P2** | B2 | S | Skip `prompt_engineer` LLM on deterministic FAIL | ~24k tokens; mirror post_mortem pattern — [`agent_optimization_handoff.md`](agent_optimization_handoff.md) §B2 |
| **P2** | B3 | — | Systems Architect QA demote/cut | Partially gated (`a4dfea6`); Stan product call on full removal vs weekly-only |
| **P2** | R2-1 | M | Round 2 rebuttal quality — verbatim R1 copy | Prompt Engineer CRITICAL on several runs |
| **P2** | — | M | **Run Review UI** — one page per run_id | Votes → allocation → gate |
| **P2** | DOC-1 | M | Sync `technical_solution.md` to current pipeline + principles | |
| **P3** | — | — | **Freeze agent roster** until QA pass rate stable | [`product_principles.md`](product_principles.md) §7 |

**QA note:** Supervisor often **BLOCKED** on Graphics/Integrity CRITICALs — advisory; does not block investor email.

### First steps (successor)

1. Spot-check `20260529_225159` briefing HTML — Action Plan Strategic Context vs Champion overlap (AP-1).
2. If shipping INT-1: extend integrity fixtures with R1/R2 mismatch case (TSM).
3. Pick **B2** or **GFX-1** based on whether next sprint is token cost vs visual polish.

---

## SaaS / multi-tenant roadmap (**blocked — stabilize first**)

**Do not start SaaS implementation until the current single-tenant pipeline is stabilized and simplified.**

| Pri | ID | Effort | Item | Gate |
|-----|-----|--------|------|------|
| — | SAAS-0 | — | Design SSOT — [`saas_technical_solution.md`](saas_technical_solution.md) | **DONE** (May 29) |
| **P2** | SAAS-1 | L | SaaS foundation (phases 1–4 in doc) | **Blocked on:** stable QA pass rate + core flow simplification |

---

## Recently shipped (last 7 days)

| Area | Commit(s) | Run / note |
|------|-----------|------------|
| Three-layer Action Plan | `cfe55fd`, `380427f` | Canonical `225159` |
| Briefing layout | `04af83d`, `e044bde` | No TWR table; SoTU before Action Plan |
| Debate + post-mortem | `4b8ee56`, `bf17114` | `201848` debate; vote verification hardened |
| B1 + Tier 1 | `748ad6c`, `a64bcd9` | Flash red_teamer; Munger/QA skips |
| Deliver perf + architect gate | `a4dfea6`–`ff91ffe` | Parallel charts; deterministic architect pre-check |
| Post-job automation | `e889940` | ecosystem_state sync after fetch/wait |
| Briefing charts sprint | `ce577bf`–`b1707c7` | Dark palette, pie legend fix — [`briefing_charts_handoff.md`](briefing_charts_handoff.md) |
| Vote engine Phase B | `285d70a` | Deterministic 3/5 allocation |

*Superseded Session Handoffs (May 30 AM, May 29):* [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md#may-30-2026-session-handoffs-archived).

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
| Charts / QuickChart / section order | [`briefing_charts_handoff.md`](briefing_charts_handoff.md) |
| QA modules | [`qa_layers.md`](qa_layers.md) |
| Pipeline timers | [`technical_solution.md`](technical_solution.md) §1.4 |
| SaaS / multi-tenant target architecture | [`saas_technical_solution.md`](saas_technical_solution.md) |
| May 2026 history | [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md) |
