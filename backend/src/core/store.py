
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from langgraph.store.postgres.aio import AsyncPostgresStore
from src.core.settings import settings


def _get_pg_url() -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


@asynccontextmanager
async def get_postgres_store(initialize=True):
    connection_kwargs = {
        "autocommit": True,
        "prepare_threshold": None,   # None = fully disable prepared statements
    }
    pool = AsyncConnectionPool(
        conninfo=_get_pg_url(),
        max_size=5,
        open=False,
        kwargs=connection_kwargs,
    )
    await pool.open()
    try:
        store = AsyncPostgresStore(pool)
        if initialize: await store.setup()
        yield store
    finally:
        await pool.close()