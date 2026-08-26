from __future__ import annotations

from contextlib import asynccontextmanager

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from ace_api.config import settings

_pool: AsyncConnectionPool | None = None


async def open_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            settings().database_url, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row}
        )
        await _pool.open()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def conn():
    pool = await open_pool()
    async with pool.connection() as c:
        yield c


async def fetch_all(query: str, params: tuple | dict = ()) -> list[dict]:
    async with conn() as c:
        cur = await c.execute(query, params)
        return await cur.fetchall()


async def fetch_one(query: str, params: tuple | dict = ()) -> dict | None:
    async with conn() as c:
        cur = await c.execute(query, params)
        return await cur.fetchone()


async def execute(query: str, params: tuple | dict = ()) -> None:
    async with conn() as c:
        await c.execute(query, params)
