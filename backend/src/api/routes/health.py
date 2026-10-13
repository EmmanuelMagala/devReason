from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.db.base import AsyncSessionLocal
from src.core.settings import settings
from src.core.deployment import worker_heartbeat_key
import structlog

log = structlog.get_logger()
router = APIRouter()


@router.get("/health")
async def health():
    """Liveness probe — returns OK if the process is running."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request):
    """
    Readiness probe — checks all external connections.
    Returns 200 only if Supabase and Upstash are both reachable.
    """
    checks = {}

    # Check Upstash Redis
    try:
        redis = request.app.state.redis
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        log.error("redis_health_check_failed", error=str(e))
        checks["redis"] = "error"

    # Check Supabase — open a temporary session just for the ping
    try:
        async with AsyncSessionLocal() as session:
            # One round trip checks connectivity and resolves both schema
            # columns. LIMIT 0 keeps row contents out of the readiness probe.
            await session.execute(text("SELECT 1, (SELECT lease_token FROM review_jobs LIMIT 0), (SELECT embedding IS NOT NULL FROM arch_rules LIMIT 0)"))
        checks["supabase"] = "ok"
    except Exception as e:
        log.error("supabase_health_check_failed", error=str(e))
        checks["supabase"] = "error"

    if settings.durable_reviews_enabled:
        try:
            checks['worker']='ok' if await request.app.state.redis.get(worker_heartbeat_key()) else 'error'
        except Exception: checks['worker']='error'

    all_ok = all(v == "ok" for v in checks.values())
    if all_ok:
        return {"status": "ok", **checks}

    return JSONResponse(
        status_code=503,
        content={"status": "degraded", **checks},
    )
