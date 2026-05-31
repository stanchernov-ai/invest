import os

def replace_in_file(filepath, replacements):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

prepare_replacements = [
    ("async def run_prepare(run_id: str = None) -> dict:", "async def run_prepare(run_id: str = None, user_id: str = \"stan\") -> dict:"),
    ("storage_client.begin_run_status(run_id, started.isoformat())", "storage_client.begin_run_status(run_id, started.isoformat(), user_id=user_id)"),
    ("storage_client.mark_phase(run_id, \"prepare\", \"running\", started_at=started.isoformat())", "storage_client.mark_phase(run_id, \"prepare\", \"running\", started_at=started.isoformat(), user_id=user_id)"),
    ("storage_client.sync_inputs_from_cloud()", "storage_client.sync_inputs_from_cloud(user_id=user_id)"),
    ("storage_client.save_report(\"portfolio_history.json\", json.dumps(history_data))", "storage_client.save_report(\"portfolio_history.json\", json.dumps(history_data), user_id=user_id)"),
    ("storage_client.save_report(\"portfolio_returns.json\", json.dumps(account_returns))", "storage_client.save_report(\"portfolio_returns.json\", json.dumps(account_returns), user_id=user_id)"),
    ("storage_client.save_checkpoint(run_id, \"prepare\", checkpoint)", "storage_client.save_checkpoint(run_id, \"prepare\", checkpoint, user_id=user_id)"),
    ("storage_client.save_report(f\"api_telemetry_{run_id}_prepare.json\", json.dumps(api_telemetry, indent=4))", "storage_client.save_report(f\"api_telemetry_{run_id}_prepare.json\", json.dumps(api_telemetry, indent=4), user_id=user_id)"),
    ("storage_client.mark_phase(run_id, \"prepare\", \"failed\",", "storage_client.mark_phase(run_id, \"prepare\", \"failed\", user_id=user_id,"),
    ("storage_client.mark_phase(run_id, \"prepare\", \"success\",", "storage_client.mark_phase(run_id, \"prepare\", \"success\", user_id=user_id,"),
    ("verdict_memory.load_board_verdicts(),", "verdict_memory.load_board_verdicts(user_id=user_id),"),
    ("from src.core.schemas import generate_dynamic_mandate", "from src.core.portfolio_policy import resolve_policy"),
    ("live_mandate = generate_dynamic_mandate(total_portfolio_value, portfolio_12m_twr)", "user_profile = {}\n        policy = resolve_policy(user_profile)\n        live_mandate = policy.generate_dynamic_mandate(total_portfolio_value, portfolio_12m_twr)"),
    ("checkpoint = {", "\"user_profile\": user_profile,\n        checkpoint = {"),
    ("\"purchase_dates\": {sym: data.get(\"Purchase_Date\", \"Unknown\") for sym, data in master_ledger.items()},", "\"purchase_dates\": {sym: data.get(\"Purchase_Date\", \"Unknown\") for sym, data in master_ledger.items()},\n            \"user_profile\": user_profile,")
]

debate_replacements = [
    ("async def run_debate(run_id: str) -> dict:", "async def run_debate(run_id: str, user_id: str = \"stan\") -> dict:"),
    ("storage_client.load_checkpoint(run_id, \"prepare\")", "storage_client.load_checkpoint(run_id, \"prepare\", user_id=user_id)"),
    ("storage_client.mark_phase(run_id, \"debate\", \"running\", started_at=started.isoformat())", "storage_client.mark_phase(run_id, \"debate\", \"running\", started_at=started.isoformat(), user_id=user_id)"),
    ("storage_client.mark_phase(run_id, \"debate\", \"failed\",", "storage_client.mark_phase(run_id, \"debate\", \"failed\", user_id=user_id,"),
    ("storage_client.mark_phase(\n                run_id,\n                \"debate\",\n                \"failed\",", "storage_client.mark_phase(\n                run_id,\n                \"debate\",\n                \"failed\", user_id=user_id,"),
    ("storage_client.mark_phase(run_id, \"debate\", \"success\",", "storage_client.mark_phase(run_id, \"debate\", \"success\", user_id=user_id,"),
    ("storage_client.save_state_blob(\n                    f\"compliance_failure_{run_id}.json\",\n                    failure_blob,\n                )", "storage_client.save_state_blob(\n                    f\"compliance_failure_{run_id}.json\",\n                    failure_blob, user_id=user_id\n                )"),
    ("storage_client.save_state_blob(\n                    f\"debate_review_{run_id}.json\",\n                    review_blob,\n                )", "storage_client.save_state_blob(\n                    f\"debate_review_{run_id}.json\",\n                    review_blob, user_id=user_id\n                )"),
    ("storage_client.save_report(\n                    f\"api_telemetry_{run_id}_debate.json\",", "storage_client.save_report(\n                    f\"api_telemetry_{run_id}_debate.json\","),
    ("storage_client.save_checkpoint(run_id, \"debate\", checkpoint)", "storage_client.save_checkpoint(run_id, \"debate\", checkpoint, user_id=user_id)"),
    ("storage_client.save_report(f\"api_telemetry_{run_id}_debate.json\", json.dumps(telemetry, indent=4))", "storage_client.save_report(f\"api_telemetry_{run_id}_debate.json\", json.dumps(telemetry, indent=4), user_id=user_id)"),
    ("asyncio.run(run_debate(sys.argv[1]))", "user_id_arg = sys.argv[2] if len(sys.argv) > 2 else \"stan\"\n    asyncio.run(run_debate(sys.argv[1], user_id=user_id_arg))")
]

deliver_replacements = [
    ("async def run_deliver(run_id: str) -> dict:", "async def run_deliver(run_id: str, user_id: str = \"stan\") -> dict:"),
    ("storage_client.load_checkpoint(run_id, \"prepare\")", "storage_client.load_checkpoint(run_id, \"prepare\", user_id=user_id)"),
    ("storage_client.load_checkpoint(run_id, \"debate\")", "storage_client.load_checkpoint(run_id, \"debate\", user_id=user_id)"),
    ("storage_client.mark_phase(run_id, \"deliver\", \"running\", started_at=started.isoformat())", "storage_client.mark_phase(run_id, \"deliver\", \"running\", started_at=started.isoformat(), user_id=user_id)"),
    ("storage_client.mark_phase(run_id, \"deliver\", \"failed\",", "storage_client.mark_phase(run_id, \"deliver\", \"failed\", user_id=user_id,"),
    ("storage_client.mark_phase(\n                run_id, \"deliver\", \"failed\",", "storage_client.mark_phase(\n                run_id, \"deliver\", \"failed\", user_id=user_id,"),
    ("storage_client.mark_phase(run_id, \"deliver\", \"success\",", "storage_client.mark_phase(run_id, \"deliver\", \"success\", user_id=user_id,"),
    ("storage_client.save_report(f\"qa_reports_{run_id}.json\", json.dumps(qa_reports, indent=2, default=str))", "storage_client.save_report(f\"qa_reports_{run_id}.json\", json.dumps(qa_reports, indent=2, default=str), user_id=user_id)"),
    ("storage_client.load_state_blob(f\"retrospective_{run_id}.json\")", "storage_client.load_state_blob(f\"retrospective_{run_id}.json\", user_id=user_id)"),
    ("storage_client.save_report(f\"qa_dashboard_{run_id}.html\", qa_dashboard_html)", "storage_client.save_report(f\"qa_dashboard_{run_id}.html\", qa_dashboard_html, user_id=user_id)"),
    ("storage_client.save_report(f\"executive_briefing_{run_id}.html\", investor_briefing_html)", "storage_client.save_report(f\"executive_briefing_{run_id}.html\", investor_briefing_html, user_id=user_id)"),
    ("storage_client.save_report(f\"raw_debate_log_{run_id}.md\", raw_log_combined)", "storage_client.save_report(f\"raw_debate_log_{run_id}.md\", raw_log_combined, user_id=user_id)"),
    ("storage_client.save_report(f\"api_telemetry_{run_id}.json\", json.dumps(merged_telemetry, indent=4))", "storage_client.save_report(f\"api_telemetry_{run_id}.json\", json.dumps(merged_telemetry, indent=4), user_id=user_id)"),
    ("storage_client.load_run_status_for_run(run_id) or {}", "storage_client.load_run_status_for_run(run_id, user_id=user_id) or {}"),
    ("storage_client.save_run_status_for_run(run_id, status)", "storage_client.save_run_status_for_run(run_id, status, user_id=user_id)"),
    ("storage_client.load_run_status()", "storage_client.load_run_status(user_id=user_id)"),
    ("storage_client.save_run_status(status)", "storage_client.save_run_status(status, user_id=user_id)"),
    ("storage_client.execute_retention_policy(14)", "storage_client.execute_retention_policy(14, user_id=user_id)"),
    ("verdict_memory.persist_chairman_watchlist_passes(\n            c_data,\n            run_id,\n            is_approved=bool(debate.get(\"is_approved\")),\n            watchlist_symbols=watchlist_symbols,\n        )", "verdict_memory.persist_chairman_watchlist_passes(\n            c_data,\n            run_id,\n            is_approved=bool(debate.get(\"is_approved\")),\n            watchlist_symbols=watchlist_symbols,\n            user_id=user_id\n        )"),
    ("asyncio.run(run_deliver(sys.argv[1]))", "user_id_arg = sys.argv[2] if len(sys.argv) > 2 else \"stan\"\n    asyncio.run(run_deliver(sys.argv[1], user_id=user_id_arg))")
]

replace_in_file("src/jobs/prepare.py", prepare_replacements)
replace_in_file("src/jobs/debate.py", debate_replacements)
replace_in_file("src/jobs/deliver.py", deliver_replacements)
