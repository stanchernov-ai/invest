# Documentation Index

**Status:** Active  
**Last updated:** May 29, 2026  
**SSOT for:** which document to read or update — agents should start here when unsure where something lives.

**Do not duplicate** content from the docs below into this file. Link only.

---

## Start here (every session)

| Order | Document | Why |
|------:|----------|-----|
| 1 | [`action_tracker.md`](action_tracker.md) | **Session Handoff** at top — current pickup, open priorities |
| 2 | [`.cursorrules`](../.cursorrules) | Guardrails, collaboration MCQ, Cursor sub-agents, triggers |
| 3 | [`engineering_playbook.md`](engineering_playbook.md) | Skim before retrying a rejected approach |

When auditing a blocked cycle: `.cursor/agent_state/ecosystem_state.json` (see `.cursorrules` §3).

---

## By task — which doc to open

| I need to… | Read |
|------------|------|
| See agent diagrams, production roster, QA layers | [`agent_architecture.md`](agent_architecture.md) |
| Understand **which QA module** does what | [`qa_layers.md`](qa_layers.md) |
| Understand pipeline phases, deploy, data layer | [`technical_solution.md`](technical_solution.md) |
| Map FMP endpoints / fields / Starter tier | [`fmp_data_dictionary.md`](fmp_data_dictionary.md) |
| Review subscriptions, SaaS costs, finance oversight | [`tech_stack_and_subscriptions.md`](tech_stack_and_subscriptions.md) + `subscriptions_registry.json` |
| Run post-deliver retrospective | [`post_deliver_checklist.md`](post_deliver_checklist.md) |
| Add backlog or record a decision | [`action_tracker.md`](action_tracker.md) |
| Change guardrails or Cursor workflow | [`.cursorrules`](../.cursorrules) only |
| Change production agent roster or QA stack | [`agent_architecture.md`](agent_architecture.md) + `src/core/agents.py` |

---

## Human workflow & backlog

| Document | SSOT for |
|----------|----------|
| [`action_tracker.md`](action_tracker.md) | Backlog, Session Handoff, shipped work |
| [`post_deliver_checklist.md`](post_deliver_checklist.md) | After each deliver run — validation + backlog hygiene |
| [`engineering_playbook.md`](engineering_playbook.md) | Rejected approaches and gotchas |

---

## Architecture & system design

| Document | SSOT for |
|----------|----------|
| [`../README.md`](../README.md) | Repo entry point — quick start + doc chain |
| [`agent_architecture.md`](agent_architecture.md) | Agent inventory, mermaid diagrams, QA layers L0–L7, golden fixtures |
| [`qa_layers.md`](qa_layers.md) | **Which QA file runs when** — deliver vs weekly vs dev |
| [`technical_solution.md`](technical_solution.md) | End-to-end flow, repo layout, env vars, blob containers |
| [`agent_guardrails.md`](agent_guardrails.md) | **Pointer only** → `.cursorrules` |

---

## Data, API & cost reference

| Document | SSOT for |
|----------|----------|
| [`fmp_data_dictionary.md`](fmp_data_dictionary.md) | FMP URLs, field map, fallback rules |
| [`tech_stack_and_subscriptions.md`](tech_stack_and_subscriptions.md) | Narrative companion to subscription registry |
| [`subscriptions_registry.json`](subscriptions_registry.json) | Structured SaaS/cloud inventory |

---

## Cursor dev plane (config, not prose)

| Path | SSOT for |
|------|----------|
| [`.cursorrules`](../.cursorrules) | Guardrails, failsafes, sub-agent mandates, execution triggers |
| `.cursor/rules/*.mdc` | Thin triggers per persona — **no architecture prose** |
| `.cursor/rules/action_tracker.mdc` | Forces read of `action_tracker.md` at session start |
| `scripts/pre_commit_check.py` | Blocking QA + refactoring on commit |

Persona rule files: `refactoring_agent.mdc`, `qa_validation_agent.mdc`, `api_optimization_agent.mdc`, `data_insight_agent.mdc`, `supervisor_agent.mdc`.

---

## Machine / runtime state (not source docs)

| Path | Purpose |
|------|---------|
| `.cursor/agent_state/ecosystem_state.json` | Conflicts, audits, QA flags, scorecards (gitignored; copy from `ecosystem_state.example.json`; rotate at 50 entries) |
| `BOARDROOM_DATA_DIR` / Azure `boardroom-state` | Runtime JSON: `board_verdicts.json`, checkpoints, telemetry |
| `.cache/` | Local Azure artifact pull via `tools/fetch_azure_reports.py` |

**Gitignored generated outputs** (not docs): `logs/`, `src/output/*.md`, `qa_*_latest.*` — see `.gitignore`.

---

## Duplication rules (keep docs clean)

| Topic | Edit here | Do not copy into |
|-------|-----------|------------------|
| Guardrails, MCQ protocol, Two Strike | `.cursorrules` | `agent_architecture.md`, `agent_guardrails.md` |
| Agent diagrams, QA stack, roster tables | `agent_architecture.md` | `.cursorrules` |
| FMP endpoints | `fmp_data_dictionary.md` | `technical_solution.md` (link only) |
| Backlog / next steps | `.cursorrules` §0.6 — easy wins (impact ÷ effort) first |
| Rejected approaches | `engineering_playbook.md` | Inline comments unless one-line pointer |

---

## When to update which doc

| You changed… | Update |
|--------------|--------|
| Agent in `src/core/agents.py` | `agent_architecture.md` §3, bump Last updated |
| Cursor rule in `.cursor/rules/` | `.cursorrules` if mandate/trigger changes; `agent_architecture.md` §2 file table |
| Pipeline phase or checkpoint shape | `agent_architecture.md`, `technical_solution.md` |
| New doc file | **This index** + `action_tracker.md` Documentation index |
| Shipped work / new priority | `action_tracker.md` Session Handoff |
