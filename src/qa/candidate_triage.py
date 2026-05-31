"""Human triage of retrospective candidate actions — promote or discard for backlog.

Persisted to:
  - boardroom-state / candidate_triage_{run_id}.json
  - boardroom-state / candidate_triages_ledger.json
  - .cursor/agent_state/ecosystem_state.json → candidate_triages[] (when writable)

Interactive UI is embedded on the /api/qa-review page (#candidates anchor).
The QA dashboard email shows a read-only preview + link to that form.
"""
from __future__ import annotations

import hashlib
import html
import logging
import re
from datetime import datetime, timezone
from typing import Any

from src import storage_client

logger = logging.getLogger(__name__)

RUN_ID_PATTERN = re.compile(r"^\d{8}_\d{6}$")
LEDGER_BLOB = "candidate_triages_ledger.json"
LEDGER_MAX = 50
VALID_DISPOSITIONS = frozenset({"promote", "discard", "pending"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def candidate_key(cand: dict) -> str:
    """Stable id for a candidate — survives retrospective refresh."""
    payload = "|".join([
        str(cand.get("source") or ""),
        str(cand.get("agent_role") or ""),
        (cand.get("description") or "")[:120],
    ])
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _validate_run_id(run_id: str) -> bool:
    return bool(run_id and RUN_ID_PATTERN.match(run_id))


def load_candidates(run_id: str) -> list[dict]:
    """Load candidate actions from retrospective marker or rebuild from QA artifacts."""
    marker = storage_client.load_state_blob(f"retrospective_{run_id}.json")
    if isinstance(marker, dict) and marker.get("candidates"):
        return list(marker["candidates"])

    qa_reports = storage_client.load_state_blob(f"qa_reports_{run_id}.json")
    if not qa_reports:
        return []

    human_review = storage_client.load_state_blob(f"qa_human_review_{run_id}.json")
    telemetry = storage_client.load_state_blob(f"api_telemetry_{run_id}.json")
    qa_scorecard = (telemetry or {}).get("QA_SCORECARD") if isinstance(telemetry, dict) else None
    if not qa_scorecard:
        from src.qa.scorecard import build_qa_scorecard

        activity = (telemetry or {}).get("AGENT_ACTIVITY", {}) if isinstance(telemetry, dict) else {}
        qa_scorecard = build_qa_scorecard(run_id, qa_reports, activity)

    from src.qa.retrospective import build_candidate_actions

    return build_candidate_actions(
        qa_reports if isinstance(qa_reports, list) else [],
        human_review if isinstance(human_review, dict) else None,
        qa_scorecard,
    )


def load_triage_context(run_id: str) -> dict[str, Any]:
    """Candidates merged with any saved triage decisions."""
    candidates = load_candidates(run_id)
    existing = storage_client.load_state_blob(f"candidate_triage_{run_id}.json")
    prior: dict[str, dict] = {}
    if isinstance(existing, dict):
        for row in existing.get("items") or []:
            key = row.get("candidate_key")
            if key:
                prior[key] = row

    merged: list[dict] = []
    for cand in candidates:
        key = candidate_key(cand)
        saved = prior.get(key, {})
        merged.append({
            **cand,
            "candidate_key": key,
            "disposition": saved.get("disposition") or "pending",
            "triage_notes": saved.get("notes") or "",
        })

    return {
        "run_id": run_id,
        "candidates": merged,
        "existing_triage": existing if isinstance(existing, dict) else None,
    }


def _summarize_items(items: list[dict]) -> str:
    promoted = sum(1 for i in items if i.get("disposition") == "promote")
    discarded = sum(1 for i in items if i.get("disposition") == "discard")
    pending = sum(1 for i in items if i.get("disposition") not in ("promote", "discard"))
    return f"{promoted} promoted · {discarded} discarded · {pending} pending"


def save_candidate_triage(run_id: str, items: list[dict], *, reviewer: str = "stan") -> dict:
    """Persist promote/discard decisions for a run."""
    if not _validate_run_id(run_id):
        raise ValueError(f"Invalid run_id: {run_id!r}")

    cleaned: list[dict] = []
    for item in items:
        disposition = (item.get("disposition") or "pending").lower()
        if disposition not in VALID_DISPOSITIONS:
            disposition = "pending"
        notes = (item.get("notes") or "").strip() or None
        if disposition == "pending" and not notes:
            continue
        cleaned.append({
            "candidate_key": item.get("candidate_key") or "",
            "disposition": disposition,
            "notes": notes,
            "description": (item.get("description") or "")[:300],
            "suggested_priority": item.get("suggested_priority"),
            "agent_role": item.get("agent_role"),
            "severity": item.get("severity"),
            "source": item.get("source"),
        })

    record = {
        "run_id": run_id,
        "reviewed_at": _utc_now(),
        "reviewer": reviewer,
        "items": cleaned,
        "summary": _summarize_items(cleaned),
        "promoted_count": sum(1 for i in cleaned if i.get("disposition") == "promote"),
        "discarded_count": sum(1 for i in cleaned if i.get("disposition") == "discard"),
        "evidence_ref": f"candidate_triage_{run_id}.json",
    }
    storage_client.save_state_blob(f"candidate_triage_{run_id}.json", record)
    _update_ledger(record)
    _persist_local_ecosystem(record)
    return record


def _update_ledger(record: dict) -> None:
    ledger = storage_client.load_state_blob(LEDGER_BLOB) or {"triages": []}
    if not isinstance(ledger, dict):
        ledger = {"triages": []}
    entries = [e for e in (ledger.get("triages") or []) if e.get("run_id") != record.get("run_id")]
    entries.append(record)
    ledger["triages"] = entries[-LEDGER_MAX:]
    ledger["last_updated"] = _utc_now()
    storage_client.save_state_blob(LEDGER_BLOB, ledger)


def _persist_local_ecosystem(record: dict) -> None:
    try:
        from tools.ecosystem_state import append_entry

        append_entry("candidate_triages", record)
    except Exception as exc:
        logger.debug("Local ecosystem_state candidate_triages append skipped: %s", exc)


def parse_triage_from_form(form: dict[str, str]) -> list[dict]:
    try:
        count = int(form.get("candidate_count", "0"))
    except ValueError:
        count = 0
    items: list[dict] = []
    for idx in range(count):
        disposition = (form.get(f"disposition_{idx}") or "pending").lower()
        if disposition not in VALID_DISPOSITIONS:
            disposition = "pending"
        items.append({
            "candidate_key": form.get(f"candidate_key_{idx}", ""),
            "disposition": disposition,
            "notes": form.get(f"triage_notes_{idx}", ""),
            "description": form.get(f"candidate_description_{idx}", ""),
            "suggested_priority": form.get(f"candidate_priority_{idx}", ""),
            "agent_role": form.get(f"candidate_agent_role_{idx}", ""),
            "severity": form.get(f"candidate_severity_{idx}", ""),
            "source": form.get(f"candidate_source_{idx}", ""),
        })
    return items


def format_promoted_markdown(run_id: str, items: list[dict]) -> str:
    """Markdown table rows ready to paste into action_tracker Open items."""
    promoted = [i for i in items if i.get("disposition") == "promote"]
    if not promoted:
        return ""
    lines = ["", "### Promoted from candidate triage (paste into Open items)", ""]
    for item in promoted:
        pri = item.get("suggested_priority") or "P2"
        desc = (item.get("description") or "").strip()
        notes = (item.get("notes") or "").strip()
        text = desc if not notes else f"{desc} — {notes}"
        lines.append(f"| **{pri}** | {text} | evidence: qa_reports_{run_id}.json |")
    return "\n".join(lines)


def render_triage_section_html(context: dict[str, Any]) -> str:
    """Interactive candidate triage block for the qa-review page."""
    run_id = context["run_id"]
    candidates = context.get("candidates") or []
    if not candidates:
        return f"""
        <section id="candidates" class="candidate-section">
          <h2>Candidate Action Items</h2>
          <p class="meta">No CRITICAL/WARNING findings to triage for this run.</p>
        </section>"""

    rows: list[str] = []
    for idx, cand in enumerate(candidates):
        key = cand.get("candidate_key") or candidate_key(cand)
        pri = html.escape(str(cand.get("suggested_priority") or "P2"))
        sev = html.escape(str(cand.get("severity") or ""))
        role = html.escape(str(cand.get("agent_role") or "General"))
        source = html.escape(str(cand.get("source") or ""))
        desc = html.escape(str(cand.get("description") or ""))
        rec = html.escape(str(cand.get("recommendation") or ""))
        notes = html.escape(str(cand.get("triage_notes") or ""))
        disp = cand.get("disposition") or "pending"
        checked_promote = "checked" if disp == "promote" else ""
        checked_discard = "checked" if disp == "discard" else ""
        checked_pending = "checked" if disp not in ("promote", "discard") else ""

        rec_html = f'<p class="rec"><em>{rec}</em></p>' if rec else ""
        rows.append(f"""
        <div class="candidate-card">
          <div class="candidate-head">
            <span class="pri">{pri}</span>
            <span class="sev sev-{sev}">{sev}</span>
            <strong>{role}</strong>
            <span class="source">({source})</span>
          </div>
          <p class="desc">{desc}</p>
          {rec_html}
          <input type="hidden" name="candidate_key_{idx}" value="{html.escape(key)}">
          <input type="hidden" name="candidate_description_{idx}" value="{desc}">
          <input type="hidden" name="candidate_priority_{idx}" value="{pri}">
          <input type="hidden" name="candidate_agent_role_{idx}" value="{role}">
          <input type="hidden" name="candidate_severity_{idx}" value="{sev}">
          <input type="hidden" name="candidate_source_{idx}" value="{source}">
          <div class="choice">
            <label><input type="radio" name="disposition_{idx}" value="promote" {checked_promote}> ✅ Add to backlog</label>
            <label><input type="radio" name="disposition_{idx}" value="discard" {checked_discard}> 🗑 Discard (false positive / won't fix)</label>
            <label><input type="radio" name="disposition_{idx}" value="pending" {checked_pending}> ⏸ Leave pending</label>
          </div>
          <label class="notes-label">Notes (optional)
            <textarea name="triage_notes_{idx}" rows="2" placeholder="Why promote or discard?">{notes}</textarea>
          </label>
        </div>""")

    existing = context.get("existing_triage")
    prior_note = ""
    if existing:
        prior_note = f'<p class="meta">Previously saved — {html.escape(existing.get("summary", "on file"))}.</p>'

    return f"""
    <section id="candidates" class="candidate-section">
      <h2>Candidate Action Items</h2>
      <p class="subtitle">Run <strong>{html.escape(run_id)}</strong> — select items to add to the backlog or discard.</p>
      {prior_note}
      <input type="hidden" name="candidate_count" value="{len(candidates)}">
      {''.join(rows)}
    </section>"""


def render_dashboard_candidates_html(
    candidates: list[dict] | None,
    *,
    triage_url: str | None = None,
) -> str:
    """Read-only candidate preview for the emailed QA dashboard."""
    items = candidates or []
    if not items:
        body = '<p style="color: #6b7280; font-style: italic;">No CRITICAL/WARNING findings to triage for this run.</p>'
    else:
        rows: list[str] = []
        for idx, cand in enumerate(items, 1):
            pri = html.escape(str(cand.get("suggested_priority") or "P2"))
            sev = html.escape(str(cand.get("severity") or ""))
            role = html.escape(str(cand.get("agent_role") or "General"))
            desc = html.escape(str(cand.get("description") or ""))[:220]
            if len(cand.get("description") or "") > 220:
                desc += "…"
            rows.append(f"""
            <tr>
                <td>{idx}</td>
                <td class="sev-{sev}">{sev}</td>
                <td>{pri}</td>
                <td>{role}</td>
                <td>{desc}</td>
                <td><span class="pending-badge">Pending</span></td>
            </tr>""")
        body = f"""
            <table class="candidate-table">
                <tr>
                    <th width="4%">#</th>
                    <th width="10%">Severity</th>
                    <th width="8%">Pri</th>
                    <th width="18%">Agent</th>
                    <th width="50%">Finding</th>
                    <th width="10%">Status</th>
                </tr>
                {''.join(rows)}
            </table>"""

    triage_link = ""
    if triage_url:
        triage_link = f"""
                <p style="margin: 16px 0;">
                    <a href="{html.escape(triage_url)}" class="review-btn">Triage candidates (add / discard)</a>
                </p>
                <p style="font-size: 0.85em;">Select which items to promote to the backlog and which to discard (2–5 min).</p>"""

    return f"""
            <div class="candidate-preview">
                <h2>Candidate Action Items</h2>
                <p class="candidate-intro">Post-deliver retrospective findings — triage before adding to Open items.</p>
                {body}
                {triage_link}
            </div>"""
