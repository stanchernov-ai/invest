"""Deterministic ROI scoring for action_tracker Open items."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.overnight.constants import FINANCIAL_KEYWORDS
from src.qa.backlog_sync import parse_backlog_items, default_action_tracker_path

PRIORITY_SCORE = {"P0": 40, "P1": 30, "P2": 20, "P3": 10}
FIX_SCORE = {"code": 50, "agent": 15, "discard": -1000}
STATUS_SKIP = frozenset({"done", "discarded"})

EFFORT_S_HINTS = (
    "footer",
    "css",
    "palette",
    "html",
    "typo",
    "single file",
    "reporting.py",
    "briefing_style",
)
EFFORT_L_HINTS = (
    "refactor",
    "multi-tenant",
    "postgres",
    "orchestrat",
    "vote_engine",
    "migration",
    "framework",
)


def _effort_multiplier(item_text: str) -> float:
    lower = item_text.lower()
    if any(h in lower for h in EFFORT_L_HINTS):
        return 0.4
    if any(h in lower for h in EFFORT_S_HINTS):
        return 1.2
    return 1.0


def _financial_penalty(item_text: str) -> float:
    lower = item_text.lower()
    if any(kw in lower for kw in FINANCIAL_KEYWORDS):
        return 0.0
    return 1.0


def _evidence_bonus(evidence: str) -> float:
    if "qa_reports_" in evidence and evidence.endswith(".json"):
        return 1.1
    return 1.0


def score_item(item: dict[str, Any]) -> float:
    if item.get("status") in STATUS_SKIP:
        return -1.0
    if item.get("fix") == "discard":
        return -1.0

    pri = PRIORITY_SCORE.get(str(item.get("priority", "P2")).upper(), 15)
    fix = FIX_SCORE.get(str(item.get("fix", "code")).lower(), 10)
    text = f"{item.get('item') or ''} {item.get('evidence') or ''}"
    base = (pri + fix) * _effort_multiplier(text) * _financial_penalty(text)
    return round(base * _evidence_bonus(item.get("evidence") or ""), 2)


def rank_open_items(
    tracker_path: Path | None = None,
    *,
    fix_type: str | None = "code",
    limit: int = 10,
) -> list[dict[str, Any]]:
    path = tracker_path or default_action_tracker_path()
    items = parse_backlog_items(path)
    ranked: list[dict[str, Any]] = []
    for item in items:
        if item.get("status") in STATUS_SKIP:
            continue
        if fix_type and item.get("fix") != fix_type:
            continue
        roi = score_item(item)
        if roi < 0:
            continue
        ranked.append({**item, "roi_score": roi})
    ranked.sort(key=lambda row: (-row["roi_score"], row.get("priority", "P9"), row.get("item_id", "")))
    return ranked[:limit]
