import os
import aiohttp
import asyncio
import logging
import datetime
import operator
import yfinance as yf
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)
dash = chr(45)
neg_two = ~1
neg_three = ~2
neg_five = ~4

# Single lookback for momentum (3Y CAGR) and history TWR (slice to shorter window in code).
EOD_LOOKBACK_DAYS = 1095

class RateLimitError(Exception):
    pass

class FatalDataError(Exception):
    pass

def safe_float(val, default='N/A'):
    if val is None or val == "":
        return default
    try:
        return round(float(val), 2)
    except (ValueError, TypeError):
        return default


def _first_row(data) -> dict:
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    if isinstance(data, dict) and data and "Error Message" not in data:
        return data
    return {}


def _growth_as_pct(val):
    """FMP growth fields are often decimal ratios (0.06 = 6%)."""
    f = safe_float(val)
    if f == 'N/A':
        return f
    if abs(f) < 2:
        return round(f * 100, 2)
    return f


def _consensus_from_grades(grades_row: dict, yf_info: dict) -> str:
    if grades_row.get("consensus"):
        return str(grades_row["consensus"])
    rec = yf_info.get("recommendationKey", "N/A")
    if rec and rec != "N/A":
        return str(rec).replace("_", " ").title()
    return "N/A"


def _next_earnings_from_rows(earn_rows: list, date_format: str) -> tuple:
    """Returns (date_str, eps_est, rev_est) for nearest future earnings."""
    if not earn_rows:
        return "Unknown", "N/A", "N/A"
    today_str = datetime.datetime.today().strftime(date_format)
    future = [e for e in earn_rows if isinstance(e, dict) and e.get("date", "") >= today_str]
    if not future:
        return "Unknown", "N/A", "N/A"
    future.sort(key=lambda x: x["date"])
    row = future[0]
    return (
        row.get("date", "Unknown"),
        safe_float(row.get("epsEstimated")),
        safe_float(row.get("revenueEstimated")),
    )


def _pct_off_52w_high(price, year_high) -> str:
    p = safe_float(price)
    h = safe_float(year_high)
    if p == 'N/A' or h == 'N/A' or h <= 0:
        return "N/A"
    return round((p - h) / h * 100, 2)

@retry(
    retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError, RateLimitError)),
    wait=wait_exponential(multiplier=2, min=4, max=20),
    stop=stop_after_attempt(5),
    reraise=True
)
async def fetch_json_endpoint(session: aiohttp.ClientSession, url: str) -> list:
    async with session.get(url, timeout=15) as response:
        if response.status == 429:
            logger.warning("Rate limit hit for URL.")
            raise RateLimitError("Rate limited by endpoint.")
        if response.status in [403, 401, 404]:
            return []
        response.raise_for_status()
        data = await response.json()
        if isinstance(data, dict) and 'Error Message' in data:
            raise RateLimitError("API capacity exhausted.")
        return data if isinstance(data, list) else [data]

def to_fmp_symbol(symbol: str) -> str:
    """FMP uses hyphens for share classes (BRK.B -> BRK-B)."""
    return symbol.replace(".", "-")


def eod_cache_lookup(eod_cache: dict | None, symbol: str) -> dict | None:
    """Resolve ledger or FMP ticker against a prefetch cache."""
    if not eod_cache:
        return None
    for key in (symbol, to_fmp_symbol(symbol)):
        series = eod_cache.get(key)
        if series:
            return series
    return None


def slice_price_series(series: dict, start_str: str, end_str: str) -> dict:
    return {d: p for d, p in series.items() if start_str <= d <= end_str}


def compute_momentum_from_series(series: dict) -> tuple:
    """Derive 3M trend % and 3Y CAGR % from {YYYY-MM-DD: close}."""
    if not series or len(series) < 2:
        return "N/A", "N/A"
    trend = "N/A"
    cagr = "N/A"
    try:
        dates_asc = sorted(series.keys())
        end_price = float(series[dates_asc[-1]])
        start_price_3y = float(series[dates_asc[0]])
        if start_price_3y > 0:
            cagr = round((((end_price / start_price_3y) ** (1 / 3)) - 1) * 100, 2)
        end_date = datetime.datetime.strptime(dates_asc[-1], "%Y-%m-%d").date()
        target_3m = (end_date - datetime.timedelta(days=95)).strftime("%Y-%m-%d")
        start_price_3m = None
        for d in dates_asc:
            if d >= target_3m:
                start_price_3m = float(series[d])
                break
        if start_price_3m and start_price_3m > 0:
            trend = round(((end_price - start_price_3m) / start_price_3m) * 100, 2)
    except Exception:
        logger.warning("Momentum computation failed for cached EOD series.")
    return trend, cagr


async def fetch_price_series(symbol: str, api_key: str, session: aiohttp.ClientSession, start_str: str, end_str: str) -> dict:
    # Daily EOD closes for [start, end] from FMP's stable light endpoint (the same
    # feed used for momentum). Returns {"YYYY-MM-DD": close_price}. Empty on failure
    # so the history engine can degrade gracefully without killing the pipeline.
    url = f"https://financialmodelingprep.com/stable/historical-price-eod/light?symbol={symbol}&from={start_str}&to={end_str}&apikey={api_key}"
    series = {}
    try:
        data = await fetch_json_endpoint(session, url)
        for d in data:
            if isinstance(d, dict) and d.get("date") and d.get("price") is not None:
                series[str(d["date"])[:10]] = float(d["price"])
    except Exception:
        logger.warning(f"FMP price series fetch failed for {symbol}")
    return series


async def prefetch_eod_cache(
    symbols: list,
    api_key: str,
    session: aiohttp.ClientSession,
    days: int = EOD_LOOKBACK_DAYS,
    max_concurrency: int = 5,
) -> dict:
    """One EOD light request per unique FMP symbol; aliases ledger tickers to the same series."""
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    fmp_symbols = sorted({to_fmp_symbol(s) for s in symbols if s})
    cache = {}
    sem = asyncio.Semaphore(max_concurrency)

    async def _fetch_one(fmp_sym: str):
        async with sem:
            series = await fetch_price_series(fmp_sym, api_key, session, start_str, end_str)
            return fmp_sym, series

    results = await asyncio.gather(*[_fetch_one(s) for s in fmp_symbols], return_exceptions=True)
    for fmp_sym, res in zip(fmp_symbols, results):
        if isinstance(res, Exception):
            logger.warning(f"EOD prefetch failed for {fmp_sym}: {res}")
            cache[fmp_sym] = {}
        else:
            _, series = res
            cache[fmp_sym] = series

    for sym in symbols:
        fmp = to_fmp_symbol(sym)
        if fmp in cache:
            cache[sym] = cache[fmp]
    return cache


async def fetch_historical_metrics(
    symbol: str,
    api_key: str,
    session: aiohttp.ClientSession,
    telemetry: dict = None,
    eod_cache: dict | None = None,
) -> tuple:
    fmp_sym = to_fmp_symbol(symbol)
    series = eod_cache_lookup(eod_cache, symbol)
    source_url = "eod_cache"

    if not series:
        end_date = datetime.datetime.today()
        start_date = end_date - datetime.timedelta(days=EOD_LOOKBACK_DAYS)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        source_url = (
            f"https://financialmodelingprep.com/stable/historical-price-eod/light"
            f"?symbol={fmp_sym}&from={start_str}&to={end_str}"
        )
        series = await fetch_price_series(fmp_sym, api_key, session, start_str, end_str)

    trend, cagr = compute_momentum_from_series(series)

    if telemetry is not None:
        if symbol not in telemetry:
            telemetry[symbol] = {}
        telemetry[symbol]["historical_metrics"] = {
            "source": "fmp_stable_eod_light",
            "url": source_url.replace(api_key, "REDACTED") if api_key in source_url else source_url,
            "response": {"3m_momentum": trend, "3y_cagr": cagr, "points": len(series)},
        }
    return trend, cagr


async def fetch_yfinance_fallback(symbol: str, telemetry: dict = None) -> dict:
    def get_yf_data():
        ticker = yf.Ticker(symbol)
        return ticker.info
    try:
        info = await asyncio.to_thread(get_yf_data)
        if telemetry is not None:
            if symbol not in telemetry: telemetry[symbol] = {}
            telemetry[symbol]["yfinance_fallback"] = {"url": "yfinance native python library", "response": info}
        return info
    except Exception as e:
        logger.warning(f"yfinance fallback failed for {symbol}")
        if telemetry is not None:
            if symbol not in telemetry: telemetry[symbol] = {}
            telemetry[symbol]["yfinance_fallback"] = {"url": "yfinance native python library", "response": f"ERROR: {str(e)}"}
        return {}

async def get_fmp_advanced_metrics(
    symbol: str,
    api_key: str,
    session: aiohttp.ClientSession,
    telemetry_ledger: dict = None,
    eod_cache: dict | None = None,
) -> dict:
    base_url = "https://financialmodelingprep.com/stable"
    date_format = f"%Y{dash}%m{dash}%d"
    
    if telemetry_ledger is not None and symbol not in telemetry_ledger:
        telemetry_ledger[symbol] = {}

    prof_url = f"{base_url}/profile?symbol={symbol}&apikey={api_key}"
    try:
        prof_res = await fetch_json_endpoint(session, prof_url)
    except Exception:
        prof_res = []

    if telemetry_ledger is not None:
        telemetry_ledger[symbol]["prof"] = {"url": prof_url.replace(api_key, "REDACTED"), "response": prof_res}

    is_etf = False
    beta = 'N/A'
    yf_info = {}

    if prof_res:
        prof_data = prof_res[0]
        is_etf = str(prof_data.get("isEtf", False)).lower() == 'true' or str(prof_data.get("isFund", False)).lower() == 'true'
        beta = safe_float(prof_data.get('beta'))
        image_url = prof_data.get('image', '')
    else:
        yf_info = await fetch_yfinance_fallback(symbol, telemetry_ledger)
        if not yf_info:
            raise FatalDataError(f"Complete Oracle Failure for {symbol}. All data sources exhausted.")
        is_etf = yf_info.get("quoteType", "") == "ETF"
        beta = safe_float(yf_info.get('beta'))
        image_url = ''

    trend_3m, cagr_3y = await fetch_historical_metrics(
        symbol, api_key, session, telemetry_ledger, eod_cache=eod_cache
    )

    if is_etf:
        quote_url = f"{base_url}/quote?symbol={symbol}&apikey={api_key}"
        try:
            quote_data = await fetch_json_endpoint(session, quote_url)
            if not quote_data: raise Exception()
            current_price = safe_float(quote_data[0].get('price'))
        except Exception:
            if not yf_info: yf_info = await fetch_yfinance_fallback(symbol, telemetry_ledger)
            current_price = safe_float(yf_info.get('currentPrice', yf_info.get('regularMarketPrice')))
            
        if current_price == 'N/A':
            raise FatalDataError("Quote data empty.")

        etf_sector = prof_res[0].get("sector", "N/A") if prof_res else "N/A"
        return {
            "beta": beta, "peg": "N/A", "ps": "N/A", "de": "N/A", "fwd_pe": "N/A",
            "roe": "N/A", "fcf_yield": "N/A", "sector": etf_sector, "market_cap": "N/A",
            "pct_off_52w_high": "N/A", "eps_estimated": "N/A", "revenue_estimated": "N/A",
            "target_high": "N/A", "target_low": "N/A",
            "3m_trend": trend_3m, "3y_cagr": cagr_3y, "rev_growth": "N/A", "eps_growth": "N/A",
            "current_price": current_price, "consensus": "N/A", "price_target": "N/A",
            "next_earnings": "Unknown", "fcs_score": 0, "fcs_rationale": "ETF Structural Exemption.",
            "image": image_url
        }

    else:
        sector = "N/A"
        market_cap = "N/A"
        if prof_res:
            prof_data = prof_res[0]
            sector = prof_data.get("sector") or "N/A"
            market_cap = safe_float(prof_data.get("marketCap"))

        urls = {
            "quote": f"{base_url}/quote?symbol={symbol}&apikey={api_key}",
            "met": f"{base_url}/key{dash}metrics{dash}ttm?symbol={symbol}&apikey={api_key}",
            "ratio": f"{base_url}/ratios{dash}ttm?symbol={symbol}&apikey={api_key}",
            "grades_consensus": f"{base_url}/grades{dash}consensus?symbol={symbol}&apikey={api_key}",
            "pt": f"{base_url}/price{dash}target{dash}consensus?symbol={symbol}&apikey={api_key}",
            "earn": f"{base_url}/earnings?symbol={symbol}&apikey={api_key}",
            "growth": f"{base_url}/financial{dash}growth?symbol={symbol}&apikey={api_key}"
        }

        tasks = {k: fetch_json_endpoint(session, url) for k, url in urls.items()}
        res = await asyncio.gather(*tasks.values(), return_exceptions=True)
        data_map = dict(zip(tasks.keys(), res))

        if telemetry_ledger is not None:
            for k, v in data_map.items():
                exact_url = urls.get(k, "Unknown URL")
                telemetry_ledger[symbol][k] = {"url": exact_url.replace(api_key, "REDACTED"), "response": f"ERROR: {str(v)}" if isinstance(v, Exception) else v}

        quote_row = {} if isinstance(data_map.get("quote"), Exception) else _first_row(data_map.get("quote", []))
        ratio_row = {} if isinstance(data_map.get("ratio"), Exception) else _first_row(data_map.get("ratio", []))
        grades_row = {} if isinstance(data_map.get("grades_consensus"), Exception) else _first_row(data_map.get("grades_consensus", []))
        pt_row = {} if isinstance(data_map.get("pt"), Exception) else _first_row(data_map.get("pt", []))
        earn_raw = data_map.get("earn", [])
        earn_data = [] if isinstance(earn_raw, Exception) else (earn_raw if isinstance(earn_raw, list) else [])
        growth_row = {} if isinstance(data_map.get("growth"), Exception) else _first_row(data_map.get("growth", []))
        met_row = {} if isinstance(data_map.get("met"), Exception) else _first_row(data_map.get("met", []))

        if not quote_row or not ratio_row:
            if not yf_info:
                yf_info = await fetch_yfinance_fallback(symbol, telemetry_ledger)

        if quote_row:
            current_price = safe_float(quote_row.get('price'))
        else:
            current_price = safe_float(yf_info.get('currentPrice', yf_info.get('regularMarketPrice')))

        if current_price == 'N/A' or current_price == 0:
            raise FatalDataError("Quote data empty.")

        pct_off_52w_high = _pct_off_52w_high(current_price, quote_row.get("yearHigh"))

        if ratio_row:
            fwd_pe = safe_float(ratio_row.get('priceToEarningsRatioTTM'))
            peg = safe_float(ratio_row.get('priceToEarningsGrowthRatioTTM'))
            ps = safe_float(ratio_row.get('priceToSalesRatioTTM'))
            de = safe_float(ratio_row.get('debtToEquityRatioTTM'))
        else:
            fwd_pe = safe_float(yf_info.get('forwardPE', yf_info.get('trailingPE')))
            peg = safe_float(yf_info.get('pegRatio'))
            ps = safe_float(yf_info.get('priceToSalesTrailing12Months'))
            de = safe_float(yf_info.get('debtToEquity'))

        roe = safe_float(met_row.get('returnOnEquityTTM'))
        fcf_yield = 'N/A'
        fcf_yield_raw = met_row.get('freeCashFlowYieldTTM')
        if fcf_yield_raw not in (None, ""):
            try:
                fcf_yield = round(float(fcf_yield_raw) * 100, 2)
            except (ValueError, TypeError):
                pass

        if not grades_row:
            if not yf_info:
                yf_info = await fetch_yfinance_fallback(symbol, telemetry_ledger)
        consensus = _consensus_from_grades(grades_row, yf_info)

        if pt_row:
            price_target = safe_float(pt_row.get('targetConsensus'))
            target_high = safe_float(pt_row.get('targetHigh'))
            target_low = safe_float(pt_row.get('targetLow'))
        else:
            price_target = safe_float(yf_info.get('targetMeanPrice'))
            target_high = "N/A"
            target_low = "N/A"

        if growth_row:
            rev_growth = _growth_as_pct(growth_row.get('revenueGrowth'))
            eps_growth = _growth_as_pct(growth_row.get('epsgrowth'))
        else:
            rev_growth = _growth_as_pct(yf_info.get('revenueGrowth'))
            eps_growth = _growth_as_pct(yf_info.get('earningsGrowth'))

        next_earnings, eps_estimated, revenue_estimated = _next_earnings_from_rows(earn_data, date_format)
        if next_earnings == "Unknown" and not yf_info:
            yf_info = await fetch_yfinance_fallback(symbol, telemetry_ledger)

        fcs_score = 0
        fcs_reasons = []

        consensus_check = str(consensus).lower()
        if 'buy' in consensus_check:
            fcs_score = operator.add(fcs_score, 2)
            fcs_reasons.append("Bullish Analyst Consensus (+2)")
        elif 'sell' in consensus_check:
            fcs_score = operator.add(fcs_score, neg_two)
            fcs_reasons.append("Bearish Analyst Consensus (" + dash + "2)")

        if price_target != 'N/A' and current_price != 'N/A' and current_price > 0:
            upside = operator.mul(operator.truediv(operator.sub(price_target, current_price), current_price), 100)
            if upside > 15:
                fcs_score = operator.add(fcs_score, 2)
                fcs_reasons.append("High Implied Upside (+2)")
            elif upside < 0:
                fcs_score = operator.add(fcs_score, neg_three)
                fcs_reasons.append("Negative Implied Upside (" + dash + "3)")

        if next_earnings != 'Unknown':
            try:
                ne_date = datetime.datetime.strptime(next_earnings, date_format).date()
                today_date = datetime.datetime.today().date()
                days_to_earn = operator.sub(ne_date, today_date).days
                if 0 <= days_to_earn <= 21:
                    fcs_score = operator.add(fcs_score, 1)
                    fcs_reasons.append("Imminent Earnings Catalyst (+1)")
            except Exception:
                pass

        fcs_score = max(neg_five, min(5, fcs_score))
        fcs_rationale = " | ".join(fcs_reasons) if fcs_reasons else "No major forward catalysts identified."
        
        return {
            "beta": beta, "peg": peg, "ps": ps, "de": de, "fwd_pe": fwd_pe,
            "roe": roe, "fcf_yield": fcf_yield, "sector": sector, "market_cap": market_cap,
            "pct_off_52w_high": pct_off_52w_high,
            "eps_estimated": eps_estimated, "revenue_estimated": revenue_estimated,
            "target_high": target_high, "target_low": target_low,
            "3m_trend": trend_3m, "3y_cagr": cagr_3y, "rev_growth": rev_growth, "eps_growth": eps_growth,
            "current_price": current_price, "consensus": consensus, "price_target": price_target,
            "next_earnings": next_earnings, "fcs_score": fcs_score, "fcs_rationale": fcs_rationale,
            "image": image_url
        }

async def get_fmp_macro(api_key: str, session: aiohttp.ClientSession) -> dict:
    tlt_url = f"https://financialmodelingprep.com/stable/quote?symbol=TLT&apikey={api_key}"
    vxx_url = f"https://financialmodelingprep.com/stable/quote?symbol=VXX&apikey={api_key}"
    try:
        tlt_data, vxx_data = await asyncio.gather(
            fetch_json_endpoint(session, tlt_url),
            fetch_json_endpoint(session, vxx_url)
        )
        tlt_price = safe_float(tlt_data[0].get('price')) if tlt_data else 'N/A'
        vxx_price = safe_float(vxx_data[0].get('price')) if vxx_data else 'N/A'
        return {"TLT": tlt_price, "VXX": vxx_price}
    except Exception:
        logger.error("Macro economic structural data fetch failed.")
        return {"TLT": "N/A", "VXX": "N/A"}