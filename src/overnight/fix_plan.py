"""Parse and validate fix_plan.md (Architect artifact)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.overnight.constants import (
    DEFAULT_DENYLIST_GLOBS,
    DEFAULT_MAX_FILES_TOUCHED,
    VERDICT_BLOCKED,
    VERDICT_READY,
)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
IN_SCOPE_TABLE_RE = re.compile(
    r"###\s*In scope",
    re.IGNORECASE,
)
TABLE_ROW_RE = re.compile(r"^\|\s*`?([^|`]+?)`?\s*\|", re.MULTILINE)
TEST_COMMAND_RE = re.compile(
    r"##\s*Test commands.*?\n```(?:powershell|bash|sh)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
SUCCESS_CRITERIA_RE = re.compile(
    r"##\s*Success criteria\s*\n(.*?)(?:\n##|\Z)",
    re.DOTALL | re.IGNORECASE,
)
PYTHON_BLOCK_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)


@dataclass
class FixPlan:
    frontmatter: dict[str, Any]
    body: str
    in_scope_paths: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw = match.group(1)
    meta: dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if val.isdigit():
            meta[key] = int(val)
        elif val.lower() in ("true", "false"):
            meta[key] = val.lower() == "true"
        else:
            meta[key] = val
    body = text[match.end() :]
    return meta, body


def extract_in_scope_paths(body: str) -> list[str]:
    marker = "### In scope"
    idx = body.lower().find(marker.lower())
    if idx < 0:
        return []
    chunk = body[idx:]
    out_end = chunk.find("### Out of scope")
    if out_end > 0:
        chunk = chunk[:out_end]
    paths: list[str] = []
    for line in chunk.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.count("|") < 2:
            continue
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if not cells or cells[0].lower() in ("path", "------", "----"):
            continue
        path = cells[0].strip("`").strip().replace("\\", "/")
        if path.endswith(".py") or path.endswith(".md"):
            paths.append(path)
    return paths


def extract_test_commands(body: str) -> list[str]:
    match = TEST_COMMAND_RE.search(body)
    if not match:
        return []
    block = match.group(1)
    commands: list[str] = []
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        commands.append(line)
    return commands


def count_success_criteria(body: str) -> int:
    match = SUCCESS_CRITERIA_RE.search(body)
    if not match:
        return 0
    return len(re.findall(r"^\s*-\s*\[\s*[ xX]?\s*\]", match.group(1), re.MULTILINE))


def parse_fix_plan(path: Path) -> FixPlan:
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    return FixPlan(
        frontmatter=meta,
        body=body,
        in_scope_paths=extract_in_scope_paths(body),
        test_commands=extract_test_commands(body),
    )


def _path_denied(path: str, denylist: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    for denied in denylist:
        if normalized == denied or normalized.endswith("/" + denied):
            return True
    return False


def validate_fix_plan(
    plan: FixPlan,
    *,
    issue_id: str | None = None,
    denylist: tuple[str, ...] = DEFAULT_DENYLIST_GLOBS,
    max_files: int = DEFAULT_MAX_FILES_TOUCHED,
    requires_human_approval: bool = False,
    approved_by: str | None = None,
) -> tuple[bool, list[str]]:
    """Return (ok, errors). Deterministic — no LLM."""
    errors: list[str] = []
    fm = plan.frontmatter

    if fm.get("schema_version") != 1:
        errors.append("frontmatter.schema_version must be 1")

    if issue_id and fm.get("issue_id") and fm.get("issue_id") != issue_id:
        errors.append(f"frontmatter.issue_id {fm.get('issue_id')!r} != expected {issue_id!r}")

    for key in ("issue_id", "fix_type", "verdict"):
        if not fm.get(key):
            errors.append(f"frontmatter missing required key: {key}")

    verdict = str(fm.get("verdict", "")).upper()
    if verdict == VERDICT_BLOCKED:
        errors.append("verdict is BLOCKED — escalate to human")
    elif verdict != VERDICT_READY:
        errors.append(f"verdict must be READY (got {verdict!r})")

    fix_type = str(fm.get("fix_type", "")).lower()
    if fix_type == "agent" and requires_human_approval and not approved_by:
        errors.append("fix_type=agent requires manifest.approved_by before Developer runs")

    estimated = fm.get("estimated_files")
    if estimated is not None and int(estimated) > max_files:
        errors.append(f"estimated_files {estimated} exceeds max_files_touched {max_files}")

    if plan.in_scope_paths:
        if len(plan.in_scope_paths) > max_files:
            errors.append(f"in-scope table lists {len(plan.in_scope_paths)} files (max {max_files})")
        for path in plan.in_scope_paths:
            if _path_denied(path, denylist):
                errors.append(f"in-scope path on denylist: {path}")
    elif estimated is None:
        errors.append("no in-scope paths and no estimated_files in frontmatter")

    if count_success_criteria(plan.body) == 0:
        errors.append("Success criteria section has no checklist items")

    if not plan.test_commands:
        errors.append("Test commands section is empty")

    for block in PYTHON_BLOCK_RE.findall(plan.body):
        line_count = len([ln for ln in block.splitlines() if ln.strip()])
        if line_count > 15:
            errors.append(
                f"fix_plan contains {line_count}-line python block (max 15 — move implementation to Developer)"
            )

    return len(errors) == 0, errors
