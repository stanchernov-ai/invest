"""Post-deliver retrospective — candidate action items from QA + human review.

Runs automatically at the end of deliver (idempotent per run_id). Artifacts:
  - boardroom-state / retrospective_{run_id}.json
  - boardroom-reports / retrospective_{run_id}.md
  - boardroom-state / retrospectives_ledger.json (rolling, deduped by run_id)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from src import storage_client

logger = logging.getLogger(__name__)

RUN_ID_RE = re.compile(r"^\d{8}_\d{6}$")
OPEN_ITEM_RE = re.compile(r"^\|\s*\*\*(P[0-3])\*\*\s*\|\s*(.+?)\s*\|$")
DONE_ITEM_RE = re.compile(r"^\|\s*~~\*\*(P[0-3])\*\*~~\s*\|\s*(.+?)\s*\|$")
LEDGER_BLOB = "retrospectives_ledger.json"
LEDGER_MAX = 50
IN_PROGRESS_STALE_SECONDS = 300


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_action_tracker_path() -> Path:
    return _repo_root() / "docs" / "action_tracker.md"


def _marker_blob(run_id: str) -> str:
    return f"retrospective_{run_id}.json"


def _load_marker(run_id: str) -> dict | None:
    data = storage_client.load_state_blob(_marker_blob(run_id))
    return data if isinstance(data, dict) else None


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def should_skip_run(run_id: str, *, force: bool = False) -> dict | None:
    """Return existing marker if this run_id should not be reprocessed."""
    if force:
        return None
    marker = _load_marker(run_id)
    if not marker:
        return None
    if marker.get("status") == "completed":
        return marker
    if marker.get("status") == "in_progress":
        started = _parse_iso(marker.get("started_at"))
        if started:
            age = (datetime.now(timezone.utc) - started.astimezone(timezone.utc)).total_seconds()
            if age < IN_PROGRESS_STALE_SECONDS:
                return marker
    return None


def _claim_run(run_id: str) -> None:
    storage_client.save_state_blob(_marker_blob(run_id), {
        "run_id": run_id,
        "status": "in_progress",
        "started_at": _utc_now(),
    })


def parse_backlog(path: Path) -> dict[str, list[dict]]:
    open_items: list[dict] = []
    done_items: list[dict] = []
    if not path.exists():
        return {"open": open_items, "done": done_items}

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        done_match = DONE_ITEM_RE.match(line)
        if done_match:
            done_items.append({
                "priority": done_match.group(1),
                "text": _strip_md(done_match.group(2)),
            })
            continue
        open_match = OPEN_ITEM_RE.match(line)
        if open_match and "~~" not in line.split("|", 2)[1]:
            open_items.append({
                "priority": open_match.group(1),
                "text": _strip_md(open_match.group(2)),
            })
    return {"open": open_items, "done": done_items}


def _strip_md(text: str) -> str:
    return re.sub(r"\*\*", "", text).strip()


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z]{4,}", text.lower())
    stop = {"this", "that", "with", "from", "have", "been", "should", "must", "need"}
    return {w for w in words if w not in stop}


def collect_qa_findings(qa_reports: list[dict]) -> list[dict]:
    items: list[dict] = []
    for report in qa_reports or []:
        role = report.get("agent_role", "Unknown")
        for finding in report.get("findings") or []:
            sev = str(finding.get("severity", "INFO")).upper()
            if sev not in ("CRITICAL", "WARNING"):
                continue
            items.append({
                "source": "qa_report",
                "agent_role": role,
                "severity": sev,
                "category": finding.get("category", ""),
                "description": finding.get("description", ""),
                "recommendation": finding.get("recommendation", ""),
            })
    return items


def collect_human_review_items(human_review: dict | None) -> list[dict]:
    if not human_review:
        return []
    items: list[dict] = []
    for row in human_review.get("reviews") or []:
        notes = (row.get("human_notes") or "").strip()
        confirmed = row.get("human_confirmed")
        if confirmed is False:
            items.append({
                "source": "human_review",
                "severity": "HIGH",
                "agent_role": row.get("agent_role", ""),
                "description": f"Human rejected QA PASS: {notes or '(no notes)'}",
                "recommendation": "Investigate QA agent config or scope; add backlog item if valid.",
            })
        elif notes:
            items.append({
                "source": "human_review",
                "severity": "HIGH" if confirmed else "MEDIUM",
                "agent_role": row.get("agent_role", ""),
                "description": notes,
                "recommendation": "Promote to action_tracker if not already tracked.",
            })
    return items


def build_candidate_actions(
    qa_reports: list[dict],
    human_review: dict | None,
    scorecard: dict | None,
) -> list[dict]:
    seen: set[str] = set()
    candidates: list[dict] = []

    def add(item: dict) -> None:
        key = (item.get("description") or "")[:120].lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append(item)

    for item in collect_qa_findings(qa_reports):
        add({**item, "suggested_priority": "P1" if item["severity"] == "CRITICAL" else "P2"})

    for item in collect_human_review_items(human_review):
        add({**item, "suggested_priority": "P1" if item["severity"] == "HIGH" else "P2"})

    for agent in (scorecard or {}).get("agents") or []:
        if agent.get("is_compliant"):
            continue
        add({
            "source": "qa_scorecard",
            "severity": "MEDIUM",
            "agent_role": agent.get("agent_role", ""),
            "description": agent.get("summary") or (
                f"QA agent failed compliance ({agent.get('critical_findings', 0)} CRITICAL)."
            ),
            "recommendation": "Review qa_reports for this run; confirm via human review if unclear.",
            "suggested_priority": "P1" if agent.get("critical_findings") else "P2",
        })

    return candidates


def cross_check_backlog(candidates: list[dict], backlog: dict[str, list[dict]]) -> list[dict]:
    flags: list[dict] = []
    open_items = backlog.get("open") or []
    done_items = backlog.get("done") or []

    for cand in candidates:
        cand_keys = _keywords(
            (cand.get("description") or "") + " " + (cand.get("recommendation") or "")
        )
        for open_item in open_items:
            overlap = cand_keys & _keywords(open_item["text"])
            if len(overlap) >= 2:
                flags.append({
                    "type": "open_overlap",
                    "message": (
                        f"Finding may match open {open_item['priority']} backlog item: "
                        f"{open_item['text'][:100]}"
                    ),
                    "overlap": sorted(overlap),
                })
        for done_item in done_items:
            overlap = cand_keys & _keywords(done_item["text"])
            if len(overlap) >= 2:
                flags.append({
                    "type": "possible_regression",
                    "message": (
                        f"Finding overlaps DONE item — verify fix still holds or mark backlog stale: "
                        f"{done_item['text'][:100]}"
                    ),
                    "overlap": sorted(overlap),
                })

    for open_item in open_items:
        lower = open_item["text"].lower()
        if "pending deploy" in lower or "validate" in lower:
            flags.append({
                "type": "needs_validation",
                "message": f"Open item may need validation on this run: {open_item['text'][:120]}",
            })

    return flags


def render_markdown(
    run_id: str,
    run_status: dict | None,
    candidates: list[dict],
    flags: list[dict],
    backlog: dict[str, list[dict]],
    human_review: dict | None,
) -> str:
    lines = [
        f"# Post-Deliver Retrospective — `{run_id}`",
        "",
        f"Generated: {_utc_now()}",
        "",
        "## Run summary",
        "",
    ]

    if run_status:
        lines.append(f"- **Overall status:** {run_status.get('status', 'unknown')}")
        for phase in ("prepare", "debate", "deliver"):
            phase_info = run_status.get(phase) or {}
            if phase_info:
                dur = phase_info.get("duration_seconds")
                dur_s = f" ({dur}s)" if dur is not None else ""
                lines.append(f"- **{phase.title()}:** {phase_info.get('status', '?')}{dur_s}")
        if run_status.get("error"):
            lines.append(f"- **Error:** {run_status['error']}")
    else:
        lines.append("- Run status not available.")

    lines.extend(["", "## Human review", ""])
    if human_review:
        lines.append(f"- **Summary:** {human_review.get('summary', 'n/a')}")
        lines.append(f"- **Reviewed at:** {human_review.get('reviewed_at', 'n/a')}")
        for row in human_review.get("reviews") or []:
            if row.get("human_notes") or row.get("human_confirmed") is not None:
                conf = row.get("human_confirmed")
                label = "confirmed" if conf is True else "rejected" if conf is False else "skipped"
                lines.append(f"  - **{row.get('agent_role')}** ({label}): {row.get('human_notes') or ''}")
    else:
        lines.append("- No human review submitted yet — complete via QA dashboard link.")

    lines.extend(["", "## Candidate action items", ""])
    if not candidates:
        lines.append("_No CRITICAL/WARNING QA findings or human notes for this run._")
    else:
        lines.append(f"_See `docs/action_tracker.md` after `tools/sync_backlog.py --run-id {run_id}`._")
        lines.append("")

    lines.extend(["## Backlog cross-check", ""])
    open_items = backlog.get("open") or []
    if open_items:
        lines.append("### Open items (from action_tracker.md)")
        for item in open_items[:15]:
            lines.append(f"- **{item['priority']}:** {item['text']}")
    else:
        lines.append("_No open P0–P3 table rows parsed._")

    if flags:
        lines.extend(["", "### Flags", ""])
        for flag in flags:
            prefix = "⚠️" if flag["type"] == "possible_regression" else "📌"
            lines.append(f"- {prefix} **{flag['type']}:** {flag['message']}")
    else:
        lines.extend(["", "_No overlap flags between this run and backlog._"])

    lines.extend([
        "",
        "## Next steps",
        "",
        "1. Validate CRITICAL findings against raw debate log / briefing (don't trust QA blindly).",
        "2. Triage via QA dashboard link (fix code vs fix agent vs discard).",
        "3. Sync into the single backlog: `tools/sync_backlog.py --run-id {run_id}`.",
        "4. Add regression test or golden fixture when fixing code-enforced behavior.",
        "",
    ])
    return "\n".join(lines)


def _update_ledger(record: dict) -> None:
    ledger = storage_client.load_state_blob(LEDGER_BLOB) or {"runs": []}
    if not isinstance(ledger, dict):
        ledger = {"runs": []}
    runs = [r for r in (ledger.get("runs") or []) if r.get("run_id") != record.get("run_id")]
    runs.append(record)
    ledger["runs"] = runs[-LEDGER_MAX:]
    ledger["last_updated"] = _utc_now()
    storage_client.save_state_blob(LEDGER_BLOB, ledger)


def _append_local_insights(run_id: str, candidates: list[dict], flags: list[dict]) -> None:
    try:
        from tools.ecosystem_state import load_state, save_state
        state = load_state()
        existing_ids = {
            e.get("run_id")
            for e in (state.get("data_insights") or [])
            if isinstance(e, dict)
        }
        if run_id in existing_ids:
            return
        from tools.ecosystem_state import append_entry
        append_entry("data_insights", {
            "run_id": run_id,
            "phase": "post_deliver_retrospective",
            "candidate_action_count": len(candidates),
            "backlog_flag_count": len(flags),
            "candidate_actions": [
                {
                    "suggested_priority": c.get("suggested_priority"),
                    "source": c.get("source"),
                    "description": (c.get("description") or "")[:300],
                }
                for c in candidates[:20]
            ],
            "evidence_ref": f"retrospective_{run_id}.json",
        })
    except Exception as exc:
        logger.debug("Local ecosystem_state insights skipped: %s", exc)


def execute_retrospective(
    run_id: str,
    *,
    qa_reports: list[dict] | None = None,
    qa_scorecard: dict | None = None,
    action_tracker_path: Path | None = None,
    force: bool = False,
    write_local_insights: bool = True,
) -> dict:
    """Run retrospective for one deliver run. Idempotent unless force=True."""
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"Invalid run_id: {run_id!r}")

    existing = should_skip_run(run_id, force=force)
    if existing:
        logger.info("[RETROSPECTIVE] Skipping run %s — already %s.", run_id, existing.get("status"))
        return {
            "run_id": run_id,
            "status": "skipped",
            "reason": existing.get("status"),
            "processed_at": existing.get("processed_at") or existing.get("started_at"),
            "candidate_count": existing.get("candidate_count", 0),
            "flag_count": existing.get("flag_count", 0),
            "markdown_blob": existing.get("markdown_blob"),
        }

    _claim_run(run_id)

    if qa_reports is None:
        qa_reports = storage_client.load_state_blob(f"qa_reports_{run_id}.json")
    if qa_reports is None:
        storage_client.save_state_blob(_marker_blob(run_id), {
            "run_id": run_id,
            "status": "failed",
            "failed_at": _utc_now(),
            "error": f"missing qa_reports_{run_id}.json",
        })
        raise FileNotFoundError(f"No qa_reports_{run_id}.json")

    human_review = storage_client.load_state_blob(f"qa_human_review_{run_id}.json")
    if qa_scorecard is None:
        telemetry = storage_client.load_state_blob(f"api_telemetry_{run_id}.json")
        qa_scorecard = (telemetry or {}).get("QA_SCORECARD") if isinstance(telemetry, dict) else None

    run_status = storage_client.load_run_status()
    tracker_path = action_tracker_path or default_action_tracker_path()
    backlog = parse_backlog(tracker_path)
    candidates = build_candidate_actions(
        qa_reports if isinstance(qa_reports, list) else [],
        human_review if isinstance(human_review, dict) else None,
        qa_scorecard,
    )
    flags = cross_check_backlog(candidates, backlog)
    markdown = render_markdown(
        run_id, run_status, candidates, flags, backlog,
        human_review if isinstance(human_review, dict) else None,
    )

    md_blob = f"retrospective_{run_id}.md"
    storage_client.save_report(md_blob, markdown)

    completed = {
        "run_id": run_id,
        "status": "completed",
        "started_at": _load_marker(run_id).get("started_at") if _load_marker(run_id) else _utc_now(),
        "processed_at": _utc_now(),
        "candidate_count": len(candidates),
        "flag_count": len(flags),
        "markdown_blob": md_blob,
        "candidates": candidates[:25],
        "flags": flags[:25],
        "evidence_ref": f"qa_reports_{run_id}.json",
    }
    storage_client.save_state_blob(_marker_blob(run_id), completed)
    _update_ledger({
        "run_id": run_id,
        "processed_at": completed["processed_at"],
        "candidate_count": len(candidates),
        "flag_count": len(flags),
        "markdown_blob": md_blob,
    })

    if write_local_insights:
        _append_local_insights(run_id, candidates, flags)

    logger.info(
        "[RETROSPECTIVE] Completed for %s — %d candidates, %d flags.",
        run_id, len(candidates), len(flags),
    )
    return {
        "run_id": run_id,
        "status": "completed",
        "candidate_count": len(candidates),
        "flag_count": len(flags),
        "markdown_blob": md_blob,
    }
