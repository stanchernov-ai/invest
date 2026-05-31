"""Job 1 - PREPARE.

All pre-debate data work: sync inputs, parse the brokerage ledger, fetch FMP
metrics / news / macro, compute time-weighted returns, and assemble the board's
mega-prompt. Ends with a deterministic price gate ($0.00 kill switch) and writes
the prepare checkpoint the debate phase consumes.
"""
import os
import json
import asyncio
import logging

import aiohttp

from src import pipeline
from src import history
from src import verdict_memory
from src.data.review_universe import build_review_universe, persist_daily_target_list
from src import storage_client
from src.output import reporting
from src.output import notifier
from src.data.news_client import fetch_ticker_news
from src.data.fmp_client import get_fmp_advanced_metrics, get_fmp_macro, prefetch_eod_cache
from src.core.schemas import generate_dynamic_mandate
from src.core.data_oracle import build_price_feed, validate_price_feed
from src.core import agent_activity
from src.config.settings import settings, DATA_DIR, now_local
from src.logging_setup import configure_logging

logger = configure_logging()

_BENCHMARK_SYMBOLS = frozenset({"SPY", "QQQ"})


def _rel_strength_3m(adv: dict, qqq_3m: float) -> str:
    t = adv.get("3m_trend")
    if t in (None, "N/A"):
        return "N/A"
    try:
        return reporting.fmt(float(t) - float(qqq_3m))
    except (ValueError, TypeError):
        return "N/A"


def _format_equity_kpi_line(adv: dict, qqq_3m: float) -> str:
    """Single-line fundamentals block shared by portfolio and watchlist."""
    rs = _rel_strength_3m(adv, qqq_3m)
    return (
        f"PE: {adv.get('fwd_pe', 'N/A')} | PEG: {adv.get('peg', 'N/A')} | P/S: {adv.get('ps', 'N/A')} | D/E: {adv.get('de', 'N/A')} | "
        f"Beta: {adv.get('beta', 'N/A')} | ROE: {reporting.fmt(adv.get('roe', 'N/A'))} | FCF Yield: {reporting.fmt(adv.get('fcf_yield', 'N/A'))} | "
        f"Sector: {adv.get('sector', 'N/A')} | Analyst: {adv.get('consensus', 'N/A')} | "
        f"3M Trend: {reporting.fmt(adv.get('3m_trend', 'N/A'))} | vs QQQ 3M: {rs} | Off 52W High: {reporting.fmt(adv.get('pct_off_52w_high', 'N/A'))} | "
        f"Rev Growth: {reporting.fmt(adv.get('rev_growth', 'N/A'))} | EPS Growth: {reporting.fmt(adv.get('eps_growth', 'N/A'))}"
    )


def _market_regime_block(macro_data: dict, portfolio_3m: float, qqq_3m: float, spy_3m: float) -> str:
    tlt = macro_data.get("TLT", "N/A")
    vxx = macro_data.get("VXX", "N/A")
    return (
        f"=== MARKET REGIME ===\n"
        f"Portfolio 3M (TWR): {reporting.fmt(portfolio_3m)} | QQQ 3M: {reporting.fmt(qqq_3m)} | SPY 3M: {reporting.fmt(spy_3m)}\n"
        f"Macro hedges — TLT: {reporting.fmt_dol(tlt) if tlt != 'N/A' else 'N/A'} | VXX: {reporting.fmt_dol(vxx) if vxx != 'N/A' else 'N/A'}\n\n"
    )


async def run_prepare(run_id: str = None, user_id: str = "stan") -> dict:
    """Execute the prepare phase. Returns {'run_id', 'status', 'oracle'}.

    On success writes the 'prepare' checkpoint and marks the phase complete so the
    caller can trigger the debate job."""
    configure_logging()
    if run_id is None:
        run_id = now_local().strftime('%Y%m%d_%H%M%S')

    logger.info(f"[PREPARE] Starting data preparation for run {run_id}.")
    started = now_local()
    agent_activity.reset()
    storage_client.begin_run_status(run_id, started.isoformat(), user_id=user_id)
    storage_client.mark_phase(run_id, "prepare", "running", started_at=started.isoformat(), user_id=user_id)

    api_telemetry = {}

    if not settings.validate():
        logger.error("FATAL ABORT: Required environment variables missing.")
        storage_client.mark_phase(run_id, "prepare", "failed",
                                  finished_at=now_local().isoformat(),
                                  error="missing environment variables",
                                  user_id=user_id)
        return {"run_id": run_id, "status": "failed", "oracle": None}

    try:
        storage_client.sync_inputs_from_cloud(user_id=user_id)

        master_ledger, total_portfolio_value = pipeline.process_portfolios()
        account_holdings = pipeline.build_account_holdings()

        keys_to_delete = [sym for sym, data in master_ledger.items() if data["Total"] < 50.0]
        for k in keys_to_delete:
            del master_ledger[k]

        watchlist_data = build_review_universe(
            master_ledger.keys(),
            verdicts_history=verdict_memory.load_board_verdicts(user_id=user_id),
        )
        persist_daily_target_list(watchlist_data)

        all_symbols = list(set(list(master_ledger.keys()) + list(watchlist_data.keys())))
        clean_symbols = [s for s in all_symbols if s != "BRK_LINK" and not s.startswith("922")]

        async with aiohttp.ClientSession() as session:
            macro_data = await get_fmp_macro(settings.FMP_API_KEY, session)
            api_telemetry['MACRO_TLT_VXX'] = macro_data

            news_feed = await fetch_ticker_news(clean_symbols, settings.FMP_API_KEY, session)
            api_telemetry['FUNDAMENTAL_NEWS'] = news_feed

            history_symbols = history.collect_symbol_universe(DATA_DIR)
            eod_symbols = sorted(
                set(clean_symbols) | history_symbols | _BENCHMARK_SYMBOLS | {"TLT", "VXX"}
            )
            logger.info(f"Prefetching shared EOD cache for {len(eod_symbols)} symbols.")
            eod_cache = await prefetch_eod_cache(
                eod_symbols, settings.FMP_API_KEY, session, max_concurrency=5
            )
            api_telemetry["EOD_CACHE"] = {
                "symbol_count": len(eod_symbols),
                "fmp_unique": len({s.replace('.', '-') for s in eod_symbols}),
            }

            qqq_adv = await get_fmp_advanced_metrics(
                "QQQ", settings.FMP_API_KEY, session, api_telemetry, eod_cache=eod_cache
            )
            spy_adv = await get_fmp_advanced_metrics(
                "SPY", settings.FMP_API_KEY, session, api_telemetry, eod_cache=eod_cache
            )

            symbols_to_fetch = [s for s in clean_symbols if s not in _BENCHMARK_SYMBOLS]
            adv_sem = asyncio.Semaphore(5)

            async def _fetch_adv(sym):
                async with adv_sem:
                    return await get_fmp_advanced_metrics(
                        sym, settings.FMP_API_KEY, session, api_telemetry, eod_cache=eod_cache
                    )

            results_list = await asyncio.gather(*[_fetch_adv(sym) for sym in symbols_to_fetch], return_exceptions=True)

            advanced_data = {"QQQ": qqq_adv, "SPY": spy_adv}
            for sym, res in zip(symbols_to_fetch, results_list):
                if isinstance(res, Exception):
                    error_msg = f"FATAL ABORT: Advanced metrics corrupted for {sym}. Killing pipeline to prevent AI hallucination."
                    logger.error(error_msg)
                    notifier.send_error_alert(error_msg)
                    storage_client.mark_phase(run_id, "prepare", "failed",
                                              finished_at=now_local().isoformat(),
                                              error=f"advanced metrics corrupted for {sym}",
                                              user_id=user_id)
                    return {"run_id": run_id, "status": "failed", "oracle": None}
                advanced_data[sym] = res

            account_returns = await history.build_account_returns(
                DATA_DIR, settings.FMP_API_KEY, session, eod_cache=eod_cache
            )

        spy_price = spy_adv.get("current_price", 0.0)
        total_portfolio_value = 0.0
        for sym, data in master_ledger.items():
            shares = data.get("Shares", 0)
            if shares > 0:
                adv = advanced_data.get(sym, {})
                live_price = adv.get("current_price", data["Total"] / shares)
                old_total = data["Total"]
                live_total = live_price * shares
                if old_total > 0:
                    ratio = live_total / old_total
                    data["Taxable"] *= ratio
                    data["Roth"] *= ratio
                    data["401K"] *= ratio
                data["Total"] = live_total
                data["Unrealized"] = live_total - data["Cost_Basis"]
                data["Personal_Return_Pct"] = (data["Unrealized"] / data["Cost_Basis"]) * 100 if data["Cost_Basis"] > 0 else 0.0
            total_portfolio_value += data["Total"]

        for sym, d in watchlist_data.items():
            adv = advanced_data.get(sym, {})
            if adv.get("current_price", 0.0) > 0:
                d["price"] = adv["current_price"]

        history_path = os.path.join(DATA_DIR, "portfolio_history.json")
        history_data = (account_returns or {}).get("benchmark_history") or {}
        if history_data:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(history_path, "w") as f:
                json.dump(history_data, f)
            storage_client.save_report("portfolio_history.json", json.dumps(history_data), user_id=user_id)
        elif spy_price > 0 and total_portfolio_value > 0:
            if os.path.exists(history_path):
                try:
                    with open(history_path, "r") as f:
                        history_data = json.load(f)
                except Exception:
                    history_data = {}
            today_str = now_local().strftime('%Y%m%d')
            qqq_price = qqq_adv.get("current_price", 0.0)
            history_data[today_str] = {
                "portfolio": total_portfolio_value,
                "spy": spy_price,
                "qqq": qqq_price,
            }
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(history_path, "w") as f:
                json.dump(history_data, f)
            storage_client.save_report("portfolio_history.json", json.dumps(history_data), user_id=user_id)

        if account_returns:
            try:
                storage_client.save_report("portfolio_returns.json", json.dumps(account_returns), user_id=user_id)
            except Exception:
                logger.warning("Could not persist portfolio_returns.json")

        live_qqq_trend = qqq_adv.get("3m_trend", 0.0)
        live_spy_trend = spy_adv.get("3m_trend", 0.0)
        try:
            qqq_3m_float = float(live_qqq_trend) if live_qqq_trend not in (None, "N/A") else 0.0
        except (ValueError, TypeError):
            qqq_3m_float = 0.0
        portfolio_3m_trend = 0.0
        portfolio_12m_twr = 0.15
        if account_returns and account_returns.get("returns"):
            total_returns = account_returns["returns"].get("Total", {})
            portfolio_3m_trend = total_returns.get("3m", 0.0) or 0.0
            raw_12m = total_returns.get("12m")
            if raw_12m is not None:
                try:
                    portfolio_12m_twr = float(raw_12m) / 100.0
                except (ValueError, TypeError):
                    pass

        regime_block = _market_regime_block(macro_data, portfolio_3m_trend, qqq_3m_float, live_spy_trend)

        tradeable_tickers = [sym for sym in master_ledger.keys() if sym != "BRK_LINK" and not sym.startswith("922")]
        sorted_ledger = sorted(master_ledger.items(), key=lambda x: x[1]["Total"], reverse=True)
        live_mandate = generate_dynamic_mandate(total_portfolio_value, portfolio_12m_twr)

        divisor = total_portfolio_value if total_portfolio_value > 0 else 1.0
        heavy_tickers = [sym for sym, data in sorted_ledger if (data["Total"] / divisor) * 100 > 33.0 and sym in tradeable_tickers]

        board_portfolio_lines = []
        for sym, data in sorted_ledger:
            pct = (data["Total"] / divisor) * 100
            shares = data.get('Shares', 0.0)
            adv = advanced_data.get(sym, {})
            live_price = adv.get("current_price", data["Total"] / shares if shares > 0 else 0.0)
            pt = adv.get('price_target', 'N/A')
            implied_upside = f"{((float(pt) - live_price) / live_price) * 100:.2f}%" if pt != 'N/A' and live_price > 0 else "N/A"
            earn_extra = ""
            if adv.get("eps_estimated", "N/A") != "N/A":
                earn_extra = f" | EPS Est: {adv.get('eps_estimated')}"
            line = (
                f"### {sym} ###\n"
                f"Position: {reporting.fmt_dol(data['Total'])} ({pct:.2f}% of portfolio)\n"
                f"Purchase Date: {data.get('Purchase_Date', 'Unknown')}\n"
                f"Current Price: {reporting.fmt_dol(live_price)} | Target: {reporting.fmt_dol(pt)} (Upside: {implied_upside}) | PT Range: {reporting.fmt_dol(adv.get('target_low', 'N/A'))}–{reporting.fmt_dol(adv.get('target_high', 'N/A'))}\n"
                f"3Y Return: {reporting.fmt(adv.get('3y_cagr', 'N/A'))}\n"
                f"{_format_equity_kpi_line(adv, qqq_3m_float)}\n"
                f"Forward Catalyst Score (FCS): {adv.get('fcs_score', 0)}/5 ({adv.get('fcs_rationale', 'No catalysts')}) | "
                f"Next Earnings: {adv.get('next_earnings', 'Unknown')}{earn_extra}\n"
            )
            board_portfolio_lines.append(line)

        portfolio_str = "\n".join(board_portfolio_lines)
        wl_lines = []
        for sym, d in watchlist_data.items():
            adv = advanced_data.get(sym, {})
            pt = adv.get('price_target', 'N/A')
            wl_live_price = float(d.get('price', 1.0))
            implied_upside = f"{((float(pt) - wl_live_price) / wl_live_price) * 100:.2f}%" if pt != 'N/A' and wl_live_price > 0 else "N/A"
            fcs_score_val = adv.get('fcs_score', 0)
            fcs_rationale_val = adv.get('fcs_rationale', '')
            next_earn_val = adv.get('next_earnings', 'Unknown')
            wl_lines.append(
                f"* {sym}: Price: ${d['price']} | Target: {reporting.fmt_dol(pt)} (Upside: {implied_upside}) | "
                f"{_format_equity_kpi_line(adv, qqq_3m_float)} | "
                f"FCS: {fcs_score_val}/5 ({fcs_rationale_val}) | Next Earnings: {next_earn_val}."
            )
        watchlist_str = "\n".join(wl_lines) if wl_lines else "None available."

        mega_prompt = (
            f"[CURRENT SYSTEM DATE: {now_local().strftime('%B %d, %Y')}]\n\n"
            f"{regime_block}"
            f"=== LIVE MARKET HEADLINES ===\n{news_feed}\n\n"
            f"=== CURRENT PORTFOLIO ===\n{portfolio_str}\n\n"
            f"=== APPROVED WATCHLIST TARGETS ===\n{watchlist_str}\n"
        )

        raw_log_header = (
            f"# RAW DEBATE LOG BACKGROUND AUDIT\n\n"
            f"=== CURRENT PORTFOLIO ===\n{portfolio_str}\n\n"
            f"=== APPROVED WATCHLIST TARGETS ===\n{watchlist_str}\n\n\n"
        )

        # --- Prepare-phase price gate (deterministic; no LLM) ---
        price_feed = build_price_feed(master_ledger, watchlist_data, advanced_data)
        oracle = validate_price_feed(price_feed)
        logger.info("Prepare-phase price gate: is_valid=%s", oracle["is_valid"])
        if not oracle["is_valid"]:
            error_msg = f"DATA ORACLE SECURITY ABORT (prepare). Reason: {oracle['reason']}"
            logger.error(error_msg)
            notifier.send_error_alert(error_msg)
            storage_client.mark_phase(run_id, "prepare", "failed",
                                      finished_at=now_local().isoformat(),
                                      error="data oracle validation failed",
                                      oracle_reason=oracle["reason"],
                                      user_id=user_id)
            return {"run_id": run_id, "status": "failed", "oracle": oracle}

        api_telemetry['AGENT_ACTIVITY'] = agent_activity.snapshot()

        checkpoint = {
            "run_id": run_id,
            "mega_prompt": mega_prompt,
            "live_mandate": live_mandate,
            "heavy_tickers": heavy_tickers,
            "all_symbols": clean_symbols,
            "total_portfolio_value": total_portfolio_value,
            "portfolio_holdings": {sym: data["Total"] for sym, data in master_ledger.items()},
            "purchase_dates": {sym: data.get("Purchase_Date", "Unknown") for sym, data in master_ledger.items()},
            "sorted_ledger": sorted_ledger,
            "account_holdings": account_holdings,
            "account_returns": account_returns,
            "history_data": history_data,
            "advanced_data": advanced_data,
            "live_qqq_trend": live_qqq_trend,
            "portfolio_3m_trend": portfolio_3m_trend,
            "raw_log_header": raw_log_header,
            "oracle": oracle,
            "price_feed": price_feed,
            "telemetry": api_telemetry,
        }
        storage_client.save_checkpoint(run_id, "prepare", checkpoint, user_id=user_id)
        storage_client.save_report(f"api_telemetry_{run_id}_prepare.json", json.dumps(api_telemetry, indent=4), user_id=user_id)

        finished = now_local()
        storage_client.mark_phase(run_id, "prepare", "success",
                                  started_at=started.isoformat(),
                                  finished_at=finished.isoformat(),
                                  duration_seconds=round((finished - started).total_seconds(), 1),
                                  user_id=user_id)
        logger.info(f"[PREPARE] Completed for run {run_id} in {round((finished - started).total_seconds(), 1)}s.")
        return {"run_id": run_id, "status": "success", "oracle": oracle}

    except Exception as e:
        logger.error(f"[PREPARE] Fatal exception: {e}")
        notifier.send_error_alert(f"Prepare phase failed: {e}")
        storage_client.mark_phase(run_id, "prepare", "failed",
                                  finished_at=now_local().isoformat(), error=str(e), user_id=user_id)
        return {"run_id": run_id, "status": "failed", "oracle": None}


if __name__ == "__main__":
    asyncio.run(run_prepare())
