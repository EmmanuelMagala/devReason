
import structlog
from contextlib import asynccontextmanager
import asyncio
from sqlalchemy import text
from src.db.base import AsyncSessionLocal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, TimeoutError as PoolTimeout
from src.core.github_app import verify_app_configured
from src.core.settings import settings
from src.core.store import get_postgres_store
from src.core.redis_client import create_redis_pool
from src.core.request_timing import RequestTimingMiddleware
from src.api.routes import health, webhooks, reviews, repos, github_app, discovery, report_actions, metrics

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting DevReason backend")

    # 1. Redis (Upstash)
    app.state.redis = await create_redis_pool()
    try:
        await app.state.redis.ping()
        log.info("Redis connected")
    except Exception:
        log.warning("Redis unavailable; connection actions and live events are degraded")

    # Only the separate worker initializes checkpoints and memory tables.
    async with get_postgres_store(initialize=False) as store:
        app.state.store = store
        # Pay the remote DNS/TLS connection cost before serving the first user.
        try:
            async with asyncio.timeout(12):
                async with AsyncSessionLocal() as db:
                    await db.execute(text('SELECT 1'))
            log.info('Application database pool warmed')
        except Exception:
            log.warning('Application database unavailable; readiness will report degraded status')
        app_ok = await verify_app_configured()
        if app_ok:
            log.info("GitHub App configuration verified", app_id=settings.github_app_id)
        else:
            log.warning("GitHub App configuration incomplete; configure it before connecting repositories")
        yield

    # Cleanup on shutdown
    await app.state.redis.aclose()
    log.info("DevReason backend shutdown complete")


app = FastAPI(
    title="DevReason API",
    description="AI-powered code review and architecture audit system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(',')],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Server-Timing"],
)
app.add_middleware(RequestTimingMiddleware)


@app.exception_handler(DBAPIError)
@app.exception_handler(PoolTimeout)
async def database_unavailable(request, error):
    log.error('database_request_failed', error_type=type(error).__name__)
    return JSONResponse(status_code=503, content={'detail':'The database is temporarily unavailable. Please retry shortly.'})


@app.get("/")
async def homepage() -> dict[str, str]:
    return {
        "name": app.title,
        "status": "ok",
        "docs": "/docs",
    }

app.include_router(health.router, prefix="/api")
app.include_router(webhooks.router, prefix="/webhooks")
app.include_router(reviews.router, prefix="/api/reviews")
app.include_router(repos.router, prefix="/api/repos")
app.include_router(discovery.router, prefix="/api/repos")
app.include_router(github_app.router, prefix="/api/auth")
app.include_router(report_actions.router, prefix="/api/reviews")
app.include_router(metrics.router, prefix="/api/metrics")
