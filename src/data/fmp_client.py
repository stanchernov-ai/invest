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

async def fetch_momentum_trend(symbol: str, api_key: str, session: aiohttp.ClientSession, telemetry: dict = None) -> float:
    # 3-month price momentum from FMP's stable EOD endpoint. The legacy v3
    # endpoint is 403 on the starter tier and yfinance is unreliable, so we
    # source this directly from the same FMP feed as the rest of the metrics.
    end_date = datetime.datetime.today()
    start_date = end_date - datetime.timedelta(days=95)
    start_str = start_date.strftime("%Y" + dash + "%m" + dash + "%d")
    end_str = end_date.strftime("%Y" + dash + "%m" + dash + "%d")
    url = f"https://financialmodelingprep.com/stable/historical-price-eod/light?symbol={symbol}&from={start_str}&to={end_str}&apikey={api_key}"

    trend = 'N/A'
    try:
        data = await fetch_json_endpoint(session, url)
        # Records are newest-first: index 0 is the latest close, [-1] the oldest.
        prices = [d.get("price") for d in data if isinstance(d, dict) and d.get("price") is not None]
        if len(prices) >= 2:
            end_price = float(prices[0])
            start_price = float(prices[~0])
            if start_price > 0:
                trend = round(((end_price - start_price) / start_price) * 100, 2)
    except Exception:
        logger.warning(f"FMP momentum fetch failed for {symbol}")
        trend = 'N/A'

    if telemetry is not None:
        if symbol not in telemetry: telemetry[symbol] = {}
        telemetry[symbol]["3m_momentum"] = {
            "source": "fmp_stable_eod_light",
            "url": url.replace(api_key, "REDACTED"),
            "response": trend,
        }
    return trend

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

async def get_fmp_advanced_metrics(symbol: str, api_key: str, session: aiohttp.ClientSession, telemetry_ledger: dict = None) -> dict:
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
    else:
        yf_info = await fetch_yfinance_fallback(symbol, telemetry_ledger)
        if not yf_info:
            raise FatalDataError(f"Complete Oracle Failure for {symbol}. All data sources exhausted.")
        is_etf = yf_info.get("quoteType", "") == "ETF"
        beta = safe_float(yf_info.get('beta'))

    trend_3m = await fetch_momentum_trend(symbol, api_key, session, telemetry_ledger)

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

        return {
            "beta": beta, "peg": "N/A", "ps": "N/A", "de": "N/A", "fwd_pe": "N/A", 
            "3m_trend": trend_3m, "3y_cagr": "N/A", "rev_growth": "N/A", "eps_growth": "N/A",
            "current_price": current_price, "consensus": "N/A", "price_target": "N/A", 
            "next_earnings": "Unknown", "fcs_score": 0, "fcs_rationale": "ETF Structural Exemption."
        }

    else:
        urls = {
            "quote": f"{base_url}/quote?symbol={symbol}&apikey={api_key}",
            "met": f"{base_url}/key{dash}metrics{dash}ttm?symbol={symbol}&apikey={api_key}",
            "ratio": f"{base_url}/ratios{dash}ttm?symbol={symbol}&apikey={api_key}",
            "rating": f"{base_url}/rating?symbol={symbol}&apikey={api_key}",
            "pt": f"{base_url}/price{dash}target{dash}consensus?symbol={symbol}&apikey={api_key}",
            "earn": f"{base_url}/earning_calendar?symbol={symbol}&apikey={api_key}",
            "growth": f"{base_url}/financial{dash}growth?symbol={symbol}&apikey={api_key}"
        }
        
        tasks = {k: fetch_json_endpoint(session, url) for k, url in urls.items()}
        res = await asyncio.gather(*tasks.values(), return_exceptions=True)
        data_map = dict(zip(tasks.keys(), res))

        if telemetry_ledger is not None:
            for k, v in data_map.items():
                exact_url = urls.get(k, "Unknown URL")
                telemetry_ledger[symbol][k] = {"url": exact_url.replace(api_key, "REDACTED"), "response": f"ERROR: {str(v)}" if isinstance(v, Exception) else v}

        quote_data = data_map.get("quote", [])
        ratio_data = data_map.get("ratio", [])
        rating_data = data_map.get("rating", [])
        pt_data = data_map.get("pt", [])
        earn_data = data_map.get("earn", [])
        growth_data = data_map.get("growth", [])

        if isinstance(quote_data, Exception) or not quote_data or isinstance(ratio_data, Exception) or not ratio_data:
            if not yf_info:
                yf_info = await fetch_yfinance_fallback(symbol, telemetry_ledger)

        if not isinstance(quote_data, Exception) and quote_data:
            current_price = safe_float(quote_data[0].get('price'))
        else:
            current_price = safe_float(yf_info.get('currentPrice', yf_info.get('regularMarketPrice')))

        if current_price == 'N/A' or current_price == 0:
            raise FatalDataError("Quote data empty.")

        if not isinstance(ratio_data, Exception) and ratio_data:
            fwd_pe = safe_float(ratio_data[0].get('priceToEarningsRatioTTM'))
            peg = safe_float(ratio_data[0].get('priceToEarningsGrowthRatioTTM'))
            ps = safe_float(ratio_data[0].get('priceToSalesRatioTTM'))
            de = safe_float(ratio_data[0].get('debtToEquityRatioTTM'))
        else:
            fwd_pe = safe_float(yf_info.get('forwardPE', yf_info.get('trailingPE')))
            peg = safe_float(yf_info.get('pegRatio'))
            ps = safe_float(yf_info.get('priceToSalesTrailing12Months'))
            de = safe_float(yf_info.get('debtToEquity'))

        if not isinstance(rating_data, Exception) and rating_data:
            consensus = rating_data[0].get('ratingRecommendation', 'N/A')
        else:
            consensus = yf_info.get('recommendationKey', 'N/A').replace('_', ' ').title()

        if not isinstance(pt_data, Exception) and pt_data:
            price_target = safe_float(pt_data[0].get('targetConsensus'))
        else:
            price_target = safe_float(yf_info.get('targetMeanPrice'))

        if not isinstance(growth_data, Exception) and growth_data:
            rev_growth = safe_float(growth_data[0].get('revenueGrowth'))
            eps_growth = safe_float(growth_data[0].get('epsgrowth'))
        else:
            rev_growth = safe_float(yf_info.get('revenueGrowth'))
            eps_growth = safe_float(yf_info.get('earningsGrowth'))

        next_earnings = 'Unknown'
        if not isinstance(earn_data, Exception) and earn_data:
            today_str = datetime.datetime.today().strftime(date_format)
            future_earnings = [e for e in earn_data if e.get('date', '') >= today_str]
            if future_earnings:
                future_earnings.sort(key=lambda x: x['date'])
                next_earnings = future_earnings[0].get('date', 'Unknown')

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
            "3m_trend": trend_3m, "3y_cagr": "N/A", "rev_growth": rev_growth, "eps_growth": eps_growth,
            "current_price": current_price, "consensus": consensus, "price_target": price_target, 
            "next_earnings": next_earnings, "fcs_score": fcs_score, "fcs_rationale": fcs_rationale
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