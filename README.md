# SC Invest Boardroom

Daily multi-agent investment boardroom: brokerage CSVs → FMP enrichment → Gemini debate → HTML briefing + QA dashboard → email. Runs on **Azure Functions** (`app-boardroom-prod`) with a local entry point for dev.

## Quick start

```powershell
# Local full pipeline (prepare → debate → deliver)
.venv\Scripts\python.exe -m src.main

# Pull latest Azure artifacts
.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id YYYYMMDD_HHMMSS
```

Secrets: copy `.env` from your vault (see `src/config/settings.py` for required vars). Deploy: push to `main` → GitHub Actions → Azure Functions.

## Documentation (read in this order)

| Step | Doc |
|------|-----|
| 1 | [`docs/action_tracker.md`](docs/action_tracker.md) — **Session Handoff** + backlog |
| 2 | [`.cursorrules`](.cursorrules) — guardrails, Cursor workflow |
| 3 | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) — **master index** (all SSOT docs) |

**Architecture:** [`docs/agent_architecture.md`](docs/agent_architecture.md) · **System design:** [`docs/technical_solution.md`](docs/technical_solution.md) · **QA map:** [`docs/qa_layers.md`](docs/qa_layers.md)

## Repo layout (high level)

| Path | Role |
|------|------|
| `function_app.py` | Azure timers + queue chain |
| `src/jobs/` | `prepare` → `debate` → `deliver` |
| `src/core/` | Engine, agents, schemas, **`vote_engine`**, guardrails, compliance |
| `src/qa/` | Deterministic QA + human review UI |
| `src/qa_pipeline.py` | Per-run LLM post-flight QA |
| `docs/` | Human SSOT documentation |

Generated run outputs (`logs/`, `src/output/*.md`, `qa_*_latest.*`) are gitignored — artifacts live in Azure Blob or local `.cache/`.
