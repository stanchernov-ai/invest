"""Daily Legal Counsel codebase audit — SaaS/commercial compliance on prompts and templates."""
from __future__ import annotations

import asyncio
import logging

from src.config.settings import now_local
from src.core import agent_activity
from src.logging_setup import configure_logging
from src import qa_pipeline
from src.qa.legal_delivery import persist_and_notify_code_legal

logger = configure_logging()


async def run_daily_legal_code_audit() -> dict:
    """Run deterministic + LLM legal scan; persist and email findings."""
    agent_activity.reset()
    day_stamp = now_local().strftime("%Y%m%d")
    started = now_local().isoformat()

    report = await qa_pipeline.run_legal_code_audit()
    report["agent_activity"] = agent_activity.snapshot()
    delivery = persist_and_notify_code_legal(day_stamp, report, started_at=started)
    return delivery["payload"]


def main() -> None:
    asyncio.run(run_daily_legal_code_audit())


if __name__ == "__main__":
    main()
