# Product Principles — SC Invest Boardroom

**Status:** Active · **Last updated:** May 29, 2026  
**Purpose:** Non-negotiable design rules for a product-grade pipeline. Enforced in code review and `.cursorrules`. Backlog derived from gaps lives in [`action_tracker.md`](action_tracker.md).

---

## 1. Board decides; code executes

Panel Round 2 JSON is ground truth. Final verdicts come from `vote_engine` + `guardrails` + `chairman_alignment` whenever votes are majority-deterministic. LLM chairman is **exception**, not default — tie-breaks and ambiguous funding only.

**Code:** `can_determine_allocation()`, `build_chairman_allocation()`, `mandate_verdict()`.

---

## 2. Fail closed; no LLM repair on debate audit failure

If in-loop compliance fails, stop the run. Do **not** re-prompt chairman or compliance agents to negotiate past the gate. Persist review artifacts and route to experts.

**Scope:** LLM conversation during debate only. Does **not** ban API backoff, deploy retries, or deterministic Python fixes.

**Artifacts:** `compliance_failure_{run_id}.json`, `debate_review_{run_id}.json`, `requires_expert_review`.

---

## 3. Python gates before LLM narration

Financial limits, vote tallies, majority alignment, max buys, alpha eligibility, and hedge mandate are **deterministic Python first**. LLM compliance (Markopolos) runs only when chairman Pro actually allocated (`allocation_source=llm`). On `vote_engine` days, Python compliance is sufficient.

---

## 4. Chairman is board recorder, not decision maker

Product language: executive secretary / board recorder — not an independent allocator. Rich prose may come from a future **narrator-only** Flash pass that cannot change verdict fields. Druckenmiller persona stays for tone; authority stays with votes + code.

---

## 5. Errors must be visible, not smoothed over

Silent LLM retries hide prompt and data defects. Blocked runs are **signal** for prompt engineering and data quality review — not noise to auto-heal. Target: weekly expert-review digest until Run Review UI exists.

---

## 6. One run, one story (observability)

Every run should answer in one place: votes → allocation source → gate result → expert queue. Telemetry must carry `allocation_source`, `compliance_source`, `chairman_bypassed`. **Run Review UI** (backlog) is the product surface for this.

---

## 7. Freeze the roster until pass rate is stable

No new panelists, QA agents, or debate rounds until deterministic allocation + fail-closed compliance prove reliable in prod. Improve prompts and data before adding personas.

---

## Enforcement checklist (PR / pre-push)

| Question | Must be yes |
|----------|-------------|
| Does this move verdict authority into Python? | Prefer yes |
| Does this add an LLM retry on a failed gate? | Must be no |
| Does this add a new agent without observability? | Must be no |
| Are failure artifacts persisted for expert review? | Must be yes on debate gates |

---

## References

| Topic | Doc |
|-------|-----|
| Vote engine | [`technical_solution.md`](technical_solution.md) §2.2 |
| QA layers | [`qa_layers.md`](qa_layers.md) |
| Rejected approaches | [`engineering_playbook.md`](engineering_playbook.md) |
| Cursor workflow | [`.cursorrules`](../.cursorrules) |
