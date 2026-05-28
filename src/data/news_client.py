import aiohttp
import asyncio
import logging

logger = logging.getLogger(__name__)

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
                headlines.append(f"[{sym}]: {title}")
                
            return "\n".join(headlines)
    except Exception as e:
        logger.error("Failed to fetch fundamental news.")
        return "News fetch failed."