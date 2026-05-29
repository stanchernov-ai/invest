import aiohttp
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _format_published_date(raw) -> str:
    """Normalize FMP stock_news date fields to YYYY-MM-DD for the debate prompt."""
    if raw is None or raw == "":
        return ""
    if isinstance(raw, (int, float)):
        try:
            ts = raw / 1000 if raw > 1e12 else raw
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        except (ValueError, OSError, OverflowError):
            return ""
    text = str(raw).strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:26].replace("Z", ""), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text[:10] if len(text) >= 10 else text


async def fetch_ticker_news(tickers: list, api_key: str, session: aiohttp.ClientSession):
    if not tickers:
        return "No recent news."
        
    ticker_string = ",".join(tickers[:20])
    url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={ticker_string}&limit=15&apikey={api_key}"
    
    try:
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                return "News feed unavailable."
            data = await response.json()
            
            if not data or not isinstance(data, list):
                return "No recent news."
                
            headlines = []
            for article in data:
                sym = article.get("symbol", "UNKNOWN")
                title = article.get("title", "")
                pub = _format_published_date(
                    article.get("publishedDate") or article.get("date") or article.get("published_date")
                )
                if pub:
                    headlines.append(f"[{sym}] ({pub}): {title}")
                else:
                    headlines.append(f"[{sym}]: {title}")

            return "\n".join(headlines)
    except Exception as e:
        logger.error("Failed to fetch fundamental news.")
        return "News fetch failed."