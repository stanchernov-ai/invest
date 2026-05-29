# SC Invest Boardroom — Action Tracker

**Status:** Active  
**Last Updated:** May 29, 2026 (doc hygiene trim — live backlog only)

**Purpose:** Current session pickup and prioritized backlog. Historical handoffs and Phase 0–6 specs live in [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md). Maintenance rules: [`doc_hygiene.md`](doc_hygiene.md). Doc map: [`DOCUMENTATION.md`](DOCUMENTATION.md).

---

## Session Handoff — May 29, 2026 (**pick up here**)

Briefing chart sprint is **code-complete** (`ce577bf` → `b1707c7`). **Read [`briefing_charts_handoff.md`](briefing_charts_handoff.md)** for QuickChart rules and validation runs.

| Gate | Action |
|------|--------|
| **Deploy** | `b1707c7` on `main` |
| **Validate** | `/api/deliver?run_id=20260529_152151` (or fresh pipeline) → **Graphics QA PASS** |
| **Then** | P1 debate / integrity items below |

**Pull artifacts:** `.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id 20260529_152151`

### First steps

1. Deploy + confirm Graphics QA PASS on first post-sprint deliver.
2. **P1** — Round 2 rebuttal quality (verbatim R1 in R2 on run `152151`).
3. **P1** — Post Mortem vote tally vs `raw_verdicts` (AMZN majority on `152151`).
4. After deliver: [`post_deliver_checklist.md`](post_deliver_checklist.md).

### Open items

| Pri | Effort | Item |
|-----|--------|------|
| **P1** | S | Production chart validation — Graphics QA on first post-sprint deliver |
| **P1** | M | Round 2 prompt quality — unique rebuttal text; reduce Pass spam in logs |
| **P1** | M | Post Mortem vote verification — chairman claims vs `raw_verdicts` / debate log |
| **P2** | L | Split `reporting.py` + extract prompts from `agents.py` |
| **P2** | M | Relative strength + sector weights in prepare; Buffett PE/P/S caps in Python |
| **P2** | S | Wire post-job Cursor agents (`api_audit`, `data_insights`, `supervisor_summaries`) |
| **P3** | S | Dedupe same-day `board_verdicts` rows (e.g. META on `20260529`) |

**Vote engine / compliance (done):** `6107539`, run `20260529_144833` — see [`technical_solution.md`](technical_solution.md) §2.2 and archive log.

---

## Recently shipped (last 7 days)

| Area | Commit(s) | Run / note |
|------|-----------|------------|
| Briefing charts | `ce577bf`–`b1707c7` | Palettes, pie legends, SoTU order, dark line/bar — `152151` |
| Vote engine Phase A | `6107539` | `vote_engine`, compliance, verdict memory — `144833` |
| Human QA review UI | `e39b337` | `/api/qa-review` on Flex hostname |
| FMP dead URLs | `63730fe` | `grades-consensus`, `earnings`, EOD cache |

---

## Deferred (intentional — revisit when mature)

- **Single bad ticker abort** — fail-fast during active dev; graceful degradation later.
- **Mega-prompt summarization** — only if token cost forces it.
- **QuickChart → local charts** — acceptable external dependency for now.

---

## References (do not duplicate here)

| Topic | Doc |
|-------|-----|
| Charts / QuickChart | [`briefing_charts_handoff.md`](briefing_charts_handoff.md) |
| FMP endpoints | [`fmp_data_dictionary.md`](fmp_data_dictionary.md) |
| QA modules | [`qa_layers.md`](qa_layers.md) |
| Pipeline timers | [`technical_solution.md`](technical_solution.md) §1.4 |
| Azure QA review URL | [`agent_architecture.md`](agent_architecture.md) §6, [`engineering_playbook.md`](engineering_playbook.md) §2 |
| May 2026 history | [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md) |
