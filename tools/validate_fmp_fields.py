"""Probe FMP stable/v3 endpoints and report which KPI fields actually populate.

Usage (from repo root):
  .venv\\Scripts\\python.exe tools\\validate_fmp_fields.py
  .venv\\Scripts\\python.exe tools\\validate_fmp_fields.py --symbols AAPL,NVDA,MSFT,SPY,QQQ,BRK-B
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.fmp_client import fetch_json_endpoint, safe_float  # noqa: E402

dash = chr(45)
BASE = f"https://financialmodelingprep.com/stable"

# Fields our code reads today + Tier-1 KPI candidates from the audit.
FIELD_SPECS = {
    "profile": {
        "url": f"{BASE}/profile?symbol={{sym}}",
        "keys_we_read": ["isEtf", "isFund", "beta", "image"],
        "keys_kpi_audit": [
            "symbol", "companyName", "sector", "industry", "mktCap",
            "currency", "exchange", "country", "ceo", "description",
        ],
    },
    "quote": {
        "url": f"{BASE}/quote?symbol={{sym}}",
        "keys_we_read": ["price"],
        "keys_kpi_audit": [
            "change", "changesPercentage", "dayLow", "dayHigh",
            "yearHigh", "yearLow", "volume", "avgVolume", "marketCap",
            "pe", "eps", "open", "previousClose", "priceAvg50", "priceAvg200",
        ],
    },
    "key-metrics-ttm": {
        "url": f"{BASE}/key{dash}metrics{dash}ttm?symbol={{sym}}",
        "keys_we_read": [],
        "keys_kpi_audit": [
            "returnOnEquityTTM", "returnOnAssetsTTM", "returnOnInvestedCapitalTTM",
            "freeCashFlowYieldTTM", "earningsYieldTTM", "currentRatioTTM",
            "debtToEquityRatioTTM", "netDebtToEBITDATTM", "enterpriseValueTTM",
            "marketCapTTM", "peRatioTTM", "priceToSalesRatioTTM",
        ],
    },
    "ratios-ttm": {
        "url": f"{BASE}/ratios{dash}ttm?symbol={{sym}}",
        "keys_we_read": [
            "priceToEarningsRatioTTM", "priceToEarningsGrowthRatioTTM",
            "priceToSalesRatioTTM", "debtToEquityRatioTTM",
        ],
        "keys_kpi_audit": [
            "grossProfitMarginTTM", "operatingProfitMarginTTM", "netProfitMarginTTM",
            "returnOnEquityTTM", "returnOnAssetsTTM", "currentRatioTTM",
            "interestCoverageRatioTTM", "dividendYieldTTM", "priceToBookRatioTTM",
        ],
    },
    "grades-consensus": {
        "url": f"{BASE}/grades{dash}consensus?symbol={{sym}}",
        "keys_we_read": ["consensus"],
        "keys_kpi_audit": [
            "symbol", "consensus", "strongBuy", "buy", "hold", "sell", "strongSell",
        ],
    },
    "rating_DEAD": {
        "url": f"{BASE}/rating?symbol={{sym}}",
        "keys_we_read": [],
        "keys_kpi_audit": ["ratingRecommendation"],
    },
    "price-target-consensus": {
        "url": f"{BASE}/price{dash}target{dash}consensus?symbol={{sym}}",
        "keys_we_read": ["targetConsensus"],
        "keys_kpi_audit": [
            "symbol", "targetHigh", "targetLow", "targetConsensus", "targetMedian",
        ],
    },
    "earnings": {
        "url": f"{BASE}/earnings?symbol={{sym}}",
        "keys_we_read": ["date", "epsEstimated", "revenueEstimated"],
        "keys_kpi_audit": [
            "date", "symbol", "epsActual", "epsEstimated", "revenueActual", "revenueEstimated",
        ],
    },
    "earning_calendar_DEAD": {
        "url": f"{BASE}/earning_calendar?symbol={{sym}}",
        "keys_we_read": [],
        "keys_kpi_audit": ["date"],
    },
    "financial-growth": {
        "url": f"{BASE}/financial{dash}growth?symbol={{sym}}",
        "keys_we_read": ["revenueGrowth", "epsgrowth"],
        "keys_kpi_audit": [
            "revenueGrowth", "epsgrowth", "epsGrowth", "grossProfitGrowth",
            "operatingIncomeGrowth", "netIncomeGrowth", "freeCashFlowGrowth",
        ],
    },
    "historical-price-eod-light": {
        "url": None,
        "keys_we_read": ["date", "price"],
        "keys_kpi_audit": [],
    },
}


def _present(val) -> bool:
    if val is None:
        return False
    if val == "":
        return False
    if isinstance(val, (int, float)) and val == 0:
        return True  # zero is valid data
    if isinstance(val, str) and val.strip().lower() in ("n/a", "null", "none"):
        return False
    return True


def _first_row(data) -> dict | None:
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    if isinstance(data, dict) and data and "Error Message" not in data:
        return data
    return None


def _all_keys_in_payload(row: dict) -> list[str]:
    return sorted(row.keys())


async def probe_endpoint(session, name: str, url: str, sym: str, api_key: str) -> dict:
    full_url = url.format(sym=sym) + f"&apikey={api_key}"
    try:
        data = await fetch_json_endpoint(session, full_url)
    except Exception as e:
        return {"ok": False, "error": str(e), "rows": 0, "row": None, "all_keys": []}

    if name == "earning_calendar":
        row = data[0] if isinstance(data, list) and data else None
        rows = len(data) if isinstance(data, list) else 0
        return {"ok": rows > 0, "error": None, "rows": rows, "row": row, "all_keys": _all_keys_in_payload(row) if row else []}

    row = _first_row(data)
    return {
        "ok": row is not None,
        "error": None if row else "empty_or_non_dict",
        "rows": len(data) if isinstance(data, list) else (1 if row else 0),
        "row": row,
        "all_keys": _all_keys_in_payload(row) if row else [],
    }


async def probe_eod(session, sym: str, api_key: str) -> dict:
    end = datetime.today()
    start = end - timedelta(days=120)
    url = (
        f"{BASE}/historical-price-eod/light?symbol={sym}"
        f"&from={start.strftime('%Y-%m-%d')}&to={end.strftime('%Y-%m-%d')}&apikey={api_key}"
    )
    try:
        data = await fetch_json_endpoint(session, url)
        prices = [d for d in data if isinstance(d, dict) and d.get("price") is not None]
        sample = data[0] if data and isinstance(data[0], dict) else {}
        return {
            "ok": len(prices) >= 2,
            "error": None if len(prices) >= 2 else "insufficient_points",
            "rows": len(data) if isinstance(data, list) else 0,
            "row": sample,
            "all_keys": _all_keys_in_payload(sample) if sample else [],
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "rows": 0, "row": None, "all_keys": []}


async def run_validation(symbols: list[str]) -> dict:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        raise SystemExit("FMP_API_KEY not set in .env or environment.")

    results = {}
    async with aiohttp.ClientSession() as session:
        for sym in symbols:
            sym_results = {}
            for ep_name, spec in FIELD_SPECS.items():
                if ep_name == "historical-price-eod-light":
                    sym_results[ep_name] = await probe_eod(session, sym, api_key)
                else:
                    sym_results[ep_name] = await probe_endpoint(
                        session, ep_name, spec["url"], sym, api_key
                    )
            results[sym] = sym_results
    return results


def summarize(results: dict) -> None:
    # Aggregate field presence across symbols (equities only for some checks)
    equities = [s for s in results if s not in ("SPY", "QQQ", "TLT", "VXX")]
    if not equities:
        equities = list(results.keys())

    print("\n=== ENDPOINT AVAILABILITY (any symbol) ===")
    for ep in FIELD_SPECS:
        hits = []
        for sym, sym_res in results.items():
            r = sym_res.get(ep, {})
            status = "OK" if r.get("ok") else f"FAIL ({r.get('error')})"
            hits.append(f"{sym}:{status}")
        print(f"  {ep}: " + " | ".join(hits))

    print("\n=== FIELD POPULATION (equities: %s) ===" % ", ".join(equities))
    for ep, spec in FIELD_SPECS.items():
        all_keys = set(spec["keys_we_read"] + spec["keys_kpi_audit"])
        if not all_keys:
            continue
        print(f"\n  [{ep}]")
        for key in sorted(all_keys):
            present = []
            missing = []
            alt_values = defaultdict(list)
            for sym in equities:
                row = results[sym][ep].get("row") or {}
                if not row and ep == "earning_calendar":
                    rows_n = results[sym][ep].get("rows", 0)
                    if rows_n == 0:
                        missing.append(sym)
                        continue
                val = row.get(key)
                if not _present(val):
                    # try common casing variants for growth fields
                    for alt in (key.swapcase(), key.lower(), key.upper()):
                        if alt != key and _present(row.get(alt)):
                            alt_values[alt].append(sym)
                            val = row.get(alt)
                            break
                if _present(val):
                    present.append(sym)
                else:
                    missing.append(sym)
            tag = "CODE_READS" if key in spec["keys_we_read"] else "KPI_CANDIDATE"
            pct = 100 * len(present) / max(len(equities), 1)
            line = f"    {key:40} {len(present)}/{len(equities)} ({pct:.0f}%)  [{tag}]"
            if missing and len(missing) <= 4:
                line += f"  missing: {','.join(missing)}"
            elif missing:
                line += f"  missing: {len(missing)} symbols"
            print(line)
            for alt, syms in alt_values.items():
                print(f"      -> populated as '{alt}' for: {','.join(syms)}")

    print("\n=== ACTUAL JSON KEYS (first equity row per endpoint) ===")
    ref = equities[0] if equities else list(results.keys())[0]
    for ep, spec in FIELD_SPECS.items():
        r = results[ref][ep]
        if r.get("all_keys"):
            print(f"  {ep} ({ref}): {', '.join(r['all_keys'][:25])}")
            if len(r["all_keys"]) > 25:
                print(f"    ... +{len(r['all_keys']) - 25} more")

    print("\n=== CODE PATH SPOT CHECK (parsed values via fmp_client logic) ===")
    for sym in equities[:3]:
        row_ratio = results[sym]["ratios-ttm"].get("row") or {}
        row_growth = results[sym]["financial-growth"].get("row") or {}
        eps_code = safe_float(row_growth.get("epsgrowth"))
        eps_alt = safe_float(row_growth.get("epsGrowth"))
        print(
            f"  {sym}: PE={safe_float(row_ratio.get('priceToEarningsRatioTTM'))} "
            f"PEG={safe_float(row_ratio.get('priceToEarningsGrowthRatioTTM'))} "
            f"revGrowth={safe_float(row_growth.get('revenueGrowth'))} "
            f"epsGrowth(code key epsgrowth)={eps_code} "
            f"epsGrowth(camelCase)={eps_alt}"
        )

    print("\n=== ETFs (SPY/QQQ) — expect sparse fundamentals ===")
    for sym in ("SPY", "QQQ"):
        if sym not in results:
            continue
        for ep in ("ratios-ttm", "key-metrics-ttm", "financial-growth", "rating"):
            r = results[sym][ep]
            print(f"  {sym} {ep}: ok={r.get('ok')} rows={r.get('rows')} err={r.get('error')}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        default="AAPL,NVDA,MSFT,GOOGL,SPY,QQQ,TLT,VXX",
        help="Comma-separated tickers",
    )
    parser.add_argument("--json-out", help="Write full probe results to this path")
    args = parser.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    print(f"Probing FMP for: {', '.join(symbols)}")
    results = asyncio.run(run_validation(symbols))

    if args.json_out:
        # strip rows for smaller file but keep keys
        slim = {}
        for sym, eps in results.items():
            slim[sym] = {}
            for ep, r in eps.items():
                slim[sym][ep] = {
                    k: r[k] for k in ("ok", "error", "rows", "all_keys")
                    if k in r
                }
                if r.get("row"):
                    slim[sym][ep]["row_sample"] = r["row"]
        Path(args.json_out).write_text(json.dumps(slim, indent=2), encoding="utf-8")
        print(f"Wrote {args.json_out}")

    summarize(results)


if __name__ == "__main__":
    main()
