
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from src.db.models import User


async def upsert_user(db: AsyncSession, clerk_user_id: str, email: str) -> User:
    """
    Insert the user if they don't exist, or do nothing if they do.
    Called by the Clerk webhook on first sign-up.
    """
    stmt = (
        insert(User)
        .values(clerk_user_id=clerk_user_id, email=email)
        .on_conflict_do_nothing(index_elements=["clerk_user_id"])
    )
    await db.execute(stmt)
    await db.commit()

    result = await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    return result.scalar_one()


async def get_user(db: AsyncSession, clerk_user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    return result.scalar_one_or_none()