#!/usr/bin/env python3
"""Sync Azure run artifacts from local .cache into ecosystem_state.json.

Called by fetch_azure_reports --sync-ecosystem and post_job_sync.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID_RE = re.compile(r"^\d{8}_\d{6}$")


def _run_id_present(bucket: list, run_id: str) -> bool:
    return any(isinstance(e, dict) and e.get("run_id") == run_id for e in bucket)


def sync_ecosystem_from_cache(
    run_id: str,
    cache_dir: Path | str = ".cache",
    *,
    phase: str = "post_job",
) -> dict[str, bool]:
    """Idempotently append qa_scorecards, data_insights, qa_human_reviews for run_id."""
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"Invalid run_id: {run_id!r}")

    cache = Path(cache_dir)
    if not cache.is_absolute():
        cache = REPO_ROOT / cache

    from tools.ecosystem_state import append_entry, load_state

    state = load_state()
    synced: dict[str, bool] = {
        "qa_scorecards": False,
        "data_insights": False,
        "qa_human_reviews": False,
    }

    telemetry_path = cache / "state" / f"api_telemetry_{run_id}.json"
    if telemetry_path.exists() and not _run_id_present(state.get("qa_scorecards", []), run_id):
        telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
        scorecard = telemetry.get("QA_SCORECARD")
        if scorecard:
            append_entry("qa_scorecards", {
                "phase": phase,
                "run_id": run_id,
                "summary": scorecard.get("summary"),
                "agents": scorecard.get("agents"),
                "totals": scorecard.get("totals"),
                "evidence_ref": f"api_telemetry_{run_id}.json → QA_SCORECARD",
            })
            synced["qa_scorecards"] = True

    retro_path = cache / "state" / f"retrospective_{run_id}.json"
    if retro_path.exists() and not _run_id_present(state.get("data_insights", []), run_id):
        marker = json.loads(retro_path.read_text(encoding="utf-8"))
        candidates = marker.get("candidates") or marker.get("candidate_actions") or []
        flags = marker.get("flags") or marker.get("backlog_flags") or []
        append_entry("data_insights", {
            "run_id": run_id,
            "phase": "post_deliver_retrospective",
            "candidate_action_count": marker.get("candidate_count", len(candidates)),
            "backlog_flag_count": marker.get("flag_count", len(flags)),
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
        synced["data_insights"] = True

    review_path = cache / "state" / f"qa_human_review_{run_id}.json"
    if review_path.exists() and not _run_id_present(state.get("qa_human_reviews", []), run_id):
        review = json.loads(review_path.read_text(encoding="utf-8"))
        append_entry("qa_human_reviews", {
            "phase": phase,
            "run_id": run_id,
            "reviewed_at": review.get("reviewed_at"),
            "reviewer": review.get("reviewer"),
            "summary": review.get("summary"),
            "reviews": review.get("reviews"),
            "evidence_ref": f"qa_human_review_{run_id}.json",
        })
        synced["qa_human_reviews"] = True

    return synced
