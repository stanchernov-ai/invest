"""Job 3 - DELIVER.

Render the executive briefing + QA dashboard, run the post-work QA, and email
both. Consumes the prepare and debate checkpoints. This is where all post-flight
QA lives:
  - Post-flight trio (post-mortem / systems architect / prompt engineer) - parallel
  - Graphics QA - deterministic chart health + multimodal review of FINAL briefing HTML
  - QA Integrity (QA-of-the-QA) - Flash model + hard timeout
Merges all three phases' telemetry into one api_telemetry_{run_id}.json.
"""
import json
import asyncio
import logging

from src import storage_client
from src.output import reporting
from src.output import briefing_enrichment
from src.output import notifier
from src.core.catalysts import ensure_chairman_catalysts
from src.core import agent_activity
from src.config.settings import now_local
from src.logging_setup import configure_logging
from src import qa_pipeline
from src import verdict_memory

logger = configure_logging()


def _merge_agent_activity(*snapshots) -> dict:
    """Combine per-phase agent_activity ledgers. Same agent across phases has its
    counts summed so HR utilization reflects the whole run."""
    merged = {}
    numeric = ("invocations", "errors", "prompt_tokens", "output_tokens", "thinking_tokens", "total_tokens")
    for snap in snapshots:
        for agent, entry in (snap or {}).items():
            if agent not in merged:
                merged[agent] = dict(entry)
                continue
            for field in numeric:
                merged[agent][field] = merged[agent].get(field, 0) + entry.get(field, 0)
            merged[agent]["model"] = entry.get("model", merged[agent].get("model"))
    return merged


def _merge_telemetry(prep_tel: dict, debate_tel: dict, deliver_activity: dict) -> dict:
    merged = dict(prep_tel or {})
    merged.update({k: v for k, v in (debate_tel or {}).items() if k != "AGENT_ACTIVITY"})
    merged["AGENT_ACTIVITY"] = _merge_agent_activity(
        (prep_tel or {}).get("AGENT_ACTIVITY"),
        (debate_tel or {}).get("AGENT_ACTIVITY"),
        deliver_activity,
    )
    return merged


async def run_deliver(run_id: str) -> dict:
    """Render + post-work QA + email for an existing debate checkpoint.

    Returns {'run_id', 'status'}. Marks the overall run 'success' on completion."""
    configure_logging()
    logger.info(f"[DELIVER] Starting render + post-QA for run {run_id}.")
    started = now_local()
    agent_activity.reset()

    prep = storage_client.load_checkpoint(run_id, "prepare")
    debate = storage_client.load_checkpoint(run_id, "debate")
    if not prep or not debate:
        missing = "prepare" if not prep else "debate"
        msg = f"Deliver phase could not load {missing} checkpoint for run {run_id}."
        logger.error(msg)
        notifier.send_error_alert(msg)
        storage_client.mark_phase(run_id, "deliver", "failed",
                                  finished_at=now_local().isoformat(), error=f"missing {missing} checkpoint")
        return {"run_id": run_id, "status": "failed"}

    storage_client.mark_phase(run_id, "deliver", "running", started_at=started.isoformat())

    try:
        # Unpack prepared + debate state.
        total_portfolio_value = prep["total_portfolio_value"]
        live_qqq_trend = prep["live_qqq_trend"]
        portfolio_3m_trend = prep["portfolio_3m_trend"]
        live_mandate = prep["live_mandate"]
        sorted_ledger = prep["sorted_ledger"]
        account_holdings = prep["account_holdings"]
        account_returns = prep["account_returns"]
        history_data = prep["history_data"]
        advanced_data = prep["advanced_data"]
        all_symbols = prep["all_symbols"]

        c_data = debate["chairman_data"]
        cos_data = debate["cos_data"]
        red_team_data = debate["red_team_data"]
        raw_board_messages = debate["raw_board_messages"]
        raw_verdicts = debate.get("raw_verdicts") or {}
        raw_log_combined = debate["raw_log_combined"]
        unicorn_trades = debate["unicorn_trades"]

        portfolio_symbols = set(prep.get("portfolio_holdings") or {})
        c_data = ensure_chairman_catalysts(c_data, advanced_data, portfolio_symbols)
        c_data = await briefing_enrichment.enrich_chairman_for_briefing(
            c_data,
            raw_verdicts,
            portfolio_symbols=portfolio_symbols,
            sanitize_fn=reporting._sanitize_briefing_text,
        )

        board_matrix = qa_pipeline.build_board_matrix(
            raw_board_messages, all_symbols, raw_verdicts=raw_verdicts or None,
        )
        matrix_md = qa_pipeline.generate_matrix_markdown(board_matrix)

        # --- Post-work QA ---
        qa_reports = await qa_pipeline.run_post_flight_qa(
            raw_log_combined,
            json.dumps(c_data),
            raw_board_messages=raw_board_messages,
            all_symbols=all_symbols,
            raw_verdicts=raw_verdicts or None,
            portfolio_symbols=set(prep.get("portfolio_holdings") or {}),
        )

        # Build every chart once; reuse for render + the deterministic health probe.
        chart_urls = reporting.build_briefing_charts(sorted_ledger, account_holdings, account_returns, history_data)
        chart_health = reporting.audit_chart_health(chart_urls)
        broken_charts = [h["name"] for h in chart_health if not h["ok"]]
        if broken_charts:
            logger.warning(f"Broken/missing briefing charts detected: {', '.join(broken_charts)}")

        # Render briefing once (QA summary injected after integrity audit).
        briefing_html = reporting.generate_html_briefing(
            total_val=total_portfolio_value, qqq_trend=live_qqq_trend,
            portfolio_3m_trend=portfolio_3m_trend, mandate=live_mandate,
            chairman_data=c_data, cos_data=cos_data, matrix_md=matrix_md, unicorn_trades=unicorn_trades,
            sorted_ledger=sorted_ledger, red_team_data=red_team_data, history_data=history_data,
            qa_summary_text="", account_holdings=account_holdings, account_returns=account_returns,
            advanced_data=advanced_data,             chart_urls=chart_urls,
            raw_verdicts=raw_verdicts or None,
            portfolio_symbols=portfolio_symbols,
            raw_board_messages=raw_board_messages,
        )
        graphics_report = await qa_pipeline.run_graphics_designer_qa(briefing_html, chart_health)
        qa_reports.append(graphics_report)
        legal_report = await qa_pipeline.run_legal_counsel_qa(briefing_html)
        qa_reports.append(legal_report)

        from src.qa.legal_delivery import persist_and_notify_briefing_legal
        legal_delivery = persist_and_notify_briefing_legal(run_id, legal_report)

        from src.qa.scorecard import build_qa_scorecard, persist_scorecard
        from src.qa.human_review import build_review_url

        review_url = build_review_url(run_id)
        triage_url = build_review_url(run_id, fragment="candidates")

        # QA-the-QA on Flash + hard timeout so it can't blow the ceiling.
        interim_qa_dashboard_html = reporting.generate_qa_dashboard_html(
            qa_reports, run_id, review_url=review_url,
        )
        integrity_report = await qa_pipeline.run_qa_integrity_audit(
            qa_reports, raw_log_combined, json.dumps(c_data), interim_qa_dashboard_html,
            executive_briefing_html=briefing_html,
            raw_verdicts=raw_verdicts or None,
            all_symbols=all_symbols,
            portfolio_symbols=portfolio_symbols,
            raw_board_messages=raw_board_messages,
        )
        qa_reports.append(integrity_report)

        storage_client.save_report(f"qa_reports_{run_id}.json", json.dumps(qa_reports, indent=2, default=str))

        # Retrospective before dashboard email so candidate actions appear in QA dashboard.
        deliver_activity = agent_activity.snapshot()
        qa_scorecard = build_qa_scorecard(run_id, qa_reports, deliver_activity)
        retrospective_candidates: list = []
        try:
            from src.qa.retrospective import execute_retrospective

            retro = execute_retrospective(
                run_id,
                qa_reports=qa_reports,
                qa_scorecard=qa_scorecard,
                write_local_insights=False,
            )
            retro_marker = storage_client.load_state_blob(f"retrospective_{run_id}.json")
            if isinstance(retro_marker, dict):
                retrospective_candidates = retro_marker.get("candidates") or []
            logger.info(
                "[DELIVER] Retrospective %s for %s (%s candidates).",
                retro.get("status"), run_id, retro.get("candidate_count", 0),
            )
        except Exception as retro_exc:
            logger.error("[DELIVER] Retrospective failed (non-blocking): %s", retro_exc)

        # GFX-6: investor email is briefing-only; QA lives on the separate dashboard email.
        investor_briefing_html = reporting.inject_qa_review_link_into_briefing(
            reporting.inject_qa_summary_into_briefing(briefing_html, ""),
            review_url,
        )
        qa_dashboard_html = reporting.generate_qa_dashboard_html(
            qa_reports, run_id, review_url=review_url,
            candidates=retrospective_candidates,
            triage_url=triage_url,
        )

        storage_client.save_report(f"qa_dashboard_{run_id}.html", qa_dashboard_html)
        storage_client.save_report(f"executive_briefing_{run_id}.html", investor_briefing_html)
        storage_client.save_report(f"raw_debate_log_{run_id}.md", raw_log_combined)

        briefing_sent_at = now_local().isoformat()
        briefing_ok = notifier.send_executive_briefing(investor_briefing_html)
        qa_sent_at = now_local().isoformat()
        qa_ok = notifier.send_qa_dashboard(qa_dashboard_html)
        email_delivery = {
            "briefing": {"ok": briefing_ok, "sent_at": briefing_sent_at},
            "qa_dashboard": {"ok": qa_ok, "sent_at": qa_sent_at},
            "legal_counsel": {
                "ok": legal_delivery.get("email_ok"),
                "blob": legal_delivery.get("blob"),
                "sent_at": now_local().isoformat(),
            },
        }
        if briefing_ok:
            logger.info(
                "[DELIVER] Executive briefing email OK for run %s at %s.",
                run_id, briefing_sent_at,
            )
        else:
            logger.error(
                "[DELIVER] Executive briefing email FAILED for run %s at %s "
                "(artifacts saved to blob; check SMTP creds / App Insights).",
                run_id, briefing_sent_at,
            )
        if qa_ok:
            logger.info(
                "[DELIVER] QA dashboard email OK for run %s at %s.",
                run_id, qa_sent_at,
            )
        else:
            logger.warning(
                "[DELIVER] QA dashboard email FAILED for run %s at %s.",
                run_id, qa_sent_at,
            )

        if not briefing_ok:
            finished = now_local()
            err = "executive briefing email delivery failed (SMTP or missing credentials)"
            notifier.send_error_alert(
                f"Deliver phase for run {run_id}: {err}. "
                f"Briefing HTML saved as executive_briefing_{run_id}.html."
            )
            storage_client.mark_phase(
                run_id, "deliver", "failed",
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                duration_seconds=round((finished - started).total_seconds(), 1),
                error=err,
                email_delivery=email_delivery,
                briefing_blob=f"executive_briefing_{run_id}.html",
                qa_blob=f"qa_dashboard_{run_id}.html",
            )
            return {"run_id": run_id, "status": "failed"}

        # Merge telemetry from all three phases into the canonical run file.
        persist_scorecard(qa_scorecard)
        merged_telemetry = _merge_telemetry(
            prep.get("telemetry"), debate.get("telemetry"), deliver_activity
        )
        from src.qa.qa_augmentation import extract_qa_execution

        merged_telemetry["QA_EXECUTION"] = extract_qa_execution(qa_reports)
        merged_telemetry["QA_SCORECARD"] = qa_scorecard
        storage_client.save_report(f"api_telemetry_{run_id}.json", json.dumps(merged_telemetry, indent=4))

        # Post-job oversight blobs (API Optimization / Data Insight / Supervisor).
        try:
            from src.qa.post_job_audit import execute_post_job_oversight

            run_status = storage_client.load_run_status_for_run(run_id) or {}
            oversight = execute_post_job_oversight(
                run_id, merged_telemetry, qa_reports, run_status=run_status,
            )
            logger.info(
                "[DELIVER] Post-job oversight saved — verdict=%s.",
                oversight.get("metrics", {}).get("verdict"),
            )
        except Exception as oversight_exc:
            logger.error("[DELIVER] Post-job oversight failed (non-blocking): %s", oversight_exc)

        finished = now_local()
        storage_client.mark_phase(run_id, "deliver", "success",
                                  started_at=started.isoformat(),
                                  finished_at=finished.isoformat(),
                                  duration_seconds=round((finished - started).total_seconds(), 1),
                                  briefing_blob=f"executive_briefing_{run_id}.html",
                                  qa_blob=f"qa_dashboard_{run_id}.html",
                                  email_delivery=email_delivery)
        # Mirror briefing/qa blob names to the top level for existing monitors.
        status = storage_client.load_run_status_for_run(run_id) or {}
        status["briefing_blob"] = f"executive_briefing_{run_id}.html"
        status["qa_blob"] = f"qa_dashboard_{run_id}.html"
        storage_client.save_run_status_for_run(run_id, status)
        current = storage_client.load_run_status()
        if not current or current.get("run_id") == run_id:
            storage_client.save_run_status(status)

        storage_client.execute_retention_policy(14)

        portfolio_syms = set(prep.get("portfolio_holdings") or {})
        watchlist_symbols = [
            sym for sym in (prep.get("all_symbols") or [])
            if sym not in portfolio_syms
        ]
        # Watchlist Pass cooldown — only after compliance-approved debate (compliance gate).
        verdict_memory.persist_chairman_watchlist_passes(
            c_data,
            run_id,
            is_approved=bool(debate.get("is_approved")),
            watchlist_symbols=watchlist_symbols,
        )

        logger.info(f"[DELIVER] Completed for run {run_id} in {round((finished - started).total_seconds(), 1)}s.")
        return {"run_id": run_id, "status": "success"}

    except Exception as e:
        logger.error(f"[DELIVER] Fatal exception: {e}")
        notifier.send_error_alert(f"Deliver phase failed: {e}")
        storage_client.mark_phase(run_id, "deliver", "failed",
                                  finished_at=now_local().isoformat(), error=str(e))
        return {"run_id": run_id, "status": "failed"}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.jobs.deliver <run_id>", file=sys.stderr)
        sys.exit(2)
    asyncio.run(run_deliver(sys.argv[1]))
