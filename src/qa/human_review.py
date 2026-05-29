"""Human-confirmed QA reviews — Azure HTTP UI + dual persistence.

Per-agent thumbs up/down after the QA dashboard email. Stored in:
  - boardroom-state / qa_human_review_{run_id}.json
  - boardroom-state / qa_human_reviews_ledger.json (rolling history)
  - .cursor/agent_state/ecosystem_state.json → qa_human_reviews[] (when writable)
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from src import storage_client

logger = logging.getLogger(__name__)

RUN_ID_PATTERN = re.compile(r"^\d{8}_\d{6}$")
LEDGER_BLOB = "qa_human_reviews_ledger.json"
LEDGER_MAX = 50


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_access_token(token: str | None) -> bool:
    expected = os.getenv("QA_REVIEW_TOKEN", "").strip()
    if not expected:
        return False
    return bool(token) and token.strip() == expected


def build_review_url(run_id: str) -> str | None:
    """Public review link for the QA dashboard email footer."""
    base = os.getenv("QA_REVIEW_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("QA_REVIEW_TOKEN", "").strip()
    if not base or not token or not run_id:
        return None
    return f"{base}/api/qa-review?run_id={run_id}&token={token}"


def _validate_run_id(run_id: str) -> bool:
    return bool(run_id and RUN_ID_PATTERN.match(run_id))


def load_review_context(run_id: str) -> dict | None:
    """Load scorecard + QA reports + any existing human review for a run."""
    if not _validate_run_id(run_id):
        return None

    telemetry = storage_client.load_state_blob(f"api_telemetry_{run_id}.json")
    qa_reports = storage_client.load_state_blob(f"qa_reports_{run_id}.json")
    existing = storage_client.load_state_blob(f"qa_human_review_{run_id}.json")

    if not telemetry and not qa_reports:
        return None

    scorecard = (telemetry or {}).get("QA_SCORECARD") if isinstance(telemetry, dict) else None
    if not scorecard and qa_reports:
        from src.qa.scorecard import build_qa_scorecard
        activity = (telemetry or {}).get("AGENT_ACTIVITY", {}) if isinstance(telemetry, dict) else {}
        scorecard = build_qa_scorecard(run_id, qa_reports, activity)

    prior = {}
    if isinstance(existing, dict):
        for row in existing.get("reviews") or []:
            key = row.get("agent_key") or row.get("agent_role")
            if key:
                prior[key] = row

    agents = []
    for row in (scorecard or {}).get("agents") or []:
        key = row.get("agent_key") or row.get("agent_role")
        merged = dict(row)
        if key in prior:
            merged["human_confirmed"] = prior[key].get("human_confirmed")
            merged["human_notes"] = prior[key].get("human_notes")
        agents.append(merged)

    return {
        "run_id": run_id,
        "scorecard": scorecard,
        "qa_reports": qa_reports or [],
        "existing_review": existing,
        "agents": agents,
    }


def _persist_local_ecosystem(record: dict) -> None:
    try:
        from tools.ecosystem_state import append_entry
        append_entry("qa_human_reviews", record)
    except Exception as e:
        logger.debug(f"Local ecosystem_state append skipped: {e}")


def _update_ledger(record: dict) -> None:
    ledger = storage_client.load_state_blob(LEDGER_BLOB) or {"reviews": []}
    if not isinstance(ledger, dict):
        ledger = {"reviews": []}
    entries = ledger.get("reviews") or []
    entries = [e for e in entries if e.get("run_id") != record.get("run_id")]
    entries.append(record)
    ledger["reviews"] = entries[-LEDGER_MAX:]
    ledger["last_updated"] = _utc_now()
    storage_client.save_state_blob(LEDGER_BLOB, ledger)


def save_human_review(run_id: str, reviews: list[dict], *, reviewer: str = "stan") -> dict:
    """Persist per-agent human confirmations for a run."""
    if not _validate_run_id(run_id):
        raise ValueError(f"Invalid run_id: {run_id!r}")

    cleaned = []
    for item in reviews:
        agent_key = item.get("agent_key")
        agent_role = item.get("agent_role", "")
        confirmed = item.get("human_confirmed")
        if confirmed is not None and isinstance(confirmed, str):
            if confirmed.lower() in ("true", "1", "yes"):
                confirmed = True
            elif confirmed.lower() in ("false", "0", "no"):
                confirmed = False
            else:
                confirmed = None
        notes = (item.get("human_notes") or "").strip() or None
        if confirmed is None and not notes:
            continue
        cleaned.append({
            "agent_key": agent_key,
            "agent_role": agent_role,
            "human_confirmed": confirmed,
            "human_notes": notes,
        })

    record = {
        "run_id": run_id,
        "reviewed_at": _utc_now(),
        "reviewer": reviewer,
        "reviews": cleaned,
        "summary": _summarize_reviews(cleaned),
        "evidence_ref": f"qa_human_review_{run_id}.json",
    }

    storage_client.save_state_blob(f"qa_human_review_{run_id}.json", record)
    _update_ledger(record)
    _persist_local_ecosystem(record)
    return record


def _summarize_reviews(reviews: list[dict]) -> str:
    confirmed = sum(1 for r in reviews if r.get("human_confirmed") is True)
    rejected = sum(1 for r in reviews if r.get("human_confirmed") is False)
    skipped = len(reviews) - confirmed - rejected
    return f"{confirmed} confirmed · {rejected} rejected · {skipped} notes-only/skipped"


def render_review_page(context: dict, *, error: str = None, success: str = None) -> str:
    """HTML review form — mobile-friendly, email-safe styling."""
    run_id = context["run_id"]
    agents = context.get("agents") or []
    rows_html = []

    for idx, agent in enumerate(agents):
        role = agent.get("agent_role", "Unknown")
        key = agent.get("agent_key") or role
        status = "PASS" if agent.get("is_compliant") else "FAIL"
        status_color = "#166534" if agent.get("is_compliant") else "#dc2626"
        crit = agent.get("critical_findings", 0)
        warn = agent.get("warning_findings", 0)
        prior = agent.get("human_confirmed")
        notes = html.escape(agent.get("human_notes") or "")
        checked_yes = "checked" if prior is True else ""
        checked_no = "checked" if prior is False else ""

        rows_html.append(f"""
        <div class="agent-card">
          <h3>{html.escape(role)}</h3>
          <p class="meta">Agent verdict: <strong style="color:{status_color}">{status}</strong>
             · {crit} CRITICAL · {warn} WARNING</p>
          <input type="hidden" name="agent_key_{idx}" value="{html.escape(str(key))}">
          <input type="hidden" name="agent_role_{idx}" value="{html.escape(role)}">
          <div class="choice">
            <label><input type="radio" name="human_confirmed_{idx}" value="true" {checked_yes}> ✅ Confirmed — verdict was correct</label>
            <label><input type="radio" name="human_confirmed_{idx}" value="false" {checked_no}> ❌ Rejected — false positive or missed issue</label>
            <label><input type="radio" name="human_confirmed_{idx}" value="" {"checked" if prior is None else ""}> Skip verdict (notes only)</label>
          </div>
          <label class="notes-label">Notes (optional)
            <textarea name="human_notes_{idx}" rows="2" placeholder="What was right or wrong?">{notes}</textarea>
          </label>
        </div>
        """)

    alert = ""
    if error:
        alert = f'<div class="alert error">{html.escape(error)}</div>'
    if success:
        alert = f'<div class="alert success">{html.escape(success)}</div>'

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QA Review — {html.escape(run_id)}</title>
<style>
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f3f4f6; margin: 0; padding: 16px; color: #1f2937; }}
  .container {{ max-width: 720px; margin: 0 auto; background: #fff; padding: 24px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }}
  h1 {{ font-size: 1.35rem; margin: 0 0 8px; }}
  .subtitle {{ color: #6b7280; font-size: 0.9rem; margin-bottom: 20px; }}
  .agent-card {{ border: 1px solid #e5e7eb; border-radius: 6px; padding: 16px; margin-bottom: 16px; }}
  .agent-card h3 {{ margin: 0 0 8px; font-size: 1.05rem; }}
  .meta {{ font-size: 0.85rem; color: #4b5563; margin: 0 0 12px; }}
  .choice label {{ display: block; margin: 8px 0; font-size: 0.95rem; cursor: pointer; }}
  .notes-label {{ display: block; font-size: 0.85rem; color: #4b5563; margin-top: 10px; }}
  textarea {{ width: 100%; box-sizing: border-box; margin-top: 6px; padding: 8px; border: 1px solid #d1d5db; border-radius: 4px; font-family: inherit; }}
  button {{ background: #2563eb; color: #fff; border: none; padding: 12px 24px; font-size: 1rem; border-radius: 6px; cursor: pointer; width: 100%; margin-top: 8px; }}
  button:hover {{ background: #1d4ed8; }}
  .alert {{ padding: 12px; border-radius: 6px; margin-bottom: 16px; }}
  .alert.error {{ background: #fee2e2; color: #991b1b; }}
  .alert.success {{ background: #dcfce7; color: #166534; }}
  .footer {{ text-align: center; font-size: 0.75rem; color: #9ca3af; margin-top: 24px; }}
</style>
</head>
<body>
<div class="container">
  <h1>QA Agent Review</h1>
  <p class="subtitle">Run <strong>{html.escape(run_id)}</strong> — confirm or reject each QA agent's overall verdict (2–5 min).</p>
  {alert}
  <form method="POST">
    <input type="hidden" name="agent_count" value="{len(agents)}">
    {''.join(rows_html)}
    <button type="submit">Save review</button>
  </form>
  <p class="footer">Invest AI Boardroom · human-confirmed QA scorecard</p>
</div>
</body></html>"""


def _parse_form_reviews(form: dict[str, str]) -> list[dict]:
    try:
        count = int(form.get("agent_count", "0"))
    except ValueError:
        count = 0
    reviews = []
    for idx in range(count):
        confirmed_raw = form.get(f"human_confirmed_{idx}", "")
        confirmed: bool | None
        if confirmed_raw == "true":
            confirmed = True
        elif confirmed_raw == "false":
            confirmed = False
        else:
            confirmed = None
        reviews.append({
            "agent_key": form.get(f"agent_key_{idx}", ""),
            "agent_role": form.get(f"agent_role_{idx}", ""),
            "human_confirmed": confirmed,
            "human_notes": form.get(f"human_notes_{idx}", ""),
        })
    return reviews


def handle_review_http(method: str, params: dict, body: bytes | None = None) -> tuple[int, str, dict[str, str]]:
    """Core handler for Azure HTTP / local tests. Returns (status, html, headers)."""
    token = params.get("token")
    if not validate_access_token(token):
        return 403, "<h1>403 Forbidden</h1><p>Invalid or missing review token.</p>", {"Content-Type": "text/html; charset=utf-8"}

    run_id = (params.get("run_id") or "").strip()
    if not _validate_run_id(run_id):
        return 400, "<h1>400 Bad Request</h1><p>Missing or invalid run_id.</p>", {"Content-Type": "text/html; charset=utf-8"}

    if method.upper() == "POST":
        form = _parse_urlencoded(body or b"")
        reviews = _parse_form_reviews(form)
        try:
            record = save_human_review(run_id, reviews)
            context = load_review_context(run_id) or {"run_id": run_id, "agents": []}
            msg = f"Saved — {record.get('summary', 'review recorded')}."
            return 200, render_review_page(context, success=msg), {"Content-Type": "text/html; charset=utf-8"}
        except Exception as e:
            logger.error(f"Failed to save human review for {run_id}: {e}")
            context = load_review_context(run_id) or {"run_id": run_id, "agents": []}
            return 500, render_review_page(context, error=str(e)), {"Content-Type": "text/html; charset=utf-8"}

    context = load_review_context(run_id)
    if not context:
        return 404, f"<h1>404 Not Found</h1><p>No QA data for run {html.escape(run_id)}.</p>", {"Content-Type": "text/html; charset=utf-8"}

    existing = context.get("existing_review")
    success = None
    if existing:
        success = f"Previously reviewed — {existing.get('summary', 'on file')}."
    return 200, render_review_page(context, success=success), {"Content-Type": "text/html; charset=utf-8"}


def _parse_urlencoded(body: bytes) -> dict[str, str]:
    from urllib.parse import parse_qs
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {k: (v[0] if v else "") for k, v in parsed.items()}


def handle_azure_request(req) -> Any:
    """Adapter for azure.functions.HttpRequest → HttpResponse."""
    import azure.functions as func

    method = req.method or "GET"
    params = dict(req.params) if req.params else {}
    body = req.get_body() if method.upper() == "POST" else None
    status, content, headers = handle_review_http(method, params, body)
    return func.HttpResponse(content, status_code=status, headers=headers)
