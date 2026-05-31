# SC Invest Boardroom — Action Tracker

**Status:** Active  
**Last Updated:** May 30, 2026 (deploy batch shipped; **HR / Prompt Engineer / Legal** review logged below; prod `20260530_205821`)

**Purpose:** Current session pickup and prioritized backlog. Historical handoffs and Phase 0–6 specs live in [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md). Maintenance rules: [`doc_hygiene.md`](doc_hygiene.md). Doc map: [`DOCUMENTATION.md`](DOCUMENTATION.md).

**Product principles (enforce in every PR):** [`product_principles.md`](product_principles.md)

---

## Session Handoff — May 30, 2026 deploy + review universe (**pick up here**)

**Theme:** **Deploy batch and REVIEW-1 are on prod.** Prior stream handoff (staged / not committed) is **superseded** — this session committed, pushed, deployed, and validated.

| State | Detail |
|-------|--------|
| **Prod HEAD** | `9f26173` — Legal Counsel + briefing UX (`83ecdca`) + review universe / Yahoo cache / FMP stable screener (`9f26173`) |
| **Last validated run** | **`20260530_205821`** (~4 min, pipeline SUCCESS, email ok) — first post–Legal Counsel / UNICORN-1 / Mag7 run |
| **Local git** | `main` synced with `origin/main`; **uncommitted WIP** in working tree (HR/QA roster, SaaS docs — see below) |
| **Deploy** | GitHub Actions on push to `main` → `app-boardroom-prod` (no `gh` CLI on Stan's Windows box — poll Azure or GitHub web) |

**Kickoff (manual run):** `GET /api/prepare?code=<function-key>` — hostname: `app-boardroom-prod-b5h4epg2d0cxefa0.eastus-01.azurewebsites.net`. Function key: `az functionapp keys list -g rg-boardroom-prod -n app-boardroom-prod --query functionKeys.default -o tsv`. **Note:** `/api/prepare` is **synchronous** — waits for prepare phase (~8–60s) before returning 202; do not interrupt.

```powershell
$key = az functionapp keys list -g rg-boardroom-prod -n app-boardroom-prod --query functionKeys.default -o tsv
Invoke-WebRequest "https://app-boardroom-prod-b5h4epg2d0cxefa0.eastus-01.azurewebsites.net/api/prepare?code=$key" -UseBasicParsing
.venv\Scripts\python.exe scripts\wait_for_run.py --run-id YYYYMMDD_HHMMSS --timeout 2700 --post-job
```

### Shipped in `83ecdca` + `9f26173`

| Area | Key paths | What |
|------|-----------|------|
| **Legal Counsel QA** | `src/qa/legal_*.py`, `src/jobs/legal_code_audit.py`, `function_app.py` | Briefing HTML scan at deliver; daily 8 AM code audit; findings blob + email |
| **Investor voice** | `src/core/investor_voice.py`, `agents.py` | Panelists cite named investors; SaaS-safe attribution |
| **Briefing UX** | `reporting.py`, `briefing_style.py` | GFX-4 order; QA review footer; catalyst fallback; **UNICORN-1** hide when empty |
| **Debate** | `boardroom_brawl.py`, `engine.py` | Per-stock Round 1 positions |
| **Catalysts** | `catalysts.py`, `deliver.py` | `ensure_chairman_catalysts` fallback |
| **INT-1** | `integrity_audit.py`, `qa_pipeline.py` | Vote digest in integrity prompt; cap fix |
| **REVIEW-1** | `src/data/review_universe.py`, `prepare.py`, `scout.py` | Mag7 + manual + **daily-cached** Yahoo; FMP `/stable/company-screener` fallback |
| **Scout validation** | `scripts/validate_scout_sources.py` | Live probe before prod scout changes — run and PASS before deploy |

### Run `20260530_205821` — post-deploy QA notes

| Phase | Duration | Status |
|-------|----------|--------|
| Prepare | 8s | success |
| Debate | 106s | success |
| Deliver | 97s | success |

**Email:** briefing + QA dashboard + Legal Counsel — all sent.

**QA advisory (non-blocking):**
- **Systems Architect** — debate log Pass spam (164 mentions / 27 symbols) — Mag7 + Yahoo universe widened watchlist
- **Graphics Designer** — SoTU `box-shadow` non-SSOT colors; MSFT logo contrast (GFX-2)
- **Integrity** — disputed Graphics CRITICAL (meta-QA disagreement)

**Human QA still open (Gmail):** section order (GFX-4), per-stock debate, catalysts, Legal Counsel email, QA review footer, Unicorn hidden when no 5/5 trades.

**Artifacts cached:** `.cache/reports/executive_briefing_20260530_205821.html`, `qa_dashboard_*.html`, `state/legal_counsel_briefing_*.json`

### Uncommitted WIP (do not assume prod)

| Path | Status |
|------|--------|
| `docs/saas_data_schema.md`, `docs/saas_postgres_rollout.md`, `docs/saas_technical_solution.md` | Untracked / unstaged — SAAS-0 design only |
| `docs/hr_qa_roster_handoff.md`, `src/hr_review.py`, `src/finance_oversight.py`, `tests/test_hr_review.py` | HR/QA roster stream — separate commit |
| `src/qa_pipeline.py`, `src/qa/architect_audit.py`, `src/qa/persona_audit.py`, etc. | Unstaged local edits — verify before next deploy |

### Issue log — HR / Prompt Engineer / Legal Counsel (May 30, 2026)

*Session: three-agent review (system roster, prompts vs runtime, SaaS-safe investor voice). Deterministic legal code scan: 0 CRITICAL. No prod telemetry in `.cache` for full HR LLM verdict.*

| ID | Agent | Sev | Issue | Status |
|----|-------|-----|-------|--------|
| PE-VOICE-1 | Prompt Engineer + Legal | P1 | Panel prompts: modern lexicon + no quotation marks on real investors; `META_DIRECTIVE` rationales; legal SAFE list aligned; deterministic `persona_audit` fabricated-quote gate | **Shipped** — `tests/test_persona_audit.py`; validate on next prod run |
| HR-ROSTER-1 | HR | P2 | Deliver-phase QA overlap (`post_mortem_qa`, `system_architect`, `prompt_engineer`, `qa_integrity_auditor`) — main token sink on vote_engine days | **Open** — consolidate per [`agent_architecture.md`](agent_architecture.md) §9 |
| HR-TELEM-1 | HR | P1 | Full HR utilization + KEEP/IMPROVE verdicts need `AGENT_ACTIVITY` from prod telemetry | **Open** — extends H1; `python -m src.hr_review <telemetry>` |
| PE-R2-1 | Prompt Engineer | P1 | Round 2 `overall_portfolio_critique` verbatim copy of Round 1 | **Open** — same as backlog R2-1; deterministic gate exists |
| PE-SYCO-1 | Prompt Engineer | P2 | Unanimous verdict buckets on most tickers (sycophancy collapse) | **Open** — deterministic threshold 60%; tune prompts if recurring |
| LEG-SAFE-1 | Legal Counsel | P1 | `legal_counsel_code` SAFE list contradicted `investor_voice` (cited attributed public-record quotes) | **Shipped** — part of PE-VOICE-1 |
| LEG-BRIEF-1 | Legal Counsel | P2 | Briefing Jinja wraps `champion_quote` in `"..."` — safe when speaker is panelist; FAIL if body reads like Buffett/Lynch live quote | **Open** — extend `legal_audit.py` or Legal Counsel QA checklist |
| LEG-MUNGER-1 | Legal Counsel | P3 | `MUNGER_DOCTRINE` in `schemas.py` names Charlie Munger in injected debate text — not endorsement; optional rename to “concentration discipline” for SaaS copy | **Open** |
| ARCH-PASS-1 | Systems Architect | P1 | Watchlist Pass spam in debate log (27 symbols / Mag7+Yahoo universe) | **Open** — same as PASS-SPAM-1 (`205821`) |
| GFX-SOTU-1 | Graphics Designer | P1 | SoTU non-SSOT `box-shadow` / colors | **Open** — `205821` advisory |
| GFX-LOGO-1 | Graphics Designer | P1 | MSFT logo contrast on dark canvas | **Open** — GFX-2 |

### Open items (prioritized)

| Pri | ID | Effort | Item | Notes |
|-----|-----|--------|------|-------|
| **P0** | QA-HUMAN-1 | S | Gmail review of `20260530_205821` | GFX-4, Legal Counsel, UNICORN-1, debate |
| **P1** | HR-1 | S | Commit + deploy HR/QA_EXECUTION batch | WIP: `hr_review`, `deliver`, `qa_pipeline` — see [`hr_qa_roster_handoff.md`](hr_qa_roster_handoff.md) |
| **P1** | HR-TELEM-1 | S | HR Efficiency review on prod telemetry | `fetch_azure_reports` → `hr_review`; `QA_EXECUTION` on prod (H1) |
| **P2** | LEG-BRIEF-1 | S | Legal: panelist-only champion_quote in briefing HTML | LEG-BRIEF-1 — see issue log |
| **P2** | HR-ROSTER-1 | M | Reduce deliver QA overlap / token sink | HR-ROSTER-1; B3 partial shipped — see [`agent_optimization_handoff.md`](agent_optimization_handoff.md) |
| **P1** | H1 | S | Post-deploy HR check with `QA_EXECUTION` | Partial on `205821` — table OK locally, telemetry field missing on prod |
| **P1** | PASS-SPAM-1 | M | Reduce watchlist Pass spam in debate log | Architect FAIL on `205821`; 27-symbol universe |
| **P1** | AV-2 | S | SoTU avatar ring alignment | Re-export 128×128 centered PNGs |
| **P1** | GFX-2 | S | Logo contrast on `#27272a` | Confirmed on `205821` — MSFT Alpha Pick |
| **P1** | GFX-3 | M | Pie categorical palette | Too many similar greens |
| **P1** | CHAIR-1 | S | Post Mortem Trim→Hold mandate | AVGO/ASML on `010432` |
| **P1** | AP-2 | S | “Today’s actions” summary box | Not started |
| **P2** | B2 | S | Skip `prompt_engineer` LLM on deterministic FAIL | **Done** — `qa_augmentation.py`; borderline band 52–60% |
| **P2** | R2-1 | M | Round 2 verbatim R1 copy | PE-R2-1 — deterministic `persona_audit`; recurring on prod |
| **P3** | LEG-MUNGER-1 | S | Rename `MUNGER_DOCTRINE` user-facing string for SaaS | Optional; debate injection only |
| **P3** | MKT-QA-1 | M | Marketing QA agent | After private beta |

**Done (now prod):** DEPLOY-1, REVIEW-1, AP-1, GFX-4, GFX-QA, INT-1, UNICORN-1, Legal Counsel QA, catalysts, per-stock debate, QA review footer, investor voice (initial), Yahoo daily cache, scout validation script, **PE-VOICE-1** (SaaS-safe attribution + fabricated-quote persona gate).

**HR / roster (partial):** `qa_augmentation.py` on prod; full HR status + `QA_EXECUTION` telemetry — **WIP, not prod**. Pickup: [`hr_qa_roster_handoff.md`](hr_qa_roster_handoff.md) §9.

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
| **Deploy batch + review universe** | `83ecdca`, `9f26173` | Prod run **`20260530_205821`** — Legal Counsel, UNICORN-1, Mag7/Yahoo cache |
| **Hypatia roster + Stealth Wealth** | `d970f20` | Focus-group personas; avatar SSOT; dark native pies |
| **Gmail inline dark palette** | `58a94ab` | Validated `20260530_010432` |
| SoTU + chart typography | `2bcbd04` | Round 1 portfolio quotes |
| Three-layer Action Plan | `cfe55fd`, `380427f` | Canonical `225159` |
| Briefing layout + charts sprint | `04af83d`–`b1707c7` | Dark palette, pie legend fix |
| B1 + Tier 1 QA | `748ad6c`, `a64bcd9` | Flash red_teamer; Munger/QA skips |
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
