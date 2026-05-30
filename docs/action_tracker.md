# SC Invest Boardroom — Action Tracker

**Status:** Active  
**Last Updated:** May 29, 2026 (product principles + pipeline cleanup)

**Purpose:** Current session pickup and prioritized backlog. Historical handoffs and Phase 0–6 specs live in [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md). Maintenance rules: [`doc_hygiene.md`](doc_hygiene.md). Doc map: [`DOCUMENTATION.md`](DOCUMENTATION.md).

**Product principles (enforce in every PR):** [`product_principles.md`](product_principles.md)

---

## Session Handoff — May 29, 2026 (**pick up here**)

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
| **P1** | S | Commit + prod validate Phase B + cleanup | §1, §3 |
| **P1** | S | ~~No LLM debate retry on compliance fail~~ **DONE** (local) | §2 |
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

## Recently shipped (last 7 days)

| Area | Commit(s) | Run / note |
|------|-----------|------------|
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
| Charts / QuickChart | [`briefing_charts_handoff.md`](briefing_charts_handoff.md) |
| QA modules | [`qa_layers.md`](qa_layers.md) |
| Pipeline timers | [`technical_solution.md`](technical_solution.md) §1.4 |
| May 2026 history | [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md) |
