
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from src.core.settings import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_timeout=settings.db_pool_timeout_seconds,
    echo=False,  # set True temporarily if you want to see SQL queries
    hide_parameters=True,
    connect_args={
        "timeout": settings.db_connect_timeout_seconds,
        "command_timeout": settings.db_command_timeout_seconds,
        "statement_cache_size": 0,    # required for Supabase transaction pooler
        "prepared_statement_cache_size": 0,  # disable prepared statement cache
    },
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
