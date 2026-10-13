
import redis.asyncio as redis
from src.core.settings import settings


async def create_redis_pool():
    client = redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=5,
        health_check_interval=30,
    )
    return client
