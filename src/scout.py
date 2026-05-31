import os
import json
import logging
import datetime
import operator
import requests
from bs4 import BeautifulSoup

from src.config.settings import DATA_DIR, settings, now_local

logger = logging.getLogger(__name__)
dash = chr(45)

YAHOO_SOURCE = "yahoo"
YAHOO_TRENDING_CACHE_FILE = "yahoo_trending_cache.json"

# At most one Yahoo HTML scrape per calendar day (BOARDROOM_TIMEZONE). FMP fallback does not
# hit Yahoo and may run when the scrape returns empty on a cache miss.
YAHOO_SCRAPE_ENABLED = os.getenv("YAHOO_SCRAPE_ENABLED", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Stable tier (v3 /api/v3/stock-screener returns 403 on Starter as of 2026-05).
FMP_COMPANY_SCREENER_URL = (
    "https://financialmodelingprep.com/stable/company-screener"
    "?marketCapMoreThan=10000000000&volumeMoreThan=2000000"
    "&sector=Technology&limit=25"
)


def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, mode="r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _yahoo_cache_path(data_dir: str | None = None) -> str:
    return os.path.join(data_dir or DATA_DIR, YAHOO_TRENDING_CACHE_FILE)


def _cache_date_key() -> str:
    return now_local().strftime("%Y%m%d")


def _load_trending_cache(data_dir: str | None = None) -> dict | None:
    cached = load_json(_yahoo_cache_path(data_dir))
    if not isinstance(cached, dict):
        return None
    if cached.get("date") != _cache_date_key():
        return None
    symbols = cached.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        return None
    return cached


def _save_trending_cache(symbols: list[str], *, source: str, data_dir: str | None = None) -> None:
    data_dir = data_dir or DATA_DIR
    os.makedirs(data_dir, exist_ok=True)
    payload = {
        "date": _cache_date_key(),
        "fetched_at": now_local().isoformat(),
        "source": source,
        "symbols": [str(s).strip().upper() for s in symbols if s],
    }
    with open(_yahoo_cache_path(data_dir), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info(
        "Yahoo trending cache saved (%d symbols, source=%s, date=%s).",
        len(payload["symbols"]),
        source,
        payload["date"],
    )


def build_pass_cooldown_set(verdicts: dict) -> set[str]:
    """Symbols in Pass cooldown from chairman watchlist verdict memory."""
    cooldown_set: set[str] = set()
    today = datetime.datetime.now()
    date_format = "%Y%m%d"

    for sym, history in (verdicts or {}).items():
        if not history:
            continue
        last_run = history[~0]
        if last_run.get("verdict") != "Pass":
            continue
        try:
            run_date = datetime.datetime.strptime(last_run["date"], date_format)
            days_passed = operator.sub(today, run_date).days
            penalty_days = 14 if last_run.get("unanimous_pass", False) else 7
            if days_passed < penalty_days:
                cooldown_set.add(str(sym).strip().upper())
        except Exception:
            pass
    return cooldown_set


def scrape_yahoo_trending():
    """Live HTML scrape — call at most once per day via ``_fetch_trending_symbol_list``."""
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
        logger.error("Failed to scrape Yahoo trending: %s", e)
        return []


def _fetch_trending_from_fmp() -> list[str]:
    api_key = settings.FMP_API_KEY
    if not api_key:
        return []
    try:
        url = f"{FMP_COMPANY_SCREENER_URL}&apikey={api_key}"
        actives = requests.get(url, timeout=15).json()
        return [str(item.get("symbol")).strip().upper() for item in actives if item.get("symbol")]
    except Exception:
        logger.warning("Scout FMP company-screener fallback failed.")
        return []


def _fetch_trending_symbol_list(
    data_dir: str | None = None,
    *,
    force_refresh: bool = False,
) -> list[str]:
    """Return trending symbol list; Yahoo HTML at most once per local calendar day."""
    if not force_refresh:
        cached = _load_trending_cache(data_dir)
        if cached:
            logger.info(
                "Using cached trending list (%d symbols, source=%s, date=%s).",
                len(cached["symbols"]),
                cached.get("source", "unknown"),
                cached.get("date"),
            )
            return list(cached["symbols"])

    trending_tickers: list[str] = []
    source = "static_fallback"

    if YAHOO_SCRAPE_ENABLED:
        trending_tickers = scrape_yahoo_trending()
        if trending_tickers:
            source = "yahoo"
    else:
        logger.info("Yahoo scrape disabled (YAHOO_SCRAPE_ENABLED=false); using FMP/static fallback.")

    if not trending_tickers:
        logger.warning("Yahoo trending empty or disabled; trying FMP screener.")
        trending_tickers = _fetch_trending_from_fmp()
        if trending_tickers:
            source = "fmp_screener"

    if not trending_tickers:
        trending_tickers = ["NVDA", "MSFT", "PLTR", "AMZN", "BABA"]
        source = "static_fallback"

    normalized = [str(s).strip().upper() for s in trending_tickers if s]
    _save_trending_cache(normalized, source=source, data_dir=data_dir)
    return normalized


def build_yahoo_discovery(
    owned_tickers: set[str],
    cooldown_set: set[str],
    *,
    max_symbols: int = 15,
    data_dir: str | None = None,
    force_refresh: bool = False,
) -> dict[str, dict]:
    """Trending discovery minus owned and Pass cooldown (Yahoo scrape cached daily)."""
    owned = {str(s).strip().upper() for s in (owned_tickers or set())}
    watchlist: dict[str, dict] = {}

    for sym in _fetch_trending_symbol_list(data_dir, force_refresh=force_refresh):
        if not sym or len(watchlist) >= max_symbols:
            break
        if sym in owned or sym in cooldown_set or sym in watchlist:
            continue
        watchlist[sym] = {
            "source": YAHOO_SOURCE,
            "price": 0.0,
        }
    return watchlist


def run_scout_pipeline(owned_tickers=None, user_id="stan"):
    """Legacy entry — writes Yahoo-only slice to daily_target_list.json."""
    logger.info("Scout Engine Booting. Hunting for organic Alpha.")
    data_dir = DATA_DIR
    os.makedirs(data_dir, exist_ok=True)

    verdicts_file = os.path.join(data_dir, "board_verdicts.json")
    target_file = os.path.join(data_dir, "daily_target_list.json")

    verdicts = load_json(verdicts_file)
    owned_tickers = {str(s).strip().upper() for s in (owned_tickers or set())}
    cooldown_set = build_pass_cooldown_set(verdicts)

    watchlist = build_yahoo_discovery(owned_tickers, cooldown_set, data_dir=data_dir)

    with open(target_file, "w") as f:
        json.dump(watchlist, f, indent=4)

    logger.info("Scout Engine finished locking targets.")


if __name__ == "__main__":
    run_scout_pipeline()
