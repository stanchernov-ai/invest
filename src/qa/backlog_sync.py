"""Sync QA findings into docs/action_tracker.md — single backlog file.

Every CRITICAL/WARNING from a run is logged to Open items. Triage marks
fix target (code vs agent) or discard. Dedupes against existing rows.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.qa.candidate_triage import candidate_key, load_candidates
from src.qa.retrospective import _keywords, cross_check_backlog, default_action_tracker_path

logger = logging.getLogger(__name__)

RUN_ID_RE = re.compile(r"^\d{8}_\d{6}$")
OPEN_SECTION_MARKER = "### Open items (prioritized)"
SECTION_END_LINE_PREFIXES = (
    "**Done (now prod):**",
    "**Done (recent):**",
    "**HR / roster",
    "## Session Handoff",
)


def _find_section_end(section: str) -> int:
    """Byte offset within *section* where Open items content ends."""
    offset = 0
    lines = section.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        if idx == 0:
            offset += len(line)
            continue
        stripped = line.strip()
        if any(stripped.startswith(prefix) for prefix in SECTION_END_LINE_PREFIXES):
            return offset
        offset += len(line)
    return len(section)


def _extract_open_section(text: str) -> str:
    start = text.find(OPEN_SECTION_MARKER)
    if start < 0:
        return ""
    section = text[start:]
    return section[: _find_section_end(section)]

OLD_ROW_RE = re.compile(
    r"^\|\s*\*\*(P[0-3])\*\*\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$"
)
NEW_ROW_RE = re.compile(
    r"^\|\s*\*\*(P[0-3])\*\*\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$"
)
HEADER_ROW_RE = re.compile(r"^\|\s*Pri\s*\|")
SEPARATOR_ROW_RE = re.compile(r"^\|\s*-+\s*\|")

OPEN_ITEMS_PREAMBLE = """### Open items (prioritized)

*Every QA CRITICAL/WARNING is logged here. Run `tools/sync_backlog.py --run-id YYYYMMDD_HHMMSS` after fetch. **Fix:** `code` = real bug · `agent` = QA/prompt · `discard` = false positive.*

| Pri | ID | Status | Source | Fix | Item | Evidence |
|-----|-----|--------|--------|-----|------|----------|"""


def _strip_md(text: str) -> str:
    return re.sub(r"\*\*", "", text).strip()


def _normalize_status(raw: str) -> str:
    val = (raw or "open").lower().strip()
    if val in ("done", "shipped", "closed"):
        return "done"
    if val == "discard":
        return "discarded"
    return val if val in ("open", "discarded", "done") else "open"


def _normalize_fix(raw: str) -> str:
    val = (raw or "code").lower().strip()
    if val in ("promote", "pending", ""):
        return "code"
    if val in ("agent", "code", "discard"):
        return val
    return "code"


def parse_backlog_items(path: Path) -> list[dict[str, Any]]:
    """Parse Open items rows from action_tracker (old or new column layout)."""
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    section = _extract_open_section(text)
    if not section:
        return []

    items: list[dict] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or HEADER_ROW_RE.match(line) or SEPARATOR_ROW_RE.match(line):
            continue
        if "~~" in line.split("|", 2)[1]:
            continue

        new_match = NEW_ROW_RE.match(line)
        if new_match:
            items.append({
                "priority": new_match.group(1),
                "item_id": _strip_md(new_match.group(2)),
                "status": _normalize_status(new_match.group(3)),
                "source": _strip_md(new_match.group(4)),
                "fix": _normalize_fix(new_match.group(5)),
                "item": _strip_md(new_match.group(6)),
                "evidence": _strip_md(new_match.group(7)),
            })
            continue

        old_match = OLD_ROW_RE.match(line)
        if old_match:
            item_text = _strip_md(old_match.group(4))
            notes = _strip_md(old_match.group(5))
            combined = f"{item_text} — {notes}" if notes and notes.lower() not in item_text.lower() else item_text
            items.append({
                "priority": old_match.group(1),
                "item_id": _strip_md(old_match.group(2)),
                "status": "open",
                "source": "manual",
                "fix": "code",
                "item": combined,
                "evidence": notes if "qa_reports_" in notes or ".json" in notes else "",
            })
    return items


def _format_row(item: dict) -> str:
    pri = item.get("priority") or "P2"
    item_id = item.get("item_id") or "QA-UNKNOWN"
    status = item.get("status") or "open"
    source = item.get("source") or "QA"
    fix = item.get("fix") or "code"
    text = (item.get("item") or "").replace("|", "/")
    evidence = item.get("evidence") or ""
    return f"| **{pri}** | {item_id} | {status} | {source} | {fix} | {text} | {evidence} |"


def _next_qa_id(run_id: str, index: int) -> str:
    suffix = run_id[-6:] if len(run_id) >= 6 else run_id
    return f"QA-{suffix}-{index:02d}"


def _is_duplicate(candidate: dict, existing: list[dict]) -> bool:
    cand_keys = _keywords(
        (candidate.get("description") or "") + " " + (candidate.get("recommendation") or "")
    )
    for row in existing:
        if row.get("status") == "discarded":
            continue
        overlap = cand_keys & _keywords(row.get("item") or "")
        if len(overlap) >= 2:
            return True
    flags = cross_check_backlog([candidate], {"open": [
        {"priority": r.get("priority"), "text": r.get("item") or ""} for r in existing
    ], "done": []})
    return bool(flags)


def _load_triage_from_cache(cache_dir: Path, run_id: str) -> dict[str, dict]:
    path = cache_dir / "state" / f"candidate_triage_{run_id}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        row.get("candidate_key", ""): row
        for row in (data.get("items") or [])
        if row.get("candidate_key")
    }


def _triage_to_fix(disposition: str) -> tuple[str, str]:
    """Map triage disposition → (status, fix)."""
    disp = (disposition or "pending").lower()
    if disp == "discard":
        return "discarded", "discard"
    if disp == "agent":
        return "open", "agent"
    if disp in ("code", "promote"):
        return "open", "code"
    return "open", "code"


def merge_run_into_backlog(
    run_id: str,
    *,
    tracker_path: Path | None = None,
    cache_dir: Path | None = None,
    candidates: list[dict] | None = None,
) -> dict[str, Any]:
    """Add QA findings from a run into action_tracker Open items (deduped)."""
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"Invalid run_id: {run_id!r}")

    path = tracker_path or default_action_tracker_path()
    cache = cache_dir or Path(".cache")
    items = parse_backlog_items(path)
    triage_map = _load_triage_from_cache(cache, run_id)

    if candidates is None:
        from src import storage_client

        marker = storage_client.load_state_blob(f"retrospective_{run_id}.json")
        if marker and marker.get("candidates"):
            candidates = marker["candidates"]
        else:
            marker_path = cache / "state" / f"retrospective_{run_id}.json"
            if marker_path.exists():
                candidates = json.loads(marker_path.read_text(encoding="utf-8")).get("candidates") or []
            else:
                candidates = load_candidates(run_id)

    added = 0
    updated = 0
    skipped = 0
    qa_index = 1

    for cand in candidates or []:
        key = candidate_key(cand)
        triage = triage_map.get(key, {})
        disposition = triage.get("disposition", "pending")
        status, fix = _triage_to_fix(disposition)

        existing_row = next(
            (r for r in items if r.get("candidate_key") == key or r.get("item_id") == key),
            None,
        )
        if existing_row:
            if triage:
                existing_row["status"] = status
                existing_row["fix"] = fix
                if triage.get("notes"):
                    note = triage["notes"].strip()
                    if note and note not in (existing_row.get("item") or ""):
                        existing_row["item"] = f"{existing_row['item']} — {note}"
                updated += 1
            else:
                skipped += 1
            continue

        if status == "discarded" and not triage:
            skipped += 1
            continue

        if _is_duplicate(cand, items) and status != "discarded":
            skipped += 1
            continue

        desc = (cand.get("description") or "").strip()
        if triage.get("notes"):
            desc = f"{desc} — {triage['notes'].strip()}"

        items.append({
            "priority": cand.get("suggested_priority") or ("P1" if cand.get("severity") == "CRITICAL" else "P2"),
            "item_id": _next_qa_id(run_id, qa_index),
            "status": status,
            "source": cand.get("agent_role") or cand.get("source") or "QA",
            "fix": fix,
            "item": desc,
            "evidence": f"qa_reports_{run_id}.json",
            "candidate_key": key,
        })
        added += 1
        qa_index += 1

    write_backlog_items(path, items)
    return {"run_id": run_id, "added": added, "updated": updated, "skipped": skipped, "total": len(items)}


def write_backlog_items(path: Path, items: list[dict]) -> None:
    """Replace the Open items section in action_tracker.md."""
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8")
    start = text.find(OPEN_SECTION_MARKER)
    if start < 0:
        raise ValueError(f"{OPEN_SECTION_MARKER} not found in {path}")

    tail = text[start:]
    end_offset = _find_section_end(tail)

    open_rows = [r for r in items if r.get("status") != "done"]
    done_rows = [r for r in items if r.get("status") == "done"]

    body_lines = [OPEN_ITEMS_PREAMBLE, ""]
    for row in open_rows:
        body_lines.append(_format_row(row))
    if done_rows:
        body_lines.extend(["", "**Done (recent):**"])
        for row in done_rows:
            body_lines.append(_format_row(row))

    new_section = "\n".join(body_lines) + "\n\n"
    updated = text[:start] + new_section + tail[end_offset:].lstrip("\n")
    path.write_text(updated, encoding="utf-8")
    logger.info("[BACKLOG] Wrote %d open + %d done rows to %s.", len(open_rows), len(done_rows), path)
