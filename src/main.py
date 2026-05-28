import os
import asyncio
import logging
import sys
import json
import aiohttp
from datetime import datetime
from google.genai import types

from src import pipeline
from src import scout
from src import storage_client
from src.data.news_client import fetch_ticker_news

from src.output import reporting
from src.output import notifier
from src.core.schemas import generate_dynamic_mandate
from src.core.engine import app
from src.data.fmp_client import get_fmp_advanced_metrics, get_fmp_macro
from src.config.settings import settings, DATA_DIR
from src.core.agents import call_gemini_async, agent_config, FAST_MODEL, FLASH_TOKEN_LIMIT

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
logger.addHandler(ch)

def parse_board_matrix(raw_messages, all_tickers):
    matrix = {ticker: {"buffett": "", "lynch": "", "livermore": "", "huang": "", "simons": ""} for ticker in all_tickers}
    for msg in raw_messages:
        content = msg.get("content", "")
        agent = None
        if "**Warren Buffett**" in content: agent = "buffett"
        elif "**Peter Lynch**" in content: agent = "lynch"
        elif "**Jesse Livermore**" in content: agent = "livermore"
        elif "**Jensen Huang**" in content: agent = "huang"
        elif "**Jim Simons**" in content: agent = "simons"
        if not agent: continue
        for line in content.split("\n"):
            if line.startswith("* **"):
                parts = line.split("**: ")
                if len(parts) > 1:
                    ticker = parts[0].replace("* **", "").strip()
                    verdict_full = parts[1].split(" ")[0].replace("*", "")
                    if "Strong" in parts[1]: verdict_full = "Strong Buy"
                    if ticker in matrix: matrix[ticker][agent] = verdict_full
    return matrix

def generate_matrix_markdown(matrix):
    md = "| Ticker | Buffett | Lynch | Livermore | Huang | Simons |\n|---|---|---|---|---|---|\n"
    for ticker, votes in matrix.items():
        if any(v != "" for v in votes.values()):
            md += f"| **{ticker}** | {votes['buffett']} | {votes['lynch']} | {votes['livermore']} | {votes['huang']} | {votes['simons']} |\n"
    return md

async def run_post_flight_qa(raw_log: str, chairman_json: str):
    logger.info("Initiating Post Flight QA Audit.")
    qa_prompt = f"RAW DEBATE LOG:\n{raw_log}\n\nFINAL CHAIRMAN ALLOCATION:\n{chairman_json}"
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=qa_prompt)])]
    
    tasks = []
    agent_keys = ["post_mortem_qa", "system_architect", "prompt_engineer"]
    for key in agent_keys:
        info = agent_config["board_members"][key]
        config_params = {"system_instruction": info["system_instruction"], "temperature": 0.15}
        if info["model"] == FAST_MODEL:
            config_params["max_output_tokens"] = FLASH_TOKEN_LIMIT
        tasks.append(call_gemini_async(info["model"], contents, types.GenerateContentConfig(**config_params), agent_name=key))
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    qa_report = ""
    for key, res in zip(agent_keys, results):
        role_name = agent_config["board_members"][key]["role"]
        qa_report += f"### {role_name} Report ###\n"
        if isinstance(res, Exception):
            qa_report += f"QA execution failed.\n\n"
        else:
            qa_report += f"{res.text.strip()}\n\n"
            
    return qa_report

async def main_batch():
    logger.info("Initializing high performance quantitative pipeline engine.")
    settings.validate()
    file_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    api_telemetry = {}

    try:
        storage_client.sync_inputs_from_cloud()
        
        target_path = os.path.join(DATA_DIR, "daily_target_list.json")
        if not os.path.exists(target_path): 
            scout.run_scout_pipeline()

        try:
            with open(target_path, "r") as f: watchlist_data = json.load(f)
        except Exception: 
            watchlist_data = {}

        master_ledger, total_portfolio_value, dummy_trend, dummy_trades, historical_verdicts, sector_weights = pipeline.process_portfolios()
        account_holdings = pipeline.build_account_holdings()
        
        keys_to_delete = [sym for sym, data in master_ledger.items() if data["Total"] < 50.0]
        for k in keys_to_delete: del master_ledger[k]
            
        all_symbols = list(set(list(master_ledger.keys()) + list(watchlist_data.keys())))
        clean_symbols = [s for s in all_symbols if s != "BRK_LINK" and not s.startswith("922")]

        async with aiohttp.ClientSession() as session:
            
            macro_data = await get_fmp_macro(settings.FMP_API_KEY, session)
            api_telemetry['MACRO_TLT_VXX'] = macro_data
            
            news_feed = await fetch_ticker_news(clean_symbols, settings.FMP_API_KEY, session)
            api_telemetry['FUNDAMENTAL_NEWS'] = news_feed
            
            qqq_adv = await get_fmp_advanced_metrics("QQQ", settings.FMP_API_KEY, session, api_telemetry)
            spy_adv = await get_fmp_advanced_metrics("SPY", settings.FMP_API_KEY, session, api_telemetry)
            
            tasks = [get_fmp_advanced_metrics(sym, settings.FMP_API_KEY, session, api_telemetry) for sym in clean_symbols]
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            advanced_data = {}
            for sym, res in zip(clean_symbols, results_list):
                if isinstance(res, Exception):
                    logger.error("FATAL ABORT: Advanced metrics corrupted. Killing pipeline to prevent AI hallucination.")
                    return
                advanced_data[sym] = res

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
        history_data = {}
        if os.path.exists(history_path):
            try:
                with open(history_path, "r") as f: history_data = json.load(f)
            except Exception: pass

        today_str = datetime.now().strftime('%Y%m%d')
        if spy_price > 0 and total_portfolio_value > 0:
            history_data[today_str] = {"portfolio": total_portfolio_value, "spy": spy_price}
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(history_path, "w") as f: json.dump(history_data, f)
            storage_client.save_report("portfolio_history.json", json.dumps(history_data))

        live_qqq_trend = qqq_adv.get("3m_trend", 0.0)
        tradeable_tickers = [sym for sym in master_ledger.keys() if sym != "BRK_LINK" and not sym.startswith("922")]
        sorted_ledger = sorted(master_ledger.items(), key=lambda x: x[1]["Total"], reverse=True)
        live_mandate = generate_dynamic_mandate(total_portfolio_value, 0.15)
        
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
            
            line = (
                f"### {sym} ###\n"
                f"Position: {reporting.fmt_dol(data['Total'])} ({pct:.2f}% of portfolio)\n"
                f"Purchase Date: {data.get('Purchase_Date', 'Unknown')}\n"
                f"Current Price: {reporting.fmt_dol(live_price)} | Target Price: {reporting.fmt_dol(pt)} (Implied Upside: {implied_upside})\n"
                f"3M Trend: {reporting.fmt(adv.get('3m_trend', 'N/A'))} | PE Ratio: {adv.get('fwd_pe', 'N/A')} | 3Y Return: {reporting.fmt(adv.get('3y_cagr', 'N/A'))}\n"
                f"1Y Rev Growth: {reporting.fmt(adv.get('rev_growth', 'N/A'))} | 1Y EPS Growth: {reporting.fmt(adv.get('eps_growth', 'N/A'))}\n"
                f"Forward Catalyst Score (FCS): {adv.get('fcs_score', 0)}/5 ({adv.get('fcs_rationale', 'No catalysts')}) | Next Earnings: {adv.get('next_earnings', 'Unknown')}\n"
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
            fwd_pe_val = adv.get('fwd_pe', 'N/A')
            
            wl_lines.append(
                f"* {sym}: Price: ${d['price']} | PE: {fwd_pe_val} | Target: {reporting.fmt_dol(pt)} (Upside: {implied_upside}) | 3M Trend: {reporting.fmt(adv.get('3m_trend', 'N/A'))} | Rev Growth: {reporting.fmt(adv.get('rev_growth', 'N/A'))} | EPS Growth: {reporting.fmt(adv.get('eps_growth', 'N/A'))} | FCS: {fcs_score_val}/5 ({fcs_rationale_val}) | Next Earnings: {next_earn_val}."
            )
            
        watchlist_str = "\n".join(wl_lines) if wl_lines else "None available."

        mega_prompt = (
            f"[CURRENT SYSTEM DATE: {datetime.now().strftime('%B %d, %Y')}]\n\n"
            f"=== LIVE MARKET HEADLINES ===\n{news_feed}\n\n"
            f"=== CURRENT PORTFOLIO ===\n{portfolio_str}\n\n"
            f"=== APPROVED WATCHLIST TARGETS ===\n{watchlist_str}\n"
        )

        initial_state = {"base_data_prompt": mega_prompt, "live_mandate": live_mandate, "heavy_tickers": heavy_tickers, "all_symbols": clean_symbols}
        
        raw_log_lines = [
            f"# RAW DEBATE LOG BACKGROUND AUDIT\n\n"
            f"=== CURRENT PORTFOLIO ===\n{portfolio_str}\n\n"
            f"=== APPROVED WATCHLIST TARGETS ===\n{watchlist_str}\n\n\n"
        ]
        
        c_data = {} 
        cos_data = {}
        red_team_data = {}
        raw_board_messages = []
        unicorn_trades = []
        is_approved_flag = False
        
        async for output in app.astream(initial_state):
            for key, value in output.items():
                if key == "oracle" and not value["is_valid"]:
                    logger.error("DATA ORACLE SECURITY ABORT TRIGGERED. EXITING.")
                    return
                if "messages" in value:
                    for msg in value["messages"]:
                        raw_log_lines.append(f"{msg['content']}\n\n")
                        if key == "full_board": raw_board_messages.append(msg)
                if key == "synthesize":
                    if "chief_of_staff_json" in value:
                        try: cos_data = json.loads(value["chief_of_staff_json"])
                        except Exception: pass
                    if "unicorn_trades" in value: unicorn_trades = value["unicorn_trades"]
                if key == "compliance":
                    is_approved_flag = value.get("is_approved", False)
                    if is_approved_flag:
                        c_data = value.get("chairman_data", {})
                        red_team_data = value.get("red_team_data", {})
        
        if not is_approved_flag or not c_data: 
            logger.error("Compliance processing failed completely.")
            return

        board_matrix = parse_board_matrix(raw_board_messages, all_symbols)
        matrix_md = generate_matrix_markdown(board_matrix)
        raw_log_combined = "".join(raw_log_lines)
        
        html_payload = reporting.generate_html_briefing(
            total_val=total_portfolio_value, qqq_trend=live_qqq_trend, mandate=live_mandate, 
            chairman_data=c_data, cos_data=cos_data, matrix_md=matrix_md, unicorn_trades=unicorn_trades,
            sorted_ledger=sorted_ledger, red_team_data=red_team_data, history_data=history_data,
            account_holdings=account_holdings
        )
        
        storage_client.save_report(f"executive_briefing_{file_timestamp}.html", html_payload)
        storage_client.save_report(f"raw_debate_log_{file_timestamp}.md", raw_log_combined)
        
        qa_report_md = await run_post_flight_qa(raw_log_combined, json.dumps(c_data))
        storage_client.save_report(f"qa_summary_{file_timestamp}.md", qa_report_md)
        
        notifier.send_executive_briefing(html_payload)
        logger.info("Pipeline finalized successfully.")

    except Exception as e:
        logger.error("Pipeline execution halted due to fatal exception.")
    finally:
        storage_client.save_report(f"api_telemetry_{file_timestamp}.json", json.dumps(api_telemetry, indent=4))
        storage_client.execute_retention_policy(14)
        logger.info("Telemetry ledger flushed. Worker shutting down.")

if __name__ == "__main__":
    asyncio.run(main_batch())