import os
from src.config.settings import settings
import logging

try:
    import asyncpg
except ImportError:
    asyncpg = None

logger = logging.getLogger(__name__)

_pool = None

async def get_db_pool():
    global _pool
    if not _pool:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            logger.error("DATABASE_URL is not set.")
            raise ValueError("Database URL is not configured.")
        _pool = await asyncpg.create_pool(db_url, min_size=2, max_size=5)
    return _pool

async def execute_query(query: str, *args):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

async def fetch_query(query: str, *args):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

async def fetch_row(query: str, *args):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)
