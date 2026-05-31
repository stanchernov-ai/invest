# Documentation Index

**Status:** Active  
**Last updated:** May 30, 2026 (deploy batch handoff)  
**SSOT for:** which document to read or update — agents should start here when unsure where something lives.

**Do not duplicate** content from the docs below into this file. Link only.

---

## Start here (every session)

| Order | Document | Why |
|------:|----------|-----|
| 1 | [`action_tracker.md`](action_tracker.md) | **Session Handoff** at top — current pickup, open priorities |
| 2 | [`product_principles.md`](product_principles.md) | Non-negotiable product rules — board in code, fail closed |
| 3 | [`.cursorrules`](../.cursorrules) | Guardrails, collaboration MCQ, Cursor sub-agents, triggers |
| 4 | [`engineering_playbook.md`](engineering_playbook.md) | Skim before retrying a rejected approach |

When auditing a blocked cycle: `.cursor/agent_state/ecosystem_state.json` (see `.cursorrules` §3).

---

## By task — which doc to open

| I need to… | Read |
|------------|------|
| See agent diagrams, production roster, QA layers | [`agent_architecture.md`](agent_architecture.md) |
| **Agent audit, runtime optimizations, funding sell** | [`agent_optimization_handoff.md`](agent_optimization_handoff.md) |
| **Cursor agents, ecosystem_state, post-job sync** | [`cursor_dev_plane_handoff.md`](cursor_dev_plane_handoff.md) |
| Understand **which QA module** does what | [`qa_layers.md`](qa_layers.md) |
| Understand pipeline phases, deploy, data layer, **vote_engine** | [`technical_solution.md`](technical_solution.md) |
| Plan SaaS / multi-tenant (blocked on stabilization) | [`saas_technical_solution.md`](saas_technical_solution.md) |
| Postgres schema for multi-user | [`saas_data_schema.md`](saas_data_schema.md) |
| Deploy Azure Postgres + admin-provision beta users | [`saas_postgres_rollout.md`](saas_postgres_rollout.md) |
| Edit briefing HTML palette / dark theme | [`briefing_style.md`](briefing_style.md) + `src/output/briefing_style.py` |
| Edit briefing charts / QuickChart / section order | [`briefing_charts_handoff.md`](briefing_charts_handoff.md) + `src/output/reporting.py` |
| Debug chairman retries / vote alignment | [`qa_layers.md`](qa_layers.md) § Debate-phase audit + `src/core/vote_engine.py` |
| Map FMP endpoints / fields / Starter tier | [`fmp_data_dictionary.md`](fmp_data_dictionary.md) |
| Review subscriptions, SaaS costs, finance oversight | [`tech_stack_and_subscriptions.md`](tech_stack_and_subscriptions.md) + `subscriptions_registry.json` |
| Run post-deliver retrospective | [`post_deliver_checklist.md`](post_deliver_checklist.md) |
| Add backlog or record a decision | [`action_tracker.md`](action_tracker.md) |
| Doc health / which files to clean | [`doc_health_snapshot.md`](doc_health_snapshot.md) |
| Change guardrails or Cursor workflow | [`.cursorrules`](../.cursorrules) only |
| Change production agent roster or QA stack | [`agent_architecture.md`](agent_architecture.md) + `src/core/agents.py` |

---

## Human workflow & backlog

| Document | SSOT for |
|----------|----------|
| [`action_tracker.md`](action_tracker.md) | **Live** backlog + Session Handoff only (≤ ~200 lines) |
| [`doc_hygiene.md`](doc_hygiene.md) | How to trim tracker, archive handoffs, agent doc rules |
| [`doc_health_snapshot.md`](doc_health_snapshot.md) | Per-file health, impact tiers, DOC-* cleanup backlog |
| [`archive/`](archive/) | Read-only May 2026 implementation log + old handoffs |
| [`post_deliver_checklist.md`](post_deliver_checklist.md) | After each deliver run — validation + backlog hygiene |
| [`engineering_playbook.md`](engineering_playbook.md) | Rejected approaches and gotchas |

---

## Architecture & system design

| Document | SSOT for |
|----------|----------|
| [`../README.md`](../README.md) | Repo entry point — quick start + doc chain |
| [`agent_architecture.md`](agent_architecture.md) | Agent inventory, mermaid diagrams, QA layers L0–L7, golden fixtures |
| [`agent_optimization_handoff.md`](agent_optimization_handoff.md) | **May 2026 audit**, telemetry baseline, funding sell, planned runtime tickets A1–B4 |
| [`cursor_dev_plane_handoff.md`](cursor_dev_plane_handoff.md) | Cursor agents, ecosystem_state sync, standing QA digest tickets C1–C5 |
| [`qa_layers.md`](qa_layers.md) | **Which QA file runs when** — deliver vs weekly vs dev |
| [`briefing_charts_handoff.md`](briefing_charts_handoff.md) | QuickChart, palettes, briefing layout |
| [`technical_solution.md`](technical_solution.md) | End-to-end flow, repo layout, env vars, blob containers, vote_engine |
| [`saas_technical_solution.md`](saas_technical_solution.md) | **Planning** — multi-user architecture, Entra External ID, tenancy phases |
| [`saas_data_schema.md`](saas_data_schema.md) | **Planning** — Postgres tables, indexes, `profile_json`, migration SQL |
| [`saas_postgres_rollout.md`](saas_postgres_rollout.md) | **Planning** — Azure Postgres provisioning + admin-provision beta playbook |
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
| Vote engine / compliance Python checks | `technical_solution.md` §2.2, `agent_architecture.md` §6, `tests/test_vote_engine.py` |
| Funding sell / allocation rules | [`agent_optimization_handoff.md`](agent_optimization_handoff.md) §3.1, `src/core/vote_engine.py` |
| Planned agent cost/latency wins | [`agent_optimization_handoff.md`](agent_optimization_handoff.md) §5 |
| Cursor ecosystem_state / post-job agents | [`cursor_dev_plane_handoff.md`](cursor_dev_plane_handoff.md) |
| Briefing charts / QuickChart config | [`briefing_charts_handoff.md`](briefing_charts_handoff.md) + `tests/test_reporting_briefing.py` |
| New doc file | **This index** only (do not add doc tables to action_tracker) |
| Shipped work / new priority | `action_tracker.md` Session Handoff — per `doc_hygiene.md` |
| Tracker exceeds ~200 lines | Archive to `docs/archive/` per `doc_hygiene.md` |
