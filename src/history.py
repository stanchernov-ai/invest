"""Time-weighted return (TWR) history engine.

Reconstructs daily securities holdings per account from the brokerage activity
files (trades back through 2025) anchored on today's actual holdings, values them
with FMP end-of-day closes, and computes flow-neutral time-weighted returns for
YTD and the trailing 12 months — for the total portfolio and each account.

Design notes:
* Basis is *securities only* (consistent with the value/pie-chart numbers). Cash is
  ignored; reinvested dividends are treated as share additions (flows), so they do
  not inflate the price-only return.
* TWR is computed by daily-linking: each day's return reflects only the price move
  of the shares held overnight, which automatically neutralizes buys/sells/deposits
  without needing to reconstruct cash balances.
* The full trailing window is recomputed from source every run, so a missed run (or
  a missed week) self-heals on the next execution — no special gap-fill needed.
"""

import os
import csv
import glob
import logging
import datetime
import asyncio

from src.config.settings import DATA_DIR
from src.data.fmp_client import fetch_price_series
from src.pipeline import clean_num, _get_col, build_account_holdings, ACCOUNT_ORDER, FIDELITY_ACCOUNT_MAP

logger = logging.getLogger(__name__)

_MONEY_MARKET = {"CASH", "CORE", "TOTAL", "PENDING", "BROKERAGELINK", "--", ""}


def _parse_date(raw):
    raw = str(raw).strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _is_tradeable_symbol(sym):
    if not sym or sym in _MONEY_MARKET:
        return False
    if "**" in sym or "FDRXX" in sym or "SPAXX" in sym:
        return False
    if sym.startswith("922"):  # Vanguard 401(k) collective trust, not price-tradeable
        return False
    return True


def parse_share_events(data_dir=None):
    """Parse brokerage activity CSVs into signed share events per account.

    Returns: {account: {symbol: [(date, signed_shares), ...]}}
    Sign convention follows the source files: Bought/Reinvestment positive,
    Sold negative. Rows without a real symbol or share quantity are ignored.
    """
    data_dir = data_dir or DATA_DIR
    events = {acct: {} for acct in ACCOUNT_ORDER}
    enc = "utf" + chr(45) + "8" + chr(45) + "sig"

    for file in glob.glob(os.path.join(data_dir, "*.csv")):
        file_lower = file.lower()
        if "activity" not in file_lower:
            continue
        broker = "fidelity" if "fidelity" in file_lower else "etrade"

        try:
            with open(file, mode="r", encoding=enc) as f:
                lines = f.readlines()
        except Exception:
            logger.warning("Could not read activity CSV for history.")
            continue

        header_idx = -1
        for i, line in enumerate(lines):
            ll = line.lower()
            if "symbol" in ll and "quantity" in ll:
                header_idx = i
                break
        if header_idx < 0:
            continue

        etrade_account = "eTrade Roth IRA" if "roth" in file_lower else "eTrade Taxable"

        reader = csv.DictReader(lines[header_idx:])
        for row in reader:
            sym_key = next((k for k in row.keys() if k and "symbol" in str(k).lower()), None)
            if not sym_key:
                continue
            sym = str(row.get(sym_key) or "").strip().upper()
            if not _is_tradeable_symbol(sym):
                continue

            qty = clean_num(_get_col(row, ["quantity #", "quantity"]))
            if qty == 0:
                continue

            date_val = _parse_date(_get_col(row, ["activity/trade date", "run date", "trade date", "date"]))
            if date_val is None:
                continue

            if broker == "fidelity":
                acct_name = str(_get_col(row, ["account"])).strip().lower()
                account = FIDELITY_ACCOUNT_MAP.get(acct_name)
                if not account:
                    continue
            else:
                account = etrade_account

            events[account].setdefault(sym, []).append((date_val, qty))

    return events


def _shares_held_at(current_shares, sym_events, on_date):
    """Shares held at end of `on_date` = current shares minus net shares from
    events strictly after `on_date` (walking backward from today's holdings)."""
    held = current_shares
    for ev_date, signed in sym_events:
        if ev_date > on_date:
            held -= signed
    return max(held, 0.0)


def _forward_fill_prices(series, global_dates):
    """Given {date_str: price}, return list aligned to global_dates with the last
    known close carried forward (0.0 before the first available close)."""
    aligned = []
    last = 0.0
    for d in global_dates:
        if d in series:
            last = series[d]
        aligned.append(last)
    return aligned


async def build_account_returns(data_dir=None, api_key=None, session=None, window_days=370):
    """Compute time-weighted YTD + trailing-12M returns per account and total.

    Returns a dict ready to persist/render, or None on hard failure. Never raises
    (history is non-critical and must not abort the pipeline).
    """
    try:
        data_dir = data_dir or DATA_DIR
        today = datetime.date.today()
        start = today - datetime.timedelta(days=window_days)
        start_str = start.strftime("%Y-%m-%d")
        end_str = today.strftime("%Y-%m-%d")

        holdings = build_account_holdings(data_dir)
        events = parse_share_events(data_dir)

        current_shares = {acct: {} for acct in ACCOUNT_ORDER}
        symbol_universe = set()
        for acct in ACCOUNT_ORDER:
            for sym, info in holdings.get(acct, {}).items():
                if _is_tradeable_symbol(sym):
                    current_shares[acct][sym] = info.get("shares", 0.0)
                    symbol_universe.add(sym)
            for sym in events.get(acct, {}):
                current_shares[acct].setdefault(sym, 0.0)
                symbol_universe.add(sym)

        if not symbol_universe:
            logger.warning("History engine: no symbols to value.")
            return None

        # Cap concurrency so the extra EOD calls don't trip FMP starter-tier rate
        # limits (which would trigger long exponential backoff against the 10-min
        # Azure Functions budget).
        sem = asyncio.Semaphore(5)

        async def _fetch(sym):
            async with sem:
                # FMP uses a hyphen for share-class tickers (e.g. BRK.B -> BRK-B).
                fmp_sym = sym.replace(".", "-")
                return await fetch_price_series(fmp_sym, api_key, session, start_str, end_str)

        symbols = sorted(symbol_universe)
        price_results = await asyncio.gather(*[_fetch(s) for s in symbols], return_exceptions=True)
        prices = {}
        for sym, res in zip(symbols, price_results):
            prices[sym] = res if isinstance(res, dict) else {}

        global_dates = sorted({d for series in prices.values() for d in series.keys() if start_str <= d <= end_str})
        if len(global_dates) < 2:
            logger.warning("History engine: insufficient price history.")
            return None

        aligned = {sym: _forward_fill_prices(series, global_dates) for sym, series in prices.items()}
        date_objs = [datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in global_dates]
        ytd_start = datetime.date(today.year, 1, 1)
        twelve_mo_start = today - datetime.timedelta(days=365)

        # Cumulative TWR growth factors per account + total, for each window.
        accounts = ACCOUNT_ORDER + ["Total"]
        factor = {acct: {"ytd": 1.0, "12m": 1.0} for acct in accounts}
        daily_total = {}

        for i in range(len(global_dates)):
            cur_date = date_objs[i]
            # Daily total value (for the optional series / display).
            tot_val = 0.0
            for acct in ACCOUNT_ORDER:
                for sym, sh0 in current_shares[acct].items():
                    held = _shares_held_at(sh0, events[acct].get(sym, []), cur_date)
                    tot_val += held * aligned.get(sym, [0.0] * len(global_dates))[i]
            daily_total[global_dates[i]] = round(tot_val, 2)

            if i == 0:
                continue
            prev_date = date_objs[i - 1]

            total_gain = 0.0
            total_vprev = 0.0
            for acct in ACCOUNT_ORDER:
                v_prev = 0.0
                gain = 0.0
                for sym, sh0 in current_shares[acct].items():
                    held_prev = _shares_held_at(sh0, events[acct].get(sym, []), prev_date)
                    if held_prev <= 0:
                        continue
                    p_prev = aligned[sym][i - 1]
                    p_cur = aligned[sym][i]
                    v_prev += held_prev * p_prev
                    gain += held_prev * (p_cur - p_prev)
                total_gain += gain
                total_vprev += v_prev
                if v_prev > 1.0:
                    r = gain / v_prev
                    if cur_date >= ytd_start:
                        factor[acct]["ytd"] *= (1 + r)
                    if cur_date >= twelve_mo_start:
                        factor[acct]["12m"] *= (1 + r)
            if total_vprev > 1.0:
                r_tot = total_gain / total_vprev
                if cur_date >= ytd_start:
                    factor["Total"]["ytd"] *= (1 + r_tot)
                if cur_date >= twelve_mo_start:
                    factor["Total"]["12m"] *= (1 + r_tot)

        returns = {}
        for acct in accounts:
            returns[acct] = {
                "ytd": round((factor[acct]["ytd"] - 1) * 100, 2),
                "12m": round((factor[acct]["12m"] - 1) * 100, 2),
            }

        return {
            "updated": end_str,
            "method": "time_weighted",
            "basis": "securities_only",
            "returns": returns,
            "daily_total": daily_total,
        }
    except Exception as e:
        logger.error(f"History engine failed (non-fatal): {e}")
        return None
