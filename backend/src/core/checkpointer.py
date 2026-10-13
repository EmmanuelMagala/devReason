
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from src.core.settings import settings


def _get_pg_url() -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


def checkpoint_serializer():
    return JsonPlusSerializer(
        allowed_msgpack_modules=[('pydantic.types','SecretStr'),('src.agents.state','RepoConfig'),('src.agents.state','Finding'),('src.agents.state','ReviewState')],
        allowed_json_modules=[('pydantic','types','SecretStr'),('src','agents','state','RepoConfig'),('src','agents','state','Finding'),('src','agents','state','ReviewState')],
    )




@asynccontextmanager
async def get_postgres_checkpointer():
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
        checkpointer = AsyncPostgresSaver(pool,serde=checkpoint_serializer())
        await checkpointer.setup()
        yield checkpointer
    finally:
        await pool.close()
