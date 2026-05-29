"""Local end-to-end entrypoint.

The pipeline is split into three phases (prepare -> debate -> deliver) that run as
independent Azure Functions chained by Storage Queues (see function_app.py). For
local runs and recovery, main_batch() executes all three in-process via
src.jobs.orchestrate.run_all.

Shared QA/matrix helpers now live in src.qa_pipeline; the per-phase logic lives in
src.jobs.{prepare,debate,deliver}.
"""
import asyncio

from src.logging_setup import configure_logging
from src.jobs.orchestrate import run_all

logger = configure_logging()


async def main_batch():
    """Run the full prepare -> debate -> deliver chain in one process."""
    return await run_all()


if __name__ == "__main__":
    asyncio.run(main_batch())
