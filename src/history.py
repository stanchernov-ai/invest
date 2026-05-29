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
from src.data.fmp_client import fetch_price_series, eod_cache_lookup, slice_price_series, to_fmp_symbol
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


def collect_symbol_universe(data_dir=None) -> set:
    """Tradeable symbols from current holdings + activity files (no network I/O)."""
    data_dir = data_dir or DATA_DIR
    holdings = build_account_holdings(data_dir)
    events = parse_share_events(data_dir)
    universe = set()
    for acct in ACCOUNT_ORDER:
        for sym, info in holdings.get(acct, {}).items():
            if _is_tradeable_symbol(sym):
                universe.add(sym)
        for sym in events.get(acct, {}):
            if _is_tradeable_symbol(sym):
                universe.add(sym)
    return universe


async def build_account_returns(
    data_dir=None, api_key=None, session=None, window_days=370, eod_cache=None
):
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

        def _series_for(sym: str) -> dict:
            cached = eod_cache_lookup(eod_cache, sym)
            if cached:
                return slice_price_series(cached, start_str, end_str)
            return {}

        spy_series = _series_for("SPY")
        qqq_series = _series_for("QQQ")
        if not spy_series:
            spy_series = await fetch_price_series("SPY", api_key, session, start_str, end_str)
        if not qqq_series:
            qqq_series = await fetch_price_series("QQQ", api_key, session, start_str, end_str)

        symbols = sorted(symbol_universe)
        prices = {}
        missing = []
        for sym in symbols:
            sliced = _series_for(sym)
            if sliced:
                prices[sym] = sliced
            else:
                missing.append(sym)

        if missing:
            sem = asyncio.Semaphore(5)

            async def _fetch(sym):
                async with sem:
                    return sym, await fetch_price_series(
                        to_fmp_symbol(sym), api_key, session, start_str, end_str
                    )

            fetched = await asyncio.gather(*[_fetch(s) for s in missing], return_exceptions=True)
            for item in fetched:
                if isinstance(item, Exception):
                    continue
                sym, series = item
                prices[sym] = series if isinstance(series, dict) else {}

        global_dates = sorted({d for series in prices.values() for d in series.keys() if start_str <= d <= end_str})
        if len(global_dates) < 2:
            logger.warning("History engine: insufficient price history.")
            return None

        aligned = {sym: _forward_fill_prices(series, global_dates) for sym, series in prices.items()}
        date_objs = [datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in global_dates]
        ytd_start = datetime.date(today.year, 1, 1)
        twelve_mo_start = today - datetime.timedelta(days=365)
        three_mo_start = today - datetime.timedelta(days=90)

        # Cumulative TWR growth factors per account + total, for each window.
        accounts = ACCOUNT_ORDER + ["Total"]
        factor = {acct: {"ytd": 1.0, "12m": 1.0, "3m": 1.0} for acct in accounts}
        daily_total = {}
        portfolio_index_by_date = {}
        portfolio_index = 100.0

        for i in range(len(global_dates)):
            cur_date = date_objs[i]
            # Daily total value (for the optional series / display).
            tot_val = 0.0
            for acct in ACCOUNT_ORDER:
                for sym, sh0 in current_shares[acct].items():
                    held = _shares_held_at(sh0, events[acct].get(sym, []), cur_date)
                    tot_val += held * aligned.get(sym, [0.0] * len(global_dates))[i]
            daily_total[global_dates[i]] = round(tot_val, 2)
            portfolio_index_by_date[global_dates[i]] = round(portfolio_index, 2)

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
                    if cur_date >= three_mo_start:
                        factor[acct]["3m"] *= (1 + r)
            if total_vprev > 1.0:
                r_tot = total_gain / total_vprev
                portfolio_index *= (1 + r_tot)
                portfolio_index_by_date[global_dates[i]] = round(portfolio_index, 2)
                if cur_date >= ytd_start:
                    factor["Total"]["ytd"] *= (1 + r_tot)
                if cur_date >= twelve_mo_start:
                    factor["Total"]["12m"] *= (1 + r_tot)
                if cur_date >= three_mo_start:
                    factor["Total"]["3m"] *= (1 + r_tot)

        returns = {}
        for acct in accounts:
            returns[acct] = {
                "ytd": round((factor[acct]["ytd"] - 1) * 100, 2),
                "12m": round((factor[acct]["12m"] - 1) * 100, 2),
                "3m": round((factor[acct]["3m"] - 1) * 100, 2),
            }

        spy_aligned = _forward_fill_prices(spy_series, global_dates)
        qqq_aligned = _forward_fill_prices(qqq_series, global_dates)
        benchmark_history = {}
        for i, date_str in enumerate(global_dates):
            benchmark_history[date_str.replace("-", "")] = {
                "portfolio": daily_total.get(date_str, 0.0),
                "portfolio_index": portfolio_index_by_date.get(date_str, 100.0),
                "spy": round(spy_aligned[i], 2),
                "qqq": round(qqq_aligned[i], 2),
            }

        return {
            "updated": end_str,
            "method": "time_weighted",
            "basis": "securities_only",
            "returns": returns,
            "daily_total": daily_total,
            "benchmark_history": benchmark_history,
        }
    except Exception as e:
        logger.error(f"History engine failed (non-fatal): {e}")
        return None
