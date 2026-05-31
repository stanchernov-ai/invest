import os
import json
import asyncio
import logging
from pydantic import BaseModel
from typing import List

from google.genai import types
from src.storage_client import get_blob_service_client, STATE_CONTAINER, REPORT_CONTAINER, DATA_DIR, save_state_blob
from src.core.agents import call_gemini_async, FAST_MODEL, HEAVY_MODEL, FLASH_TOKEN_LIMIT
from src.output.notifier import send_qa_digest
from src.config.settings import now_local, settings
from src import hr_review

logger = logging.getLogger(__name__)

class QAReviewReport(BaseModel):
    agent_role: str
    score: int
    findings: List[str]
    top_recommendations: List[str]

QA_TEAM_CONFIG = {
    "data_flow": {
        "role": "Data Flow Analyst",
        "model": FAST_MODEL,
        "system_instruction": "You are the Data Flow Analyst. Review the provided telemetry and debate logs to ensure data ingestion, ledger integrity, null/zero handling, and report data quality are correct."
    },
    "prompt_engineering": {
        "role": "Prompt Engineer",
        "model": HEAVY_MODEL,
        "system_instruction": "You are the Prompt Engineer. Review the debate logs to identify persona drift, sycophancy, or prompt/schema conflicts among the board members."
    },
    "api_health": {
        "role": "API Health Monitor",
        "model": FAST_MODEL,
        "system_instruction": "You are the API Health Monitor. Analyze the telemetry JSON for endpoint health, deprecations, 4xx/429 rates, and fallback usage."
    },
    "tech_stack": {
        "role": "Tech Stack Architect",
        "model": HEAVY_MODEL,
        "system_instruction": "You are the Tech Stack Architect. Review pipeline structure, concurrency, error handling, and deploy/runtime health from the provided artifacts."
    },
    "finance_cost": {
        "role": "Finance & Cost Consultant",
        "model": FAST_MODEL,
        "system_instruction": "You are the Finance & Cost Consultant. Review the run duration and data to identify cheaper alternatives without losing functionality."
    },
    "opportunity_audit": {
        "role": "Opportunity Auditor",
        "model": HEAVY_MODEL,
        "system_instruction": "You are the Opportunity Auditor. Check if we are extracting max value from each agent and API call. Identify unused data fields."
    },
    "graphics_designer": {
        "role": "Graphics Designer",
        "model": HEAVY_MODEL,
        "system_instruction": "You are the Graphics Designer. Review the HTML briefing structure and suggest layout, typography, and chart quality improvements."
    }
}

async def fetch_latest_artifacts():
    client = get_blob_service_client()
    if not client:
        return None, None, None, None
    
    state_client = client.get_container_client(STATE_CONTAINER)
    report_client = client.get_container_client(REPORT_CONTAINER)
    
    latest_telemetry_name = None
    try:
        telemetry_blobs = [b for b in state_client.list_blobs() if b.name.startswith("api_telemetry_")]
        telemetry_blobs.sort(key=lambda x: x.name, reverse=True)
        latest_telemetry_name = telemetry_blobs[0].name if telemetry_blobs else None
        latest_telemetry = state_client.download_blob(latest_telemetry_name).readall().decode('utf-8') if latest_telemetry_name else "{}"
    except Exception as e:
        logger.warning(f"Could not fetch telemetry: {e}")
        latest_telemetry = "{}"
        
    try:
        debate_blobs = [b for b in report_client.list_blobs() if b.name.startswith("raw_debate_log_")]
        debate_blobs.sort(key=lambda x: x.name, reverse=True)
        latest_debate = report_client.download_blob(debate_blobs[0].name).readall().decode('utf-8') if debate_blobs else ""
    except Exception as e:
        logger.warning(f"Could not fetch debate log: {e}")
        latest_debate = ""
        
    try:
        html_blobs = [b for b in report_client.list_blobs() if b.name.startswith("executive_briefing_")]
        html_blobs.sort(key=lambda x: x.name, reverse=True)
        latest_html = report_client.download_blob(html_blobs[0].name).readall().decode('utf-8') if html_blobs else ""
    except Exception as e:
        logger.warning(f"Could not fetch html briefing: {e}")
        latest_html = ""
        
    return latest_telemetry, latest_debate, latest_html, latest_telemetry_name

def generate_qa_digest_html(reports, hr_html=""):
    html = "<html><body style='font-family: Arial, sans-serif; padding: 20px; background-color: #f4f6f9;'>"
    html += "<h2 style='color: #2c3e50; border-bottom: 2px solid #bdc3c7; padding-bottom: 10px;'>QA & Cost Review Team Digest</h2>"
    
    if hr_html:
        html += hr_html

    for r in reports:
        score_color = "#27ae60" if r.get("score", 0) >= 4 else "#f39c12" if r.get("score", 0) == 3 else "#e74c3c"
        html += f"<div style='background-color: #ffffff; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 5px solid {score_color};'>"
        html += f"<h3 style='margin-top: 0; color: #34495e;'>{r.get('agent_role', 'Agent')} <span style='font-weight: normal; color: {score_color};'>(Score: {r.get('score', 'N/A')}/5)</span></h3>"
        
        html += "<strong style='color: #7f8c8d;'>Findings:</strong><ul style='margin-top: 5px; margin-bottom: 15px; color: #2c3e50;'>"
        for finding in r.get('findings', []):
            html += f"<li>{finding}</li>"
        html += "</ul>"
        
        html += "<strong style='color: #7f8c8d;'>Top Recommendations:</strong><ul style='margin-top: 5px; margin-bottom: 0; color: #2c3e50;'>"
        for rec in r.get('top_recommendations', []):
            html += f"<li>{rec}</li>"
        html += "</ul>"
        html += "</div>"
        
    html += "<p style='color: #95a5a6; font-size: 12px; margin-top: 30px;'>Invest AI Boardroom Automated QA Pipeline</p>"
    html += "</body></html>"
    return html

async def run_qa_review_team():
    logger.info("Initiating Weekly (Daily for now) QA Cost Review Team.")
    
    if not settings.validate():
        logger.error("FATAL ABORT: Required environment variables missing. Halting QA review pipeline.")
        return

    latest_telemetry, latest_debate, latest_html, latest_telemetry_name = await fetch_latest_artifacts()
    
    if not latest_telemetry and not latest_debate:
        logger.warning("No artifacts found to review. Exiting.")
        return
        
    # We truncate strings to avoid overflowing context limits.
    prompt_text = (
        f"Review the latest pipeline artifacts and provide your specialized QA analysis.\n\n"
        f"TELEMETRY (Truncated to first 10000 chars):\n{latest_telemetry[:10000]}\n\n"
        f"DEBATE LOG (Truncated to first 25000 chars):\n{latest_debate[:25000]}\n\n"
        f"HTML BRIEFING SNIPPET (Truncated to first 10000 chars):\n{latest_html[:10000]}"
    )
    
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])]
    
    tasks = []
    agent_keys = list(QA_TEAM_CONFIG.keys())
    for key in agent_keys:
        info = QA_TEAM_CONFIG[key]
        config_params = {
            "system_instruction": info["system_instruction"],
            "temperature": 0.15,
            "response_mime_type": "application/json",
            "response_schema": QAReviewReport
        }
        if info["model"] == FAST_MODEL:
            config_params["max_output_tokens"] = FLASH_TOKEN_LIMIT
            
        tasks.append(call_gemini_async(info["model"], contents, types.GenerateContentConfig(**config_params), agent_name=key))
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    reports = []
    for key, res in zip(agent_keys, results):
        role_name = QA_TEAM_CONFIG[key]["role"]
        if isinstance(res, Exception):
            logger.error(f"QA review failed for {role_name}: {res}")
            reports.append({
                "agent_role": role_name,
                "score": 1,
                "findings": [f"Execution failed: {str(res)}"],
                "top_recommendations": ["Check API/system logs."]
            })
        else:
            try:
                # remove ```json if any
                text = res.text.strip().replace("```json", "").replace("```", "").strip()
                parsed_res = json.loads(text)
                parsed_res["agent_role"] = role_name
                reports.append(parsed_res)
            except Exception as e:
                logger.error(f"Failed to parse QA review for {role_name}: {e}")
                reports.append({
                    "agent_role": role_name,
                    "score": 1,
                    "findings": ["Failed to parse agent JSON output."],
                    "top_recommendations": ["Review raw agent output for syntax errors."]
                })
                
    # HR Efficiency Consultant (5.4): deterministic agent utilization + right-sizing
    # verdicts, driven by the AGENT_ACTIVITY ledger persisted in telemetry.
    hr_html = ""
    try:
        telemetry_obj = json.loads(latest_telemetry) if latest_telemetry else {}
        activity = telemetry_obj.get("AGENT_ACTIVITY", {})
        if activity:
            hr_result = await hr_review.run_hr_efficiency_review(
                activity, raw_log=latest_debate or "", telemetry=telemetry_obj,
            )
            hr_html = hr_review.generate_hr_section_html(hr_result["utilization"], hr_result["report"])
        else:
            logger.warning("No AGENT_ACTIVITY in latest telemetry; skipping HR Efficiency Consultant.")
    except Exception as e:
        logger.error(f"HR Efficiency Consultant failed: {e}")

    html_content = generate_qa_digest_html(reports, hr_html=hr_html)
    
    send_qa_digest(html_content)

    run_id = None
    if latest_telemetry_name and latest_telemetry_name.startswith("api_telemetry_"):
        run_id = latest_telemetry_name.replace("api_telemetry_", "").replace(".json", "")
    if run_id:
        digest_record = {
            "run_id": run_id,
            "generated_at": now_local().isoformat(),
            "reports": reports,
            "hr_included": bool(hr_html),
        }
        try:
            save_state_blob(f"qa_digest_{run_id}.json", digest_record)
            logger.info("Persisted qa_digest_%s.json to state container.", run_id)
        except Exception as exc:
            logger.warning("Could not persist QA digest blob: %s", exc)

    logger.info("QA Cost Review Team execution complete.")

if __name__ == "__main__":
    # Ensure logging is configured if run standalone
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    asyncio.run(run_qa_review_team())
