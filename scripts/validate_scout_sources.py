"""Live probe for Scout / review-universe external sources before prod deploy.

Validates:
  - FMP stable company-screener (Scout fallback — required when Yahoo disabled or --skip-yahoo)
  - Yahoo Finance trending HTML scrape (primary discovery; may be blocked by IP)
  - End-to-end build_yahoo_discovery + build_review_universe in a temp DATA_DIR

At least one of FMP screener or Yahoo must pass; integration must always pass.

Usage (from repo root, requires .env with FMP_API_KEY for screener check):
  .venv\\Scripts\\python.exe scripts\\validate_scout_sources.py
  .venv\\Scripts\\python.exe scripts\\validate_scout_sources.py --skip-yahoo

Exit 0 = safe to deploy scout/review-universe changes; non-zero = fix before prod.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.config.settings  # noqa: F401 — loads .env
from src.config.settings import settings
from src import scout
from src.data.review_universe import build_review_universe, MAGNIFICENT_SEVEN

def probe_fmp_screener() -> tuple[bool, str, list[str]]:
    import requests

    api_key = settings.FMP_API_KEY
    if not api_key:
        return False, "FMP_API_KEY missing — Scout FMP fallback will fail.", []

    url = f"{scout.FMP_COMPANY_SCREENER_URL}&apikey={api_key}"
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code in (402, 403):
            return False, f"FMP company-screener returned HTTP {resp.status_code} (plan blocked).", []
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            return False, f"FMP screener returned empty or unexpected shape: {type(data)}", []
        symbols = [str(row.get("symbol", "")).upper() for row in data if row.get("symbol")]
        if not symbols:
            return False, "FMP screener returned rows but no symbols.", []
        return True, f"OK — {len(symbols)} symbol(s), e.g. {symbols[0]}", symbols
    except Exception as exc:
        return False, f"FMP company-screener request failed: {exc}", []


def probe_yahoo_scrape() -> tuple[bool, str, list[str]]:
    try:
        symbols = scout.scrape_yahoo_trending()
        if not symbols:
            return (
                False,
                "Yahoo trending scrape returned no symbols (blocked, HTML change, or outage). "
                "Set YAHOO_SCRAPE_ENABLED=false or rely on FMP fallback.",
                [],
            )
        return True, f"OK — {len(symbols)} symbol(s), e.g. {symbols[0]}", symbols
    except Exception as exc:
        return False, f"Yahoo scrape raised: {exc}", []


def probe_integration(*, skip_yahoo: bool) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        os.makedirs(data_dir, exist_ok=True)

        if skip_yahoo:
            os.environ["YAHOO_SCRAPE_ENABLED"] = "false"
        else:
            os.environ.pop("YAHOO_SCRAPE_ENABLED", None)

        try:
            yahoo = scout.build_yahoo_discovery(set(), set(), data_dir=data_dir, force_refresh=True)
            universe = build_review_universe(set(), include_yahoo=True, data_dir=data_dir)

            mag7_count = sum(1 for s in MAGNIFICENT_SEVEN if s in universe)
            if mag7_count != len(MAGNIFICENT_SEVEN):
                return False, f"Mag7 missing from universe ({mag7_count}/{len(MAGNIFICENT_SEVEN)})."

            cache_path = scout._yahoo_cache_path(data_dir)
            if not skip_yahoo and not os.path.exists(cache_path):
                return False, "Yahoo cache file not written after force_refresh."

            return (
                True,
                f"OK — yahoo_discovery={len(yahoo)} symbols, "
                f"review_universe={len(universe)} symbols, cache={'yes' if os.path.exists(cache_path) else 'n/a'}",
            )
        finally:
            os.environ.pop("YAHOO_SCRAPE_ENABLED", None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Scout external sources before prod.")
    parser.add_argument(
        "--skip-yahoo",
        action="store_true",
        help="Skip live Yahoo HTML probe (still tests FMP + integration with YAHOO_SCRAPE_ENABLED=false).",
    )
    args = parser.parse_args()

    print("=== Scout / review-universe source validation ===\n")
    failures: list[str] = []

    fmp_ok, fmp_msg, _ = probe_fmp_screener()
    fmp_status = "PASS" if fmp_ok else "FAIL"
    print(f"[{fmp_status}] FMP company-screener (stable): {fmp_msg}")

    yahoo_ok = False
    if args.skip_yahoo:
        print("[SKIP] Yahoo trending HTML ( --skip-yahoo )")
    else:
        yahoo_ok, yahoo_msg, _ = probe_yahoo_scrape()
        yahoo_status = "PASS" if yahoo_ok else "WARN"
        print(f"[{yahoo_status}] Yahoo trending HTML: {yahoo_msg}")

    if args.skip_yahoo:
        if not fmp_ok:
            failures.append("fmp_screener")
    elif not fmp_ok and not yahoo_ok:
        failures.append("discovery_sources")

    ok, msg = probe_integration(skip_yahoo=args.skip_yahoo)
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] Integration (build_review_universe): {msg}")
    if not ok:
        failures.append("integration")

    print()
    if failures:
        print(f"RESULT: BLOCKED — fix {', '.join(failures)} before prod deploy.")
        return 1
    print("RESULT: PASS — scout sources validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
