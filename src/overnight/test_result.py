"""Execute test commands from fix_plan and emit test_result.json."""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.overnight.constants import DEFAULT_DENYLIST_GLOBS, SCHEMA_VERSION
from src.overnight.fix_plan import FixPlan
from src.overnight.paths import iteration_dir, test_result_path

FAILURE_RE = re.compile(
    r"^(FAIL|ERROR):\s*(.+?)\s*\((.+?)\)$",
    re.MULTILINE,
)
TRACEBACK_MARKER = "Traceback (most recent call last):"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_head(repo: Path) -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip()


def _git_changed_files(repo: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    return [ln.strip().replace("\\", "/") for ln in (proc.stdout or "").splitlines() if ln.strip()]


def _policy_violations(
    changed_files: list[str],
    denylist: tuple[str, ...] = DEFAULT_DENYLIST_GLOBS,
) -> list[str]:
    violations: list[str] = []
    for path in changed_files:
        normalized = path.replace("\\", "/")
        for denied in denylist:
            if normalized == denied:
                violations.append(f"edited {path} — denylist")
    return violations


def _parse_unittest_failures(output: str) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for match in FAILURE_RE.finditer(output):
        status, err_msg, test_id = match.groups()
        failures.append({
            "test_id": test_id.strip(),
            "message": err_msg.strip(),
            "file": test_id.split(".")[0].replace(".", "/") + ".py" if "." in test_id else "",
            "line": None,
            "traceback_tail": _tail_traceback(output, test_id),
        })
    return failures


def _tail_traceback(output: str, test_id: str, max_lines: int = 20) -> str:
    idx = output.find(test_id)
    if idx < 0:
        return ""
    chunk = output[idx:]
    tb_idx = chunk.rfind(TRACEBACK_MARKER)
    if tb_idx >= 0:
        chunk = chunk[tb_idx:]
    lines = chunk.splitlines()[:max_lines]
    return "\n".join(lines)


def _count_tests(output: str) -> tuple[int, int, int]:
    ran = re.search(r"Ran\s+(\d+)\s+tests?", output)
    errors = re.search(r"errors=(\d+)", output)
    failures = re.search(r"failures=(\d+)", output)
    skipped = re.search(r"skipped=(\d+)", output)
    total = int(ran.group(1)) if ran else 0
    fail_count = int(failures.group(1)) if failures else 0
    err_count = int(errors.group(1)) if errors else 0
    skip_count = int(skipped.group(1)) if skipped else 0
    failed = fail_count + err_count
    passed = max(0, total - failed - skip_count)
    return passed, failed, skip_count


def run_command(command: str, *, cwd: Path | None = None) -> dict[str, Any]:
    root = cwd or _repo_root()
    start = time.perf_counter()
    proc = subprocess.run(
        command,
        cwd=root,
        shell=True,
        capture_output=True,
        text=True,
    )
    duration_ms = int((time.perf_counter() - start) * 1000)
    output = (proc.stdout or "") + (proc.stderr or "")
    passed, failed, skipped = _count_tests(output)
    suite: dict[str, Any] = {
        "name": "unittest" if "unittest" in command else "shell",
        "command": command,
        "exit_code": proc.returncode,
        "duration_ms": duration_ms,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "failures": _parse_unittest_failures(output) if proc.returncode != 0 else [],
    }
    if proc.returncode == 0 and "pre_commit" in command:
        suite["name"] = "pre_commit"
        suite["verdict"] = "PASS"
    return suite


def run_test_suite(
    issue_id: str,
    plan: FixPlan,
    iteration: int,
    *,
    repo_root: Path | None = None,
    denylist: tuple[str, ...] = DEFAULT_DENYLIST_GLOBS,
) -> dict[str, Any]:
    root = repo_root or _repo_root()
    suites: list[dict[str, Any]] = []
    for cmd in plan.test_commands:
        suites.append(run_command(cmd, cwd=root))

    changed = _git_changed_files(root)
    violations = _policy_violations(changed, denylist)

    any_fail = any(s["exit_code"] != 0 for s in suites)
    if violations:
        verdict = "BLOCK"
    elif any_fail:
        verdict = "FAIL"
    else:
        verdict = "PASS"

    hints: list[str] = []
    for suite in suites:
        for failure in suite.get("failures") or []:
            hints.append(
                f"Fix {failure.get('test_id')}: {failure.get('message', '')[:120]}"
            )
    for violation in violations:
        hints.append(violation)

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "issue_id": issue_id,
        "iteration": iteration,
        "generated_at": _utc_now(),
        "git": {
            "branch": None,
            "head_sha": _git_head(root),
            "files_changed": changed,
        },
        "verdict": verdict,
        "summary": _build_summary(verdict, suites, violations),
        "suites": suites,
        "policy_violations": violations,
        "next_developer_hints": hints[:10],
    }

    out_dir = iteration_dir(issue_id, iteration)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = test_result_path(issue_id, iteration)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def _build_summary(verdict: str, suites: list[dict], violations: list[str]) -> str:
    if verdict == "BLOCK":
        return f"Policy block: {violations[0]}"
    if verdict == "PASS":
        names = ", ".join(s["name"] for s in suites)
        return f"All suites passed ({names})"
    failed = sum(s.get("failed", 0) for s in suites)
    return f"{failed} test failure(s) across {len(suites)} suite(s)"
