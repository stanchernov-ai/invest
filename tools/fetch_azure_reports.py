#!/usr/bin/env python
"""Fetch Invest AI Boardroom artifacts from Azure Blob Storage into a local cache
so Cursor agents (and humans) can review past runs offline.

It pulls from the two output containers:
  * boardroom-reports -> executive_briefing_*.html, qa_dashboard_*.html, raw_debate_log_*.md
  * boardroom-state   -> api_telemetry_*.json (+ the singleton state JSONs:
                         run_status.json, portfolio_history.json,
                         portfolio_returns.json, board_verdicts.json)

Auth reuses the pipeline's AZURE_STORAGE_CONNECTION_STRING (.env), via
src.storage_client.get_blob_service_client.

Usage (from repo root, via the venv interpreter):
  .venv\\Scripts\\python.exe tools/fetch_azure_reports.py                 # latest run + state singletons
  .venv\\Scripts\\python.exe tools/fetch_azure_reports.py --list          # list available run IDs, no download
  .venv\\Scripts\\python.exe tools/fetch_azure_reports.py --latest 3      # last 3 of each artifact family
  .venv\\Scripts\\python.exe tools/fetch_azure_reports.py --run-id 20260528_204417
  .venv\\Scripts\\python.exe tools/fetch_azure_reports.py --out .cache --no-state-singletons

Exit codes: 0 = ok, 2 = no Azure connection string / client, 3 = nothing matched.
"""
import os
import sys
import re
import json
import argparse

# Ensure the repo root is importable when this file is run as a script
# (python tools/fetch_azure_reports.py puts tools/ on sys.path, not the root).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.storage_client import get_blob_service_client, STATE_CONTAINER, REPORT_CONTAINER

# Timestamped artifact families: prefix -> source container.
ARTIFACT_FAMILIES = {
    "executive_briefing_": REPORT_CONTAINER,
    "qa_dashboard_": REPORT_CONTAINER,
    "raw_debate_log_": REPORT_CONTAINER,
    "api_telemetry_": STATE_CONTAINER,
    "qa_reports_": STATE_CONTAINER,
    "qa_human_review_": STATE_CONTAINER,
}

# Always-current singletons worth grabbing alongside a run.
STATE_SINGLETONS = [
    "run_status.json",
    "portfolio_history.json",
    "portfolio_returns.json",
    "board_verdicts.json",
]

# run id looks like 20260528_204417
RUN_ID_RE = re.compile(r"(\d{8}_\d{6})")


def extract_run_id(name: str):
    m = RUN_ID_RE.search(name)
    return m.group(1) if m else None


def list_container(client, container):
    """Return [(name, last_modified)] for a container, or [] if it doesn't exist."""
    try:
        cc = client.get_container_client(container)
        if not cc.exists():
            return []
        return [(b.name, b.last_modified) for b in cc.list_blobs()]
    except Exception as e:
        print(f"  ! Could not list {container}: {e}", file=sys.stderr)
        return []


def download(client, container, name, out_dir, subdir):
    dest_dir = os.path.join(out_dir, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(name))
    data = client.get_blob_client(container=container, blob=name).download_blob().readall()
    with open(dest, "wb") as f:
        f.write(data)
    return dest, len(data)


def collect_run_ids(report_blobs, state_blobs):
    """Map run_id -> set of artifact prefixes present, newest first."""
    runs = {}
    for name, _ in report_blobs + state_blobs:
        rid = extract_run_id(name)
        if not rid:
            continue
        for prefix in ARTIFACT_FAMILIES:
            if name.startswith(prefix):
                runs.setdefault(rid, set()).add(prefix.rstrip("_"))
    return dict(sorted(runs.items(), key=lambda kv: kv[0], reverse=True))


def main():
    parser = argparse.ArgumentParser(description="Fetch Boardroom artifacts from Azure to a local cache.")
    parser.add_argument("--out", default=".cache", help="Output directory (default: .cache)")
    parser.add_argument("--latest", type=int, default=1, help="How many of each artifact family to fetch (default: 1)")
    parser.add_argument("--run-id", default=None, help="Fetch all artifacts for a specific run id (e.g. 20260528_204417)")
    parser.add_argument("--list", action="store_true", help="List available run IDs and exit (no download)")
    parser.add_argument("--no-state-singletons", action="store_true", help="Skip run_status/portfolio_history/etc.")
    args = parser.parse_args()

    client = get_blob_service_client()
    if not client:
        print("ERROR: No Azure client. Set AZURE_STORAGE_CONNECTION_STRING in your .env.", file=sys.stderr)
        return 2

    report_blobs = list_container(client, REPORT_CONTAINER)
    state_blobs = list_container(client, STATE_CONTAINER)
    runs = collect_run_ids(report_blobs, state_blobs)

    if args.list:
        if not runs:
            print("No timestamped runs found in Azure.")
            return 3
        print(f"Available runs (newest first) - {len(runs)} total:\n")
        for rid, prefixes in runs.items():
            print(f"  {rid}  [{', '.join(sorted(prefixes))}]")
        return 0

    # Decide which (container, blobname) pairs to download.
    to_fetch = []  # (container, name, subdir)

    if args.run_id:
        rid = args.run_id
        matched = ([(REPORT_CONTAINER, n, "reports") for n, _ in report_blobs if rid in n] +
                   [(STATE_CONTAINER, n, "state") for n, _ in state_blobs if rid in n])
        if not matched:
            print(f"No artifacts found for run id {rid}.", file=sys.stderr)
            return 3
        to_fetch.extend(matched)
    else:
        # Latest N of each timestamped family (names sort chronologically).
        report_names = sorted([n for n, _ in report_blobs], reverse=True)
        state_names = sorted([n for n, _ in state_blobs], reverse=True)
        for prefix, container in ARTIFACT_FAMILIES.items():
            pool = report_names if container == REPORT_CONTAINER else state_names
            subdir = "reports" if container == REPORT_CONTAINER else "state"
            picked = [n for n in pool if n.startswith(prefix)][: args.latest]
            to_fetch.extend((container, n, subdir) for n in picked)

    # State singletons (current snapshot), unless suppressed.
    if not args.no_state_singletons:
        existing_state = {n for n, _ in state_blobs}
        for name in STATE_SINGLETONS:
            if name in existing_state:
                to_fetch.append((STATE_CONTAINER, name, "state"))

    if not to_fetch:
        print("Nothing to fetch (no matching artifacts in Azure).", file=sys.stderr)
        return 3

    # De-dup while preserving order.
    seen = set()
    unique = []
    for item in to_fetch:
        key = (item[0], item[1])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    manifest = []
    print(f"Fetching {len(unique)} artifact(s) -> {out_dir}\n")
    for container, name, subdir in unique:
        try:
            dest, size = download(client, container, name, out_dir, subdir)
            manifest.append({"container": container, "blob": name, "path": dest, "bytes": size})
            print(f"  OK  {subdir}/{os.path.basename(name)}  ({size:,} bytes)")
        except Exception as e:
            print(f"  ERR {name}: {e}", file=sys.stderr)

    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"files": manifest, "count": len(manifest)}, f, indent=2)

    print(f"\nDone. {len(manifest)} file(s) cached. Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
