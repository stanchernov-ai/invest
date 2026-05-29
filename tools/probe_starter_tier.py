"""Live probe of FMP endpoints proposed as optimizations — Starter tier validation.

Run: .venv\\Scripts\\python.exe tools\\probe_starter_tier.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("FMP_API_KEY")
if not API_KEY:
    raise SystemExit("FMP_API_KEY not set")

STABLE = "https://financialmodelingprep.com/stable"
V3 = "https://financialmodelingprep.com/api/v3"

# Endpoints to validate (including rejected batch variants)
CANDIDATES = [
    ("macro_current", f"{STABLE}/quote?symbol=TLT&apikey={{key}}", "Current production path (TLT only)"),
    ("macro_current_vxx", f"{STABLE}/quote?symbol=VXX&apikey={{key}}", "Current production path (VXX only)"),
    ("batch_quote_stable_csv", f"{STABLE}/batch-quote?symbols=TLT,VXX&apikey={{key}}", "Proposed batch-quote stable"),
    ("batch_quote_stable_pipe", f"{STABLE}/batch-quote?symbols=TLT|VXX&apikey={{key}}", "batch-quote pipe separator"),
    ("batch_quote_v3", f"{V3}/quote/TLT,VXX?apikey={{key}}", "v3 comma batch quote"),
    ("batch_quote_v3_alt", f"{V3}/quote/TLT|VXX?apikey={{key}}", "v3 pipe batch quote"),
    ("quote_short_stable", f"{STABLE}/quote-short?symbol=TLT&apikey={{key}}", "quote-short (lighter?)"),
    ("quote_short_vxx", f"{STABLE}/quote-short?symbol=VXX&apikey={{key}}", "quote-short VXX"),
]


async def probe_one(session: aiohttp.ClientSession, name: str, url_template: str, note: str) -> dict:
    url = url_template.format(key=API_KEY)
    t0 = time.perf_counter()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            elapsed_ms = round((time.perf_counter() - t0) * 1000)
            body_text = await resp.text()
            try:
                body = json.loads(body_text)
            except json.JSONDecodeError:
                body = body_text[:500]
            rows = len(body) if isinstance(body, list) else (1 if isinstance(body, dict) and body else 0)
            # Extract price if possible
            prices = {}
            if isinstance(body, list):
                for row in body[:5]:
                    if isinstance(row, dict) and row.get("symbol") and row.get("price") is not None:
                        prices[row["symbol"]] = row["price"]
                    elif isinstance(row, dict) and row.get("price") is not None:
                        prices[row.get("symbol", "?")] = row["price"]
            elif isinstance(body, dict) and "Error Message" in body:
                err = body["Error Message"]
            else:
                err = None
            err_msg = None
            if isinstance(body, dict) and "Error Message" in body:
                err_msg = body["Error Message"]
            elif resp.status in (401, 403, 404):
                err_msg = f"HTTP {resp.status}"
            usable = resp.status == 200 and rows > 0 and err_msg is None
            if isinstance(body, list) and body and isinstance(body[0], dict):
                if not any(k in body[0] for k in ("price", "symbol")):
                    usable = False
            return {
                "name": name,
                "note": note,
                "status": resp.status,
                "elapsed_ms": elapsed_ms,
                "rows": rows,
                "prices": prices,
                "error": err_msg,
                "usable": usable,
                "url_redacted": url.replace(API_KEY, "REDACTED"),
            }
    except Exception as e:
        return {
            "name": name,
            "note": note,
            "status": None,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000),
            "rows": 0,
            "prices": {},
            "error": str(e),
            "usable": False,
            "url_redacted": url.replace(API_KEY, "REDACTED"),
        }


async def main():
    async with aiohttp.ClientSession() as session:
        results = []
        for name, tmpl, note in CANDIDATES:
            r = await probe_one(session, name, tmpl, note)
            results.append(r)
            await asyncio.sleep(0.3)  # gentle pacing

    print("=== FMP STARTER TIER — OPTIMIZATION ENDPOINT VALIDATION ===\n")
    for r in results:
        flag = "USABLE" if r["usable"] else "NOT USABLE"
        print(f"[{flag}] {r['name']}")
        print(f"  {r['note']}")
        print(f"  HTTP {r['status']} | {r['elapsed_ms']}ms | rows={r['rows']} | prices={r['prices']}")
        if r["error"]:
            print(f"  error: {r['error']}")
        print()

    # Parallel vs sequential timing for current approach
    async with aiohttp.ClientSession() as session:
        from src.data.fmp_client import fetch_json_endpoint, get_fmp_macro

        t0 = time.perf_counter()
        macro = await get_fmp_macro(API_KEY, session)
        parallel_ms = round((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        tlt = await fetch_json_endpoint(session, f"{STABLE}/quote?symbol=TLT&apikey={API_KEY}")
        vxx = await fetch_json_endpoint(session, f"{STABLE}/quote?symbol=VXX&apikey={API_KEY}")
        sequential_ms = round((time.perf_counter() - t0) * 1000)

    print("=== CURRENT MACRO PATH (already in production) ===")
    print(f"  get_fmp_macro (asyncio.gather 2x quote): {parallel_ms}ms -> {macro}")
    print(f"  sequential 2x quote: {sequential_ms}ms")
    print(f"  Savings from batch even if it worked: ~{max(0, parallel_ms - 200)}ms (negligible vs prepare budget)\n")

    usable_batch = [r for r in results if "batch" in r["name"] and r["usable"]]
    print("=== VERDICT ===")
    if usable_batch:
        print(f"  Batch macro quote WORKS on Starter: {usable_batch[0]['name']}")
    else:
        print("  Batch macro quote: NOT available on Starter — keep parallel /quote calls (already optimal for this tier).")
    short_ok = all(r["usable"] for r in results if r["name"].startswith("quote_short"))
    if short_ok:
        print("  quote-short: works — could shave payload size for macro only (minor).")
    else:
        print("  quote-short: not a reliable substitute for macro quotes.")


if __name__ == "__main__":
    asyncio.run(main())
