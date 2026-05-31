# SC Invest Boardroom — Action Tracker

**Status:** Active  
**Last Updated:** May 31, 2026 (prod `b6984fa`; validated run **`20260531_014121`** — Crucible palette, QA triage, backlog sync)

**Purpose:** Current session pickup and prioritized backlog (**single file** for QA findings + engineering work). Every QA CRITICAL/WARNING is logged to **Open items** via `tools/sync_backlog.py`. Historical handoffs and Phase 0–6 specs live in [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md). Maintenance rules: [`doc_hygiene.md`](doc_hygiene.md). Doc map: [`DOCUMENTATION.md`](DOCUMENTATION.md).

**Product principles (enforce in every PR):** [`product_principles.md`](product_principles.md)

---

## Session Handoff — May 31, 2026 Crucible + QA backlog (**pick up here**)

**Theme:** **May 31 deploy batch on prod.** First validated run with cold-iron Crucible styling, QA dashboard backlog triage, and unified `action_tracker` sync.

| State | Detail |
|-------|--------|
| **Prod HEAD** | **`b6984fa`** — unified backlog sync · **`760ebb6`** Crucible palette · **`52613b2`** QA triage UI · **`6de1d69`** Today's Actions layout |
| **Last validated run** | **`20260531_014121`** (~4.5 min, pipeline SUCCESS, all emails ok) |
| **Local git** | `main` synced with `origin/main`; minor uncommitted fix in `fetch_azure_reports.py` (Path for sync_backlog) |
| **Deploy** | GitHub Actions [run #92](https://github.com/stanchernov-ai/invest/actions/runs/26707882120) — success |

**Kickoff (manual run):** `GET /api/prepare?code=<function-key>` — hostname: `app-boardroom-prod-b5h4epg2d0cxefa0.eastus-01.azurewebsites.net`. Function key: `az functionapp keys list -g rg-boardroom-prod -n app-boardroom-prod --query functionKeys.default -o tsv`. **Note:** `/api/prepare` is **synchronous** — waits for prepare phase (~8–60s) before returning 202; do not interrupt.

```powershell
$key = az functionapp keys list -g rg-boardroom-prod -n app-boardroom-prod --query functionKeys.default -o tsv
Invoke-WebRequest "https://app-boardroom-prod-b5h4epg2d0cxefa0.eastus-01.azurewebsites.net/api/prepare?code=$key" -UseBasicParsing
.venv\Scripts\python.exe scripts\wait_for_run.py --run-id YYYYMMDD_HHMMSS --timeout 2700 --post-job
```

### Shipped May 31 (`52613b2` → `b6984fa`)

| Area | Key paths | What |
|------|-----------|------|
| **The Crucible** | `briefing_style.py`, `reporting.py`, `board_roster.py`, `agents.py` | Void charcoal `#09090b`, steel border, icy text, silver header; avatar + rebuttal layout (Alpha Pick + Unicorn) |
| **QA triage** | `candidate_triage.py`, `human_review.py`, `deliver.py` | Backlog items at bottom of QA dashboard; fix code / fix agent / discard via `/api/qa-review#candidates` |
| **Backlog sync** | `backlog_sync.py`, `tools/sync_backlog.py`, `fetch_azure_reports.py --post-job` | Auto-log QA CRITICAL/WARNING into Open items (deduped) |
| **Today's Actions** | `reporting.py` (`c4189f1`, `6de1d69`) | Scannable summary after Unicorn; champion/dissent columns; 3× chart DPR |

### Run `20260531_014121` — post-deploy QA notes

| Phase | Duration | Status |
|-------|----------|--------|
| Prepare | 9s | success |
| Debate | 108s | success |
| Deliver | 128s | success |

**Email:** briefing + QA dashboard + Legal Counsel — all sent.

**Validated on prod briefing (artifact check):**
- **The Crucible** — `#09090b` vault, `#a8b0ba` border, `#e4e4e7` body, `#c0c8d0` header + avatar (Alpha Pick + Unicorn)
- **Today's Actions** section present
- **Legal Counsel** — 0 CRITICAL; INFO disclaimer note only
- **Charts** — 4/4 deterministic health OK

**QA FAIL (see Open items — synced; fixes in local WIP, see [`debate_qa_architect_handoff.md`](debate_qa_architect_handoff.md)):**
- **Systems Architect** — watchlist Pass spam persists (192 mentions / 27 symbols) → overlaps PASS-SPAM-1
- **Prompt Engineer** — 3× persona drift CRITICAL (forbidden vocab in Round 2 rebuttals) → **PE-PERSONA-1** (fix **agent**)
- **Graphics Designer** — LLM visual review parse error (WARNING); deterministic chart audit PASS

**Post-job:** 5 QA CRITICAL · ~295k tokens · `QA_EXECUTION` + `QA_SCORECARD` on prod telemetry.

**Human QA still open (Gmail):** Crucible look/feel, Today's Actions scan, QA dashboard backlog table + triage link, Unicorn Crucible rebuttal.

**Artifacts cached:** `.cache/reports/executive_briefing_20260531_014121.html`, `qa_dashboard_20260531_014121.html`, `state/qa_reports_20260531_014121.json`

```powershell
.venv\Scripts\python.exe tools/fetch_azure_reports.py --run-id 20260531_014121 --post-job
.venv\Scripts\python.exe tools/sync_backlog.py --run-id YYYYMMDD_HHMMSS   # if triage submitted after fetch
```

### Open items (prioritized)

*Every QA CRITICAL/WARNING is logged here. Run `tools/sync_backlog.py --run-id YYYYMMDD_HHMMSS` after fetch. **Fix:** `code` = real bug · `agent` = QA/prompt · `discard` = false positive.*

| Pri | ID | Status | Source | Fix | Item | Evidence |
|-----|-----|--------|--------|-----|------|----------|
| **P0** | QA-HUMAN-1 | open | manual | code | Gmail review of `20260531_014121` — Crucible palette, Today's Actions, QA backlog triage, debate | |
| **P1** | PASS-SPAM-1 | done | Systems Architect | code | Reduce watchlist Pass spam in debate log (86/100 Pass rows; 192 mentions / 27 symbols) | qa_reports_20260531_014121.json |
| **P1** | PE-PERSONA-1 | done | Prompt Engineer | agent | Round 2 persona drift — forbidden vocab (`margin of safety`, `relative strength`, `the tape`) across panelists | qa_reports_20260531_014121.json |
| **P1** | R2-1 | done | Prompt Engineer | agent | Round 2 `overall_portfolio_critique` verbatim copy of Round 1 | qa_reports_20260530_205821.json |
| **P1** | HR-TELEM-1 | open | HR | code | HR Efficiency review on prod telemetry — `hr_review` on `20260531_014121` (`QA_EXECUTION` now on prod) | api_telemetry_20260531_014121.json |
| **P1** | GFX-2 | done | Graphics Designer | code | Logo contrast on `#27272a` — MSFT Alpha Pick | qa_reports_20260530_205821.json |
| **P1** | GFX-SOTU-1 | done | Graphics Designer | code | SoTU non-SSOT `box-shadow` / colors | qa_reports_20260530_205821.json |
| **P1** | AV-2 | closed | manual | code | SoTU avatar ring alignment — **duplicate of GFX-5 (`d8b7385`); reverted `4d0bbaa` re-recenter** |  |
| **P1** | GFX-3 | done | manual | code | Pie categorical palette — too many similar greens |  |
| **P1** | CHAIR-1 | open | Post Mortem QA | code | Post Mortem Trim→Hold mandate — AVGO/ASML on `010432` |  |
| **P1** | HR-1 | open | manual | code | Commit + deploy remaining HR/QA roster WIP | [`hr_qa_roster_handoff.md`](hr_qa_roster_handoff.md) |
| **P2** | GFX-LLM-1 | open | Graphics Designer | agent | Visual review LLM parse error (deterministic chart audit still PASS) | qa_reports_20260531_014121.json |
| **P2** | PE-SYCO-1 | open | Prompt Engineer | agent | Unanimous verdict buckets on most tickers (sycophancy collapse) | persona_audit threshold 60% |
| **P2** | LEG-BRIEF-1 | open | Legal Counsel | code | Briefing Jinja wraps `champion_quote` in quotes — safe for panelist only |  |
| **P2** | HR-ROSTER-1 | open | HR | agent | Reduce deliver QA overlap / token sink | [`agent_architecture.md`](agent_architecture.md) §9 |
| **P3** | LEG-MUNGER-1 | open | Legal Counsel | code | Rename `MUNGER_DOCTRINE` user-facing string for SaaS | debate injection only |

**Done (now prod):** GFX-2, GFX-SOTU-1, GFX-3, GFX-5 (avatar rings), PASS-SPAM-1, R2-1, PE-PERSONA-1, DEPLOY-1, REVIEW-1, AP-1, **AP-2**, GFX-4, GFX-QA, INT-1, UNICORN-1, Legal Counsel QA, catalysts, per-stock debate, QA review footer, investor voice, Yahoo cache, scout validation, **PE-VOICE-1**, **Crucible palette** (`760ebb6`), **QA triage UI** (`52613b2`), **backlog sync** (`b6984fa`), `qa_augmentation.py` (B2).

**Dropped / merged:** H1 → HR-TELEM-1; MKT-QA-1 lives in GTM section only; auto-sync rows that duplicate PASS-SPAM-1 / PE-PERSONA-1 / GFX-LLM-1 — discard via triage.

---

## Session Handoff — May 30 deploy batch prep (archived)

**Theme:** Prior agent staged 33 files but commit hung on pre-commit. **Successor completed:** `83ecdca` + `9f26173` pushed; prod run `20260530_205821`. Original commit recipe and staged-batch table preserved in git history for this file (~May 30 AM).

---

## Session Handoff — May 30, 2026 late night (archived)

**Theme:** Hypatia roster + Stealth Wealth inline email — **superseded by deploy batch above.**

| Canonical run | Note |
|---------------|------|
| `20260530_010432` | Stealth Wealth Gmail validation; Graphics/Post Mortem advisory FAILs |

*Detail:* [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md#may-30-2026--late-night-handoff-archived).

---

## Session Handoff — May 30, 2026 EOD (archived)

**Theme:** Briefing quality sprint **deployed and validated on prod** — debate completeness, three-layer Action Plan, layout cleanup, Tier 1/B1 optimizations, post-job automation.

| Canonical run | Pipeline | Use for |
|---------------|----------|---------|
| **`20260529_225159`** | **SUCCESS** | **Action Plan** — 8/8 blocks with Strategic Context + Champion + Dissent; no placeholder synthesis |
| `20260529_201848` | SUCCESS | Debate fix — 3 complete paragraphs, brawl validation |
| `20260529_220253` | SUCCESS | Post B1 (`red_teamer` → Flash) |
| `20260529_214609` | Supervisor BLOCKED | Pre-layout baseline; Integrity TSM false positive (R1 vs R2 digest) |

*Full EOD table and open items from this sprint:* see git history for `action_tracker.md` before May 30 late-night rewrite, or [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md).

---

## SaaS / multi-tenant roadmap (**blocked — stabilize first**)

**Do not start SaaS implementation until the current single-tenant pipeline is stabilized and simplified.**

| Pri | ID | Effort | Item | Gate |
|-----|-----|--------|------|------|
| — | SAAS-0 | — | Design SSOT — [`saas_technical_solution.md`](saas_technical_solution.md) + schema + rollout + client + [`saas_tenancy_gaps.md`](saas_tenancy_gaps.md) | **DONE** (May 30) |
| **P2** | SAAS-1 | L | Phase 1–2: `PortfolioSource` + Azure Postgres + admin-provision beta | **Blocked on:** stable QA pass rate + core flow simplification |
| **P3** | SAAS-2 | M | Phase 4: Entra External ID self-service | After Phase 2b beta validated |

---

## Go-to-market QA (**after private beta — before public launch**)

**Not now.** Schedule only after tester users are running the product on real portfolio data (private beta). Must complete **before** public engagement, paid acquisition, or press outreach.

| Pri | ID | Effort | Item | Gate |
|-----|-----|--------|------|------|
| **P2** | MKT-QA-1 | M | **Marketing QA agent** — LLM + deterministic review of landing page copy, onboarding emails, social/announcement snippets, and any forwardable marketing HTML for: implied investor endorsement, securities/marketing language, brand/tone vs Stealth Wealth SSOT, consistency with Legal Counsel SaaS policy ([`legal_policy.py`](../src/qa/legal_policy.py)), and CTA/disclaimer hygiene | **After:** private beta live (tester cohort on prod). **Before:** public launch. **Blocked on:** SAAS-1 beta provisioning + stable deliver/QA path for testers |

**Scope sketch (implementation later):** separate from per-run `legal_counsel_qa` (briefing artifact) and daily `legal_counsel_code` (repo prompts). Marketing QA targets **growth surfaces** — website, waitlist, beta invite emails, App Store / Product Hunt copy — not the daily executive briefing. Findings → dedicated blob + email (mirror Legal Counsel delivery pattern).

---

## Recently shipped (last 7 days)

| Area | Commit(s) | Run / note |
|------|-----------|------------|
| **Crucible palette + QA backlog** | `760ebb6`, `52613b2`, `b6984fa` | Prod run **`20260531_014121`** — void charcoal rebuttal, triage UI, sync_backlog |
| **Today's Actions + chart DPR** | `c4189f1`, `6de1d69` | Validated on `014121` briefing |
| **Deploy batch + review universe** | `83ecdca`, `9f26173` | Run `20260530_205821` |
| **Hypatia roster + Stealth Wealth** | `d970f20` | Focus-group personas; avatar SSOT |
| Three-layer Action Plan | `cfe55fd`, `380427f` | Canonical `225159` |
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
