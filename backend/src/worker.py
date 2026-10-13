import asyncio
import sys
from contextlib import AsyncExitStack
from src.core.settings import settings
from src.core.checkpointer import get_postgres_checkpointer
from src.core.store import get_postgres_store
from src.core.redis_client import create_redis_pool
from src.agents.graph import compile_review_graph
from src.services.jobs import run_once
from src.services.execution import run_review
from src.core.deployment import worker_heartbeat_key


async def main():
    if not settings.durable_reviews_enabled: raise RuntimeError('Durable reviews are disabled')
    redis=await create_redis_pool()
    async def announce():
        while True:
            try: await redis.setex(worker_heartbeat_key(),30,'ok')
            except Exception: pass
            await asyncio.sleep(10)
    heartbeat_task=None
    try:
        async with AsyncExitStack() as stack:
            checkpointer=await stack.enter_async_context(get_postgres_checkpointer())
            store=await stack.enter_async_context(get_postgres_store())
            graph=compile_review_graph(checkpointer,store)
            heartbeat_task=asyncio.create_task(announce())
            async def execute(job): return await run_review(job.review_id,graph,redis,job.lease_token)
            while True:
                try:
                    if not await run_once(execute): await asyncio.sleep(1)
                except Exception:
                    import structlog
                    structlog.get_logger().warning('worker_database_unavailable')
                    await asyncio.sleep(2)
    finally:
        if heartbeat_task:
            heartbeat_task.cancel(); await asyncio.gather(heartbeat_task,return_exceptions=True)
        await redis.aclose()


if __name__=='__main__':
    asyncio.run(main(),loop_factory=asyncio.SelectorEventLoop if sys.platform=='win32' else asyncio.new_event_loop)
