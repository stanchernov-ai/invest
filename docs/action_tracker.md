# SC Invest Boardroom — Action Tracker

**Status:** Active  
**Last Updated:** May 30, 2026 (deploy batch staged — commit/deploy blocked)

**Purpose:** Current session pickup and prioritized backlog. Historical handoffs and Phase 0–6 specs live in [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md). Maintenance rules: [`doc_hygiene.md`](doc_hygiene.md). Doc map: [`DOCUMENTATION.md`](DOCUMENTATION.md).

**Product principles (enforce in every PR):** [`product_principles.md`](product_principles.md)

---

## Session Handoff — May 30, 2026 deploy batch (**pick up here**)

**Theme:** Large **deliver + compliance + briefing UX** batch is **fully staged** but **not committed**. Prior agent hung on `git commit` (pre-commit runs full `unittest discover`). **Prod unchanged** at `a17792b`.

| State | Detail |
|-------|--------|
| **Prod HEAD** | `a17792b` — vote digest SSOT, Action Plan context, email delivery logging |
| **Last validated run** | `20260530_190325` (~3m46s, QA PASS, email ok) — pre–Legal Counsel / UNICORN-1 |
| **Local git** | **33 files staged** (~1,591 lines); **not committed, not pushed** |
| **Deploy** | Blocked — push `main` triggers GitHub Actions → `app-boardroom-prod` |
| **Next run** | After deploy: `GET /api/prepare?code=<function-key>` on regional hostname below |

**Kickoff:** `GET /api/prepare?code=<function-key>` — hostname: `app-boardroom-prod-b5h4epg2d0cxefa0.eastus-01.azurewebsites.net` ([`engineering_playbook.md`](engineering_playbook.md)). Function key: `az functionapp keys list -g rg-boardroom-prod -n app-boardroom-prod --query functionKeys.default -o tsv`.

### First steps (successor — do in order)

1. **Commit staged batch only** (PowerShell — no bash heredoc):

```powershell
cd c:\Projects\sc-invest-boardroom
@'
Add Legal Counsel QA, briefing UX fixes, and investor voice.

Legal counsel scans briefing HTML and codebase daily; catalyst fallback, per-stock debate, QA review footer, hide Unicorn when no actionable unanimous trades.
'@ | Set-Content -Encoding utf8 _commitmsg.txt
git commit -F _commitmsg.txt
Remove-Item _commitmsg.txt
```

Pre-commit hook runs **full** `unittest discover` — expect **2–10 min**; do not interrupt. If hook fails, fix and **new commit** (do not amend unless hook auto-fixed files).

2. **Push:** `$env:GIT_TERMINAL_PROMPT=0; git push origin main`
3. **Watch deploy:** `gh run watch --exit-status` (latest “Deploy to Azure Functions” workflow)
4. **Kick off run** (note local `run_id` = timestamp at trigger):

```powershell
$key = az functionapp keys list -g rg-boardroom-prod -n app-boardroom-prod --query functionKeys.default -o tsv
Invoke-WebRequest "https://app-boardroom-prod-b5h4epg2d0cxefa0.eastus-01.azurewebsites.net/api/prepare?code=$key" -UseBasicParsing
```

5. **Poll:** `.venv\Scripts\python.exe scripts\wait_for_run.py --run-id YYYYMMDD_HHMMSS --timeout 2700 --post-job`
6. **Human QA (Gmail):** section order, per-stock debate, catalysts, Legal Counsel email, QA review footer link, Unicorn hidden when no 5/5 Buy/Reduce

### Staged batch (ready to ship)

| Area | Key paths | What |
|------|-----------|------|
| **Legal Counsel QA** | `src/qa/legal_audit.py`, `legal_policy.py`, `legal_delivery.py`, `src/jobs/legal_code_audit.py`, `function_app.py` | Briefing HTML scan at deliver; daily 8 AM code audit timer + `GET /api/legal-code-audit`; findings blob + email Stan |
| **Investor voice** | `src/core/investor_voice.py`, `agents.py` | Panelists cite named investors + industry terms; SaaS-safe attribution mandate |
| **Briefing UX** | `reporting.py`, `briefing_style.py` | GFX-4 order (Charts → SoTU → Alpha → Debate → Unicorn → Action Plan); QA review footer CTA; catalyst fallback; **UNICORN-1** hide when empty |
| **Debate** | `boardroom_brawl.py`, `engine.py` | Per-stock Round 1 positions (not SoTU duplicate) |
| **Catalysts** | `catalysts.py`, `deliver.py` | `ensure_chairman_catalysts` when chairman `upcoming_events` empty |
| **INT-1** | `integrity_audit.py`, `qa_pipeline.py`, fixtures | Vote digest in integrity prompt; Post Mortem cross-check; `count_equity_buys` cap fix |
| **Tests** | `test_legal_*`, `test_catalysts`, `test_unicorn_protocol`, `test_boardroom_brawl`, etc. | 52+ tests pass on touched modules (run full suite before push) |

**Pre-push sanity:**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_unicorn_protocol.py tests/test_legal_audit.py tests/test_legal_delivery.py tests/test_catalysts.py tests/test_boardroom_brawl.py tests/test_vote_engine.py -q
```

### Not in staged batch (separate WIP — do not mix into first commit)

| Path | Status |
|------|--------|
| `src/data/review_universe.py`, `tests/test_review_universe.py` | **Untracked** — Mag7 + Yahoo watchlist merge at prepare |
| `src/jobs/prepare.py`, `src/scout.py` | **Unstaged** — wires `build_review_universe()`; needs its own commit + test |
| `docs/saas_technical_solution.md` | Unstaged edits |
| `docs/saas_data_schema.md`, `docs/saas_postgres_rollout.md` | Untracked SaaS design (SAAS-0 docs only) |

### Open items (prioritized)

| Pri | ID | Effort | Item | Notes |
|-----|-----|--------|------|-------|
| **P0** | DEPLOY-1 | S | Commit + push staged batch + prod run | **Blocked this session** — pre-commit hang |
| **P1** | AV-2 | S | SoTU avatar ring alignment | Re-export 128×128 centered PNGs |
| **P1** | GFX-2 | S | Logo contrast on `#27272a` | Partial locally — verify Gmail post-deploy |
| **P1** | GFX-3 | M | Pie categorical palette | Too many similar greens |
| **P1** | CHAIR-1 | S | Post Mortem Trim→Hold mandate | AVGO/ASML on `010432` |
| **P1** | AP-2 | S | “Today’s actions” summary box | Not started |
| **P1** | REVIEW-1 | M | Watchlist universe refactor | `review_universe.py` WIP — untracked |
| **P2** | B2 | S | Skip `prompt_engineer` LLM on deterministic FAIL | [`agent_optimization_handoff.md`](agent_optimization_handoff.md) §B2 |
| **P2** | R2-1 | M | Round 2 verbatim R1 copy | Prompt Engineer recurring |
| **P3** | MKT-QA-1 | M | Marketing QA agent | After private beta — see below |

**Done locally (in staged batch, not prod):** AP-1, GFX-4, GFX-QA, INT-1, UNICORN-1, Legal Counsel QA, catalysts, per-stock debate, QA review footer, investor voice.

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
| — | SAAS-0 | — | Design SSOT — [`saas_technical_solution.md`](saas_technical_solution.md) + [`saas_data_schema.md`](saas_data_schema.md) + [`saas_postgres_rollout.md`](saas_postgres_rollout.md) | **DONE** (May 30) |
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
