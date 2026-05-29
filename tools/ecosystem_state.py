#!/usr/bin/env python3
"""Append structured entries to .cursor/agent_state/ecosystem_state.json.

Usage (from repo root):
  .venv\\Scripts\\python.exe tools/ecosystem_state.py append qa_flags --data '{"verdict":"PASS"}'
  .venv\\Scripts\\python.exe tools/ecosystem_state.py append api_audit --file finding.json
  .venv\\Scripts\\python.exe tools/ecosystem_state.py show qa_flags --last 5
  .venv\\Scripts\\python.exe tools/ecosystem_state.py show --last 3
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".cursor" / "agent_state" / "ecosystem_state.json"
ARCHIVE_DIR = ROOT / ".cursor" / "agent_state" / "ecosystem_state_archive"

ARRAY_KEYS = (
    "conflicts",
    "sub_agent_runs",
    "qa_flags",
    "api_audit",
    "data_insights",
    "supervisor_summaries",
    "qa_scorecards",
    "qa_human_reviews",
)
MAX_ENTRIES = 50


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_state() -> dict:
    return {
        "version": 1,
        "last_updated": None,
        **{key: [] for key in ARRAY_KEYS},
    }


def load_state() -> dict:
    if not STATE_PATH.exists():
        return _default_state()
    with STATE_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    for key in ARRAY_KEYS:
        data.setdefault(key, [])
    data.setdefault("version", 1)
    return data


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = _utc_now()
    with STATE_PATH.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")


def _rotate(category: str, items: list) -> list:
    if len(items) <= MAX_ENTRIES:
        return items
    overflow = items[: len(items) - MAX_ENTRIES]
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = ARCHIVE_DIR / f"{category}_{stamp}.json"
    with archive_path.open("w", encoding="utf-8") as fh:
        json.dump(overflow, fh, indent=2)
        fh.write("\n")
    return items[-MAX_ENTRIES:]


def append_entry(category: str, entry: dict) -> dict:
    if category not in ARRAY_KEYS:
        raise ValueError(f"Unknown category {category!r}. Choose one of: {', '.join(ARRAY_KEYS)}")

    state = load_state()
    record = {"recorded_at": _utc_now(), **entry}
    bucket = state[category]
    bucket.append(record)
    state[category] = _rotate(category, bucket)
    save_state(state)
    return record


def cmd_append(args: argparse.Namespace) -> int:
    if args.data and args.file:
        print("Use only one of --data or --file.", file=sys.stderr)
        return 2

    if args.file:
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    elif args.data:
        payload = json.loads(args.data)
    else:
        payload = {}

    if args.agent:
        payload.setdefault("agent", args.agent)
    if args.phase:
        payload.setdefault("phase", args.phase)

    record = append_entry(args.category, payload)
    print(json.dumps(record, indent=2))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    state = load_state()
    if args.category:
        items = state.get(args.category, [])
        excerpt = {args.category: items[-args.last :]}
    else:
        excerpt = {
            "last_updated": state.get("last_updated"),
            **{key: state.get(key, [])[-args.last :] for key in ARRAY_KEYS},
        }
    print(json.dumps(excerpt, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage ecosystem_state.json entries.")
    sub = parser.add_subparsers(dest="command", required=True)

    append_p = sub.add_parser("append", help="Append one structured record.")
    append_p.add_argument("category", choices=ARRAY_KEYS)
    append_p.add_argument("--data", help="JSON object string.")
    append_p.add_argument("--file", help="Path to a JSON object file.")
    append_p.add_argument("--agent", help="Optional agent name tag.")
    append_p.add_argument("--phase", help="Optional phase tag (pre_commit, pre_push, post_job, daily).")
    append_p.set_defaults(func=cmd_append)

    show_p = sub.add_parser("show", help="Print recent records.")
    show_p.add_argument("category", nargs="?", choices=ARRAY_KEYS, help="Optional category filter.")
    show_p.add_argument("--last", type=int, default=5, help="Number of recent records (default 5).")
    show_p.set_defaults(func=cmd_show)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
