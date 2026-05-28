import os
import json
import logging
import datetime
import operator
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
dash = chr(45)

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def scrape_yahoo_trending():
    url = f"https://finance.yahoo.com/trending{dash}tickers"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        tickers = []
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if '/quote/' in href and '?' not in href:
                ticker = href.split('/quote/')[1].split('/')[0].upper()
                if ticker and ticker.isalpha() and len(ticker) <= 5 and ticker not in tickers:
                    tickers.append(ticker)
                    
        return tickers[:30]
        
    except Exception as e:
        logger.error("Failed to scrape pre market targets.")
        return []

def run_scout_pipeline():
    logger.info("Scout Engine Booting. Hunting for organic Alpha.")
    data_dir = "/tmp/data"
    os.makedirs(data_dir, exist_ok=True)
    
    ledger_file = os.path.join(data_dir, "ledger_state.json")
    verdicts_file = os.path.join(data_dir, "board_verdicts.json")
    target_file = os.path.join(data_dir, "daily_target_list.json")
    
    portfolio = load_json(ledger_file)
    verdicts = load_json(verdicts_file)
    
    owned_tickers = set(portfolio.keys())
    cooldown_set = set()
    today = datetime.datetime.now()
    date_format = "%Y%m%d"
    
    for sym, history in verdicts.items():
        if not history: continue
        last_run = history[~0]
        
        if last_run.get("verdict") == "Pass":
            try:
                run_date = datetime.datetime.strptime(last_run["date"], date_format)
                days_passed = operator.sub(today, run_date).days
                penalty_days = 14 if last_run.get("unanimous_pass", False) else 7
                if days_passed < penalty_days:
                    cooldown_set.add(sym)
            except Exception:
                pass
                
    watchlist = {}
    
    trending_tickers = scrape_yahoo_trending()
    
    api_key = os.getenv("FMP_API_KEY")
    if not trending_tickers and api_key:
        logger.warning("Scraper returned empty. Falling back to FMP API Screener.")
        try:
            url = f"https://financialmodelingprep.com/api/v3/stock{dash}screener?marketCapMoreThan=10000000000&volumeMoreThan=2000000&sector=Technology&limit=25&apikey={api_key}"
            actives = requests.get(url, timeout=15).json()
            trending_tickers = [item.get("symbol") for item in actives if item.get("symbol")]
        except Exception:
            logger.warning("Scout FMP API Fallback Failed.")
            trending_tickers = ["NVDA", "MSFT", "PLTR", "AMZN", "BABA"]
            
    for sym in trending_tickers:
        if not sym or len(watchlist) >= 15: break
        if sym in owned_tickers or sym in cooldown_set or sym in watchlist: 
            continue
        
        watchlist[sym] = {
            "source": "Autonomous Scout Engine",
            "price": 1.0 
        }
            
    with open(target_file, "w") as f:
        json.dump(watchlist, f, indent=4)
        
    logger.info("Scout Engine finished locking targets.")

if __name__ == "__main__":
    run_scout_pipeline()