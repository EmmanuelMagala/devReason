
from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.base import get_session
from src.core.clerk import get_current_user  # re-export for convenience

# Re-export so routes only need to import from deps
__all__ = ["get_db", "get_redis", "get_current_user"]


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


async def get_redis(request: Request):
    return request.app.state.redis