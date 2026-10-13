"""Read-only performance probes. Never print credentials or repository content.

Run from backend: python scripts/measure_performance.py --output PATH
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import select, text, func
from src.core.settings import settings
from src.core.crypto import decrypt
from src.core.github_api import request
from src.core.redis_client import create_redis_pool
from src.db.base import AsyncSessionLocal, engine
from src.db.models import User, Review, Finding, GitHubConnection, ReviewJob
from src.db.repositories.review_repo import get_review
from src.schemas.review import ReviewRead


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--sync', action='store_true', help='Also time a verified metadata sync (writes repository metadata only).')
    args = parser.parse_args()
    results = {'captured_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'measurements': []}

    async def probe(name, operation, limit=20):
        start = time.perf_counter()
        try:
            async with asyncio.timeout(limit):
                metadata = await operation()
            result = {'name': name, 'seconds': round(time.perf_counter()-start, 3), 'ok': True, **(metadata or {})}
        except Exception as error:
            result = {'name': name, 'seconds': round(time.perf_counter()-start, 3), 'ok': False, 'error_type': type(error).__name__}
        results['measurements'].append(result)
        print(json.dumps(result), flush=True)

    async with httpx.AsyncClient(timeout=12, trust_env=False) as client:
        for path in ['/api/health', '/api/ready', '/api/repos/browse', '/api/health']:
            async def fetch(path=path):
                response = await client.get('http://127.0.0.1:8000'+path)
                return {'status': response.status_code, 'bytes': len(response.content)}
            await probe('http:'+path, fetch)
        for port in [5173, 5174]:
            for path in ['/', '/src/pages/RepositoriesPage.tsx', '/src/pages/ReviewPage.tsx']:
                async def fetch(port=port, path=path):
                    response = await client.get(f'http://localhost:{port}'+path)
                    return {'status': response.status_code, 'bytes': len(response.content)}
                await probe(f'vite:{port}:{path}', fetch)

    redis = await create_redis_pool()
    for index in range(3):
        async def ping():
            await redis.ping()
        await probe(f'redis:{index}', ping)
    await redis.aclose()

    for index in range(4):
        async def query():
            async with AsyncSessionLocal() as db:
                await db.execute(text('SELECT 1'))
        await probe(f'db_session_select_and_release:{index}', query)

    async with AsyncSessionLocal() as db:
        # Only metadata and lengths leave the database. No email, token or source is logged.
        owner = (await db.execute(select(GitHubConnection.clerk_user_id).where(GitHubConnection.status=='connected').limit(1))).scalar_one_or_none()
        if owner is None:
            owner = (await db.execute(select(User.clerk_user_id).limit(1))).scalar_one_or_none()
        ids = (await db.execute(select(Review.id).where(Review.clerk_user_id==owner).order_by(Review.created_at.desc()).limit(20))).scalars().all()
        connection = (await db.execute(select(GitHubConnection).where(GitHubConnection.clerk_user_id==owner,GitHubConnection.status=='connected').limit(1))).scalar_one_or_none()
        token = decrypt(connection.access_token_enc) if connection else None

    if owner:
        async def repeated_auth_reads():
            # Model the old existing-user path without its redundant insert/commit.
            for _ in range(2):
                async with AsyncSessionLocal() as db:
                    await db.execute(select(User).where(User.clerk_user_id==owner))
        await probe('auth_existing_user_two_sessions_read_only_lower_bound', repeated_auth_reads)

        async def history():
            from src.api.routes.reviews import list_reviews
            from fastapi.encoders import jsonable_encoder
            async with AsyncSessionLocal() as db:
                result = await list_reviews(page=1,page_size=20,user={'clerk_user_id':owner},db=db)
                payload = json.dumps(jsonable_encoder(result)).encode()
                return {'count': result['total'], 'bytes':len(payload), 'authentication_included':False}
        await probe('history_route_without_auth', history)
        async def summary_history():
            from src.api.routes.reviews import list_reviews
            from fastapi.encoders import jsonable_encoder
            async with AsyncSessionLocal() as db:
                result=await list_reviews(page=1,page_size=20,summary=True,user={'clerk_user_id':owner},db=db)
                return {'count':result['total'],'bytes':len(json.dumps(jsonable_encoder(result)).encode()),'authentication_included':False}
        await probe('summary_history_route_without_auth',summary_history)
        async def browse():
            from src.api.routes.discovery import browse
            async with AsyncSessionLocal() as db:
                result=await browse(page=1,page_size=20,user={'clerk_user_id':owner},db=db)
                return {'count':result['total'],'authentication_included':False}
        await probe('repository_browse_without_auth',browse)
        async def profile():
            from src.core.clerk import _ensure_local_user
            async with AsyncSessionLocal() as db:
                email=(await db.execute(select(User.email).where(User.clerk_user_id==owner))).scalar_one()
            await _ensure_local_user(owner,email)
        await probe('existing_user_provision_with_initial_lookup',profile)
        from types import SimpleNamespace
        async def cached_profile():
            from src.core.clerk import _local_email
            await _local_email(owner,SimpleNamespace(payload={}))
        await probe('local_profile_first_request',cached_profile)
        await probe('local_profile_cached_request',cached_profile)
        if ids:
            async def detail():
                async with AsyncSessionLocal() as db:
                    row = await get_review(db,ids[0])
                    payload = ReviewRead.model_validate(row).model_dump_json().encode()
                    return {'bytes':len(payload),'findings':len(row.findings),'authentication_included':False}
            await probe('review_detail_without_auth', detail)

    async def diagnostics():
        async with AsyncSessionLocal() as db:
            states=(await db.execute(text("SELECT state,wait_event_type,count(*) AS count FROM pg_stat_activity WHERE datname=current_database() GROUP BY state,wait_event_type"))).mappings().all()
            jobs=(await db.execute(select(ReviewJob.status,func.count()).group_by(ReviewJob.status))).all()
            return {'database_activity':[dict(row) for row in states], 'job_counts':[{ 'status':status,'count':count } for status,count in jobs]}
    await probe('database_activity', diagnostics)
    async def database_execution():
        async with AsyncSessionLocal() as db:
            plan=(await db.execute(text('EXPLAIN (ANALYZE, FORMAT JSON) SELECT 1'))).scalar_one()
            return {'server_execution_ms':plan[0]['Execution Time'],'server_planning_ms':plan[0]['Planning Time']}
    await probe('database_explain_simple_query',database_execution)

    if token:
        installations=[]
        async def github_installations():
            payload=await request(token,'GET','/user/installations',params={'per_page':100,'page':1})
            installations.extend(payload.get('installations',[]))
            return {'count':len(installations),'total':payload.get('total_count')}
        await probe('github_user_installations_page_one', github_installations)
        if installations:
            async def github_repos():
                payload=await request(token,'GET',f"/user/installations/{installations[0]['id']}/repositories",params={'per_page':100,'page':1})
                return {'count':len(payload.get('repositories',[])),'total':payload.get('total_count')}
            await probe('github_user_repositories_page_one', github_repos)

    if owner and args.sync:
        async def refresh():
            from src.api.routes.github_app import refresh
            async with AsyncSessionLocal() as db:
                result=await refresh(user={'clerk_user_id':owner},db=db)
                return {'accounts':len(result['accounts']),'notices':len(result['notices']),'authentication_included':False}
        await probe('verified_full_repository_sync_without_auth',refresh,limit=90)

    await engine.dispose()
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(results,indent=2),encoding='utf-8')


if __name__=='__main__':
    if sys.platform=='win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
