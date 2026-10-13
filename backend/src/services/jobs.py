import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, or_, and_, update
from src.db.base import AsyncSessionLocal
from src.db.models import Review, ReviewJob
from src.core.settings import settings


async def fence(db, review_id, lease_token):
    job=(await db.execute(select(ReviewJob).where(ReviewJob.review_id==review_id).with_for_update())).scalar_one()
    if job.lease_token!=lease_token or job.status!='running' or job.cancel_requested or job.lease_until<=datetime.now(timezone.utc):
        raise asyncio.CancelledError('Review lease is no longer owned')


async def claim_job():
    now=datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        job=(await db.execute(select(ReviewJob).where(or_(ReviewJob.status=='pending',and_(ReviewJob.status=='running',ReviewJob.lease_until<now))).order_by(ReviewJob.created_at).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
        if not job: return None
        if job.cancel_requested or job.attempts>=3:
            status='cancelled' if job.cancel_requested else 'failed'
            job.status=status
            await db.execute(update(Review).where(Review.id==job.review_id).values(status=status,completed_at=now,error_message=None if status=='cancelled' else 'Worker recovery limit reached. Rerun this review.'))
            await db.commit(); return None
        job.status='running'; job.attempts+=1; job.lease_token=str(uuid.uuid4()); job.lease_until=now+timedelta(seconds=settings.worker_lease_seconds)
        if job.attempts>1:
            import structlog
            structlog.get_logger().info('review_recovered',attempt=job.attempts)
        await db.commit(); return job


async def heartbeat(job):
    async with AsyncSessionLocal() as db:
        current=(await db.execute(select(ReviewJob).where(ReviewJob.id==job.id).with_for_update())).scalar_one()
        if current.lease_token!=job.lease_token or not current.lease_until or current.lease_until<=datetime.now(timezone.utc): return 'lost'
        if current.cancel_requested: return 'cancelled'
        current.lease_until=datetime.now(timezone.utc)+timedelta(seconds=settings.worker_lease_seconds)
        await db.commit(); return 'owned'


async def finish_job(job,status,error=None):
    async with AsyncSessionLocal() as db:
        current=(await db.execute(select(ReviewJob).where(ReviewJob.id==job.id).with_for_update())).scalar_one()
        if current.lease_token!=job.lease_token: return
        if current.cancel_requested: status='cancelled'
        current.status=status; current.lease_until=None
        values={'status':status,'completed_at':datetime.now(timezone.utc)}
        if status=='cancelled': values['error_message']=None
        if error: values['error_message']=error
        await db.execute(update(Review).where(Review.id==job.review_id).values(**values))
        await db.commit()


async def run_once(execute):
    job=await claim_job()
    if not job: return False
    task=asyncio.create_task(execute(job))
    try:
        deadline=asyncio.get_running_loop().time()+settings.review_job_timeout_seconds
        while not task.done():
            await asyncio.wait({task},timeout=2)
            ownership=await heartbeat(job)
            if ownership!='owned' or asyncio.get_running_loop().time()>deadline:
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
                if ownership!='lost': await finish_job(job,'cancelled' if ownership=='cancelled' else 'failed','Review exceeded its execution time limit.' if ownership!='cancelled' else None)
                return True
        status=await task
        await finish_job(job,status)
    except asyncio.CancelledError:
        task.cancel(); await asyncio.gather(task,return_exceptions=True)
        # Leave the lease recoverable on worker shutdown.
        raise
    except Exception:
        task.cancel(); await asyncio.gather(task,return_exceptions=True)
        await finish_job(job,'failed','The review worker failed. Please retry.')
    return True
