"""Job 2 - DEBATE.

The board engine: parallel panel + rebuttal, synthesis, Munger audit, chairman
arbitration with the deterministic 10% cap, and the compliance gate. Consumes the
prepare checkpoint (including its Data Oracle result — not re-run here) and writes
the debate checkpoint (chairman allocation, red team, raw debate log) for deliver.
No rendering or email happens here.
"""
import json
import asyncio
import logging

from src import storage_client
from src.output import notifier
from src.core.engine import app
from src.core import agent_activity
from src.config.settings import now_local
from src.logging_setup import configure_logging

logger = configure_logging()


async def run_debate(run_id: str) -> dict:
    """Execute the debate phase for an existing prepare checkpoint.

    Returns {'run_id', 'status', 'is_approved'}. On success writes the 'debate'
    checkpoint so the caller can trigger the deliver job."""
    configure_logging()
    logger.info(f"[DEBATE] Starting board engine for run {run_id}.")
    started = now_local()
    agent_activity.reset()

    prep = storage_client.load_checkpoint(run_id, "prepare")
    if not prep:
        msg = f"Debate phase could not load prepare checkpoint for run {run_id}."
        logger.error(msg)
        notifier.send_error_alert(msg)
        storage_client.mark_phase(run_id, "debate", "failed",
                                  finished_at=now_local().isoformat(), error="missing prepare checkpoint")
        return {"run_id": run_id, "status": "failed", "is_approved": False}

    storage_client.mark_phase(run_id, "debate", "running", started_at=started.isoformat())

    try:
        prep_oracle = prep.get("oracle") or {}
        initial_state = {
            "base_data_prompt": prep["mega_prompt"],
            "live_mandate": prep["live_mandate"],
            "heavy_tickers": prep["heavy_tickers"],
            "all_symbols": prep["all_symbols"],
            "total_portfolio_value": prep["total_portfolio_value"],
            "portfolio_holdings": prep["portfolio_holdings"],
            "purchase_dates": prep.get("purchase_dates", {}),
            "oracle_valid": prep_oracle.get("is_valid") if prep_oracle else None,
            "oracle_reason": prep_oracle.get("reason", ""),
            "oracle_prices": prep.get("price_feed") or {},
        }

        raw_log_lines = [prep.get("raw_log_header", "# RAW DEBATE LOG\n\n")]
        c_data, cos_data, red_team_data = {}, {}, {}
        raw_board_messages = []
        raw_verdicts = {}
        unicorn_trades = []
        is_approved_flag = False
        compliance_failure_detail = None
        allocation_source = "llm"
        chairman_bypassed = False
        compliance_source = "python+llm"
        munger_skipped = False

        async for output in app.astream(initial_state):
            for key, value in output.items():
                if key == "oracle" and not value["is_valid"]:
                    error_msg = f"DATA ORACLE SECURITY ABORT (debate). Reason: {value.get('reason', 'Unknown')}"
                    logger.error(error_msg)
                    notifier.send_error_alert(error_msg)
                    storage_client.mark_phase(run_id, "debate", "failed",
                                              finished_at=now_local().isoformat(),
                                              error="data oracle validation failed")
                    return {"run_id": run_id, "status": "failed", "is_approved": False}
                if "messages" in value:
                    for msg in value["messages"]:
                        raw_log_lines.append(f"{msg['content']}\n\n")
                        if key == "full_board":
                            raw_board_messages.append(msg)
                if key == "synthesize":
                    if "chief_of_staff_json" in value:
                        try:
                            cos_data = json.loads(value["chief_of_staff_json"])
                        except Exception:
                            pass
                    if "unicorn_trades" in value:
                        unicorn_trades = value["unicorn_trades"]
                    if value.get("raw_verdicts"):
                        raw_verdicts = value["raw_verdicts"]
                if key == "compliance":
                    is_approved_flag = value.get("is_approved", False)
                    allocation_source = value.get("allocation_source", "llm")
                    chairman_bypassed = value.get("chairman_bypassed", False)
                    compliance_source = value.get("compliance_source", "python+llm")
                    munger_skipped = value.get("munger_skipped", False)
                    if is_approved_flag:
                        c_data = value.get("chairman_data", {})
                        red_team_data = value.get("red_team_data", {})
                    else:
                        compliance_failure_detail = value.get("failure_detail") or {}

        if not is_approved_flag or not c_data:
            detail = compliance_failure_detail or {}
            error_summary = detail.get("summary") or "Compliance processing failed completely."
            logger.error("[DEBATE] Compliance gate failed for run %s:\n%s", run_id, error_summary)

            failure_blob = {
                "run_id": run_id,
                "phase": "debate",
                "gate": "compliance",
                "error": error_summary,
                "requires_expert_review": True,
                "expert_review_domains": detail.get("expert_review_domains")
                or ["prompt_engineering", "data_quality"],
                **detail,
            }
            review_blob = {
                **failure_blob,
                "raw_verdicts": raw_verdicts,
                "raw_board_messages": raw_board_messages,
                "raw_log_combined": "".join(raw_log_lines),
                "cos_data": cos_data,
                "unicorn_trades": unicorn_trades,
                "allocation_source": allocation_source,
                "chairman_bypassed": chairman_bypassed,
            }
            try:
                storage_client.save_state_blob(
                    f"compliance_failure_{run_id}.json",
                    failure_blob,
                )
                storage_client.save_state_blob(
                    f"debate_review_{run_id}.json",
                    review_blob,
                )
                storage_client.save_report(
                    f"api_telemetry_{run_id}_debate.json",
                    json.dumps(
                        {
                            "AGENT_ACTIVITY": agent_activity.snapshot(),
                            "COMPLIANCE_FAILURE": failure_blob,
                            "DEBATE_REVIEW": {"blob": f"debate_review_{run_id}.json"},
                        },
                        indent=4,
                    ),
                )
            except Exception as persist_exc:
                logger.warning("[DEBATE] Could not persist compliance failure artifact: %s", persist_exc)

            notifier.send_error_alert(error_summary)
            storage_client.mark_phase(
                run_id,
                "debate",
                "failed",
                finished_at=now_local().isoformat(),
                error=error_summary[:2000],
                compliance_violations=detail.get("violations") or [],
                requires_expert_review=True,
            )
            return {"run_id": run_id, "status": "failed", "is_approved": False}

        raw_log_combined = "".join(raw_log_lines)
        telemetry = {
            "AGENT_ACTIVITY": agent_activity.snapshot(),
            "allocation_source": allocation_source,
            "chairman_bypassed": chairman_bypassed,
            "compliance_source": compliance_source,
            "munger_skipped": munger_skipped,
        }

        checkpoint = {
            "run_id": run_id,
            "is_approved": is_approved_flag,
            "chairman_data": c_data,
            "cos_data": cos_data,
            "red_team_data": red_team_data,
            "raw_board_messages": raw_board_messages,
            "raw_verdicts": raw_verdicts,
            "raw_log_combined": raw_log_combined,
            "unicorn_trades": unicorn_trades,
            "telemetry": telemetry,
            "allocation_source": allocation_source,
            "chairman_bypassed": chairman_bypassed,
            "compliance_source": compliance_source,
            "munger_skipped": munger_skipped,
        }
        storage_client.save_checkpoint(run_id, "debate", checkpoint)
        storage_client.save_report(f"api_telemetry_{run_id}_debate.json", json.dumps(telemetry, indent=4))

        finished = now_local()
        storage_client.mark_phase(run_id, "debate", "success",
                                  started_at=started.isoformat(),
                                  finished_at=finished.isoformat(),
                                  duration_seconds=round((finished - started).total_seconds(), 1))
        logger.info(f"[DEBATE] Completed for run {run_id} in {round((finished - started).total_seconds(), 1)}s.")
        return {"run_id": run_id, "status": "success", "is_approved": is_approved_flag}

    except Exception as e:
        logger.error(f"[DEBATE] Fatal exception: {e}")
        notifier.send_error_alert(f"Debate phase failed: {e}")
        storage_client.mark_phase(run_id, "debate", "failed",
                                  finished_at=now_local().isoformat(), error=str(e))
        return {"run_id": run_id, "status": "failed", "is_approved": False}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.jobs.debate <run_id>", file=sys.stderr)
        sys.exit(2)
    asyncio.run(run_debate(sys.argv[1]))
