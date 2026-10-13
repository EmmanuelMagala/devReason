"""Deterministic regression gates. Run ONLY against compose.dev.yml's test DB."""
import asyncio
import json
import uuid
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, HTTPException
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from redis.asyncio import Redis
from src.db.models import User, Repo, Review, ReviewJob, ReviewCache, GitHubConnection, GitHubInstallation, ArchRule, Conversation
from src.core.settings import settings
from src.core.crypto import encrypt
from src.api.deps import get_db, get_current_user, get_redis
from src.api.routes import reviews, discovery, github_app, repos, report_actions, webhooks, metrics
from src.services import jobs, github_connection_service as github, source_service, memory_service, posting, stream_service

pytestmark=pytest.mark.asyncio


@pytest.fixture(scope='session')
def event_loop_policy():
    return asyncio.WindowsSelectorEventLoopPolicy() if sys.platform=='win32' else asyncio.DefaultEventLoopPolicy()


@pytest.fixture
async def fixture(monkeypatch):
    if '127.0.0.1:55439/devreason_test' not in settings.database_url:
        pytest.skip('Set DATABASE_URL to the dedicated localhost:55439/devreason_test database')
    engine=create_async_engine(settings.database_url,poolclass=NullPool)
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    monkeypatch.setattr(settings,'encryption_key','11'*32)
    monkeypatch.setattr(jobs,'AsyncSessionLocal',sessions)
    from src.services import execution
    from src.agents.nodes import persist_review, complete_review
    for module in (execution,persist_review,complete_review): monkeypatch.setattr(module,'AsyncSessionLocal',sessions)
    from src.db import base
    monkeypatch.setattr(base,'AsyncSessionLocal',sessions)
    user_id='regression_'+uuid.uuid4().hex
    repo_id=uuid.uuid4(); connection_id=uuid.uuid4()
    async with sessions() as db:
        db.add(User(clerk_user_id=user_id,email=user_id+'@example.test'))
        await db.flush()
        db.add(Repo(id=repo_id,clerk_user_id=user_id,owner='acme',name='widget',github_repo_id=99,github_installation_id=123))
        db.add(GitHubConnection(id=connection_id,clerk_user_id=user_id,github_user_id=7,login='test',access_token_enc=encrypt('fixture-user-token'),status='connected'))
        await db.flush()
        db.add(GitHubInstallation(connection_id=connection_id,installation_id=123,account_login='acme',status='connected'))
        await db.commit()
    redis=Redis.from_url('redis://127.0.0.1:6381/15')
    app=FastAPI()
    for router,prefix in [(reviews.router,'/api/reviews'),(report_actions.router,'/api/reviews'),(repos.router,'/api/repos'),(discovery.router,'/api/repos'),(github_app.router,'/api/auth'),(webhooks.router,'/webhooks')]: app.include_router(router,prefix=prefix)
    async def db_override():
        async with sessions() as db: yield db
    async def user_override(): return {'clerk_user_id':user_id}
    async def redis_override(): return redis
    app.dependency_overrides.update({get_db:db_override,get_current_user:user_override,get_redis:redis_override})
    app.include_router(metrics.router,prefix='/api/metrics')
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://fixture') as client:
        yield SimpleNamespace(db=sessions,client=client,user=user_id,repo=repo_id,connection=connection_id,redis=redis)
    async with sessions() as db:
        ids=list((await db.execute(select(Review.id).where(Review.clerk_user_id==user_id))).scalars())
        for ident in ids: await redis.delete(f'review:{ident}:events:v2',f'review:{ident}:status')
        await db.execute(delete(Review).where(Review.clerk_user_id==user_id))
        await db.execute(delete(Conversation).where(Conversation.clerk_user_id==user_id))
        await db.execute(delete(ReviewCache).where(ReviewCache.repo_id==repo_id))
        await db.execute(delete(Repo).where(Repo.clerk_user_id==user_id))
        await db.execute(delete(User).where(User.clerk_user_id==user_id)); await db.commit()
    await redis.aclose(); await engine.dispose()


async def add_job(f,**kwargs):
    rid=uuid.uuid4()
    async with f.db() as db:
        db.add(Review(id=rid,repo_id=f.repo,clerk_user_id=f.user,pr_url='https://github.com/acme/widget/pull/1',pr_number=1,thread_id=str(rid),status='pending'))
        await db.flush()
        row=ReviewJob(review_id=rid,clerk_user_id=f.user,request_key=str(rid),**kwargs); db.add(row); await db.commit()
    return row


async def test_workers_claim_distinct_jobs_and_recover_expired_lease(fixture):
    f=fixture; first=await add_job(f); second=await add_job(f)
    a,b=await asyncio.gather(jobs.claim_job(),jobs.claim_job())
    assert {a.id,b.id}=={first.id,second.id}
    assert await jobs.claim_job() is None
    async with f.db() as db:
        row=await db.get(ReviewJob,a.id); row.lease_until=datetime.now(timezone.utc)-timedelta(seconds=1); await db.commit()
    recovered=await jobs.claim_job()
    assert recovered.id==a.id and recovered.attempts==2 and recovered.lease_token!=a.lease_token
    assert await jobs.heartbeat(a)=='lost'
    async with f.db() as db:
        with pytest.raises(asyncio.CancelledError): await jobs.fence(db,a.review_id,a.lease_token)
    await jobs.finish_job(a,'completed')
    async with f.db() as db: assert (await db.get(ReviewJob,a.id)).status=='running'


async def test_worker_cancellation_terminal_and_recovery_limit(fixture):
    f=fixture; job=await add_job(f)
    started=asyncio.Event()
    async def execute(claimed):
        started.set(); await asyncio.Event().wait()
    task=asyncio.create_task(jobs.run_once(execute)); await started.wait()
    result=await f.client.post(f'/api/reviews/{job.review_id}/cancel')
    assert result.status_code==200
    await asyncio.wait_for(task,5)
    async with f.db() as db: assert (await db.get(Review,job.review_id)).status=='cancelled'
    abandoned=await add_job(f,status='running',attempts=3,lease_until=datetime.now(timezone.utc)-timedelta(seconds=1))
    assert await jobs.claim_job() is None
    async with f.db() as db: assert (await db.get(Review,abandoned.review_id)).status=='failed'


async def test_replay_is_independent_for_two_tabs_and_late_subscriber(fixture):
    f=fixture; job=await add_job(f)
    from src.schemas.stream import StreamEvent
    for i in range(120): await stream_service.push_event(f.redis,str(job.review_id),StreamEvent(event='agent_start',agent='code_analyst',data={'n':i}))
    await stream_service.push_event(f.redis,str(job.review_id),StreamEvent(event='complete',data={'status':'partial'}))
    async def drain():
        cursor='0-0'; items=[]
        while True:
            batch=await stream_service.read_events(f.redis,str(job.review_id),cursor)
            items+=batch
            if any(json.loads(payload)['event']=='complete' for _,payload in batch): return items
            cursor=batch[-1][0]
    a,b=await asyncio.gather(drain(),drain()); late=await drain()
    assert a==b==late and len(a)==121


async def test_verified_installation_rejects_other_account_and_removed_repo(fixture,monkeypatch):
    f=fixture
    async def listing(token,path,**kwargs):
        assert token=='fixture-user-token'
        return [{'id':123,'account':{'login':'acme'}}] if path=='/user/installations' else [{'id':99,'owner':{'login':'acme'},'name':'widget'}]
    monkeypatch.setattr(github,'paginate',listing)
    async with f.db() as db:
        repo=await db.get(Repo,f.repo)
        assert await github.authorize_repo(db,f.user,repo)=='fixture-user-token'
        with pytest.raises(HTTPException) as denied: await github.verified_installation(db,f.user,999)
        assert denied.value.status_code==403
        repo.github_repo_id=100
        with pytest.raises(HTTPException) as denied: await github.authorize_repo(db,f.user,repo)
        assert denied.value.status_code==403
    response=await f.client.post('/api/auth/github/sync',json={'installation_id':999})
    assert response.status_code==403


async def test_oauth_state_one_use_bound_to_user_and_redirect(fixture,monkeypatch):
    f=fixture; monkeypatch.setattr(settings,'github_app_client_secret','fixture-secret')
    monkeypatch.setattr(settings,'github_app_client_id','fixture-client')
    async def exchange(**values): return {'access_token':'fixture'}
    captured=[]
    async def save(db,user,tokens): captured.append(user); return SimpleNamespace(id=f.connection)
    monkeypatch.setattr(github_app,'exchange_token',exchange); monkeypatch.setattr(github_app,'save_connection',save)
    response=await f.client.post('/api/auth/github/start',json={'return_to':'/repos/'+str(f.repo)})
    from urllib.parse import urlparse,parse_qs
    state=parse_qs(urlparse(response.json()['authorize_url']).query)['state'][0]
    callback=await f.client.get('/api/auth/github/callback',params={'state':state,'code':'fixture'})
    assert callback.status_code==307 and '/repos/'+str(f.repo) in callback.headers['location']
    ticket=parse_qs(urlparse(callback.headers['location']).query)['github_ticket'][0]
    assert captured==[]
    raw=await f.redis.get('github_pending:'+ticket)
    assert 'fixture-secret' not in raw.decode() and 'access_token' not in raw.decode()
    other_ticket=uuid.uuid4().hex
    await f.redis.setex('github_pending:'+other_ticket,60,json.dumps({'clerk_user_id':'different-user','tokens_enc':encrypt('{"access_token":"fixture"}')}))
    denied=await f.client.post('/api/auth/github/complete',json={'ticket':other_ticket})
    assert denied.status_code==403 and captured==[]
    await f.redis.delete('github_pending:'+other_ticket)
    completed=await f.client.post('/api/auth/github/complete',json={'ticket':ticket})
    assert completed.status_code==200
    again=await f.client.get('/api/auth/github/callback',params={'state':state,'code':'fixture'})
    assert 'github_error' in again.headers['location'] and captured==[f.user]
    assert github_app.safe_return('//evil.test')=='/repositories'


async def test_github_return_preserves_queries_anchors_and_cancelled_authorization(fixture,monkeypatch):
    f=fixture
    monkeypatch.setattr(settings,'github_app_client_secret','fixture-secret')
    monkeypatch.setattr(settings,'github_app_client_id','fixture-client')
    from urllib.parse import urlparse,parse_qs
    target='/repos/'+str(f.repo)+'?tab=branches&branch=feature%2Fauth&q=two%20words#scope'
    start=await f.client.post('/api/auth/github/start',json={'return_to':target})
    state=parse_qs(urlparse(start.json()['authorize_url']).query)['state'][0]
    cancelled=await f.client.get('/api/auth/github/callback',params={'state':state,'error':'access_denied'})
    destination=urlparse(cancelled.headers['location']); query=parse_qs(destination.query)
    assert destination.path=='/repos/'+str(f.repo) and destination.fragment=='scope'
    assert query['branch']==['feature/auth'] and query['q']==['two words'] and 'github_error' in query
    assert await f.redis.get('github_oauth:'+state) is None
    for invalid in ('//evil.test','/%2fevil.test','/\\evil.test','/repo%0d%0aLocation:evil','https://evil.test'):
        assert github_app.safe_return(invalid)=='/repositories'


async def test_installation_return_and_organization_request_consume_state(fixture,monkeypatch):
    f=fixture; calls=[]
    async def sync(db,user,installation,connection): calls.append((user,installation,connection)); return {}
    monkeypatch.setattr(github_app,'sync_verified',sync)
    target='/repos/'+str(f.repo)+'?tab=branches&branch=main#scope'
    for action in ('install','update','request'):
        state=uuid.uuid4().hex
        await f.redis.setex('github_install:'+state,60,json.dumps({'clerk_user_id':f.user,'connection_id':str(f.connection),'return_to':target}))
        response=await f.client.get('/api/auth/github/setup',params={'installation_id':123,'state':state,'setup_action':action})
        from urllib.parse import urlparse,parse_qs
        destination=urlparse(response.headers['location'])
        assert destination.path=='/repos/'+str(f.repo) and destination.fragment=='scope'
        query=parse_qs(destination.query)
        assert query['branch']==['main'] and ('github_notice' if action=='request' else 'github_connected') in query
        assert await f.redis.get('github_install:'+state) is None
    assert calls==[(f.user,123,f.connection)]*2
    response=await f.client.get('/api/auth/github/setup',params={'installation_id':999,'setup_action':'update'})
    assert 'github_return=1' in response.headers['location'] and len(calls)==2


async def test_installation_cookie_restores_origin_without_query_state(fixture,monkeypatch):
    f=fixture; calls=[]
    monkeypatch.setattr(settings,'allowed_origins','http://localhost:5173,http://127.0.0.1:5174')
    async def sync(db,user,installation,connection): calls.append((user,installation,connection)); return {}
    monkeypatch.setattr(github_app,'sync_verified',sync)
    target='/repos/'+str(f.repo)+'?tab=branches&branch=feature%2Fauth#scope'
    start=await f.client.post('/api/auth/github/install',params={'connection_id':str(f.connection),'return_to':target},headers={'Origin':'http://127.0.0.1:5174'})
    assert start.status_code==200
    assert 'HttpOnly' in start.headers['set-cookie'] and 'SameSite=lax' in start.headers['set-cookie']
    from urllib.parse import urlparse,parse_qs
    state=parse_qs(urlparse(start.json()['install_url']).query)['state'][0]
    response=await f.client.get('/api/auth/github/setup',params={'installation_id':123,'setup_action':'update'})
    destination=urlparse(response.headers['location'])
    assert destination.netloc=='127.0.0.1:5174' and destination.fragment=='scope'
    assert parse_qs(destination.query)['branch']==['feature/auth']
    assert calls==[(f.user,123,f.connection)] and await f.redis.get('github_install:'+state) is None
    assert github_app.INSTALL_COOKIE not in f.client.cookies
    again=await f.client.get('/api/auth/github/setup',params={'installation_id':123,'setup_action':'update'})
    assert 'github_return=1' in again.headers['location'] and len(calls)==1


async def test_manage_installation_requires_user_access_and_keeps_return_context(fixture,monkeypatch):
    f=fixture
    async def pages(token,path,**kwargs): return [{'id':123,'html_url':'https://github.com/organizations/acme/settings/installations/123'}]
    monkeypatch.setattr(github_app,'paginate',pages)
    response=await f.client.post('/api/auth/github/install',params={'connection_id':str(f.connection),'installation_id':123,'return_to':'/reviews?page=2'})
    assert response.status_code==200 and response.json()['install_url'].startswith('https://github.com/organizations/acme/settings/installations/123?state=')
    from urllib.parse import urlparse,parse_qs
    state=parse_qs(urlparse(response.json()['install_url']).query)['state'][0]
    payload=json.loads(await f.redis.get('github_install:'+state))
    assert payload['clerk_user_id']==f.user and payload['return_to']=='/reviews?page=2'
    await f.redis.delete('github_install:'+state)
    denied=await f.client.post('/api/auth/github/install',params={'connection_id':str(f.connection),'installation_id':999})
    assert denied.status_code==403


async def test_oauth_redirect_origin_is_allowlisted(fixture,monkeypatch):
    f=fixture
    monkeypatch.setattr(settings,'github_app_client_secret','fixture-secret')
    monkeypatch.setattr(settings,'github_app_client_id','fixture-client')
    monkeypatch.setattr(settings,'allowed_origins','http://127.0.0.1:5174')
    from urllib.parse import urlparse,parse_qs
    for origin,expected in [('http://127.0.0.1:5174','http://127.0.0.1:5174'),('https://evil.test',settings.frontend_base_url.rstrip('/'))]:
        response=await f.client.post('/api/auth/github/start',json={'return_to':'/reviews?page=2#history'},headers={'Origin':origin})
        state=parse_qs(urlparse(response.json()['authorize_url']).query)['state'][0]
        callback=await f.client.get('/api/auth/github/callback',params={'state':state,'error':'access_denied'})
        assert callback.headers['location'].startswith(expected+'/reviews?') and callback.headers['location'].endswith('#history')


async def test_unexpired_token_does_not_block_other_account_actions(fixture):
    f=fixture
    async with f.db() as first, f.db() as second:
        _,token=await github.connection_token(first,f.connection,f.user)
        assert token=='fixture-user-token'
        # NOWAIT fails if a metadata request locks the account during API calls.
        row=(await second.execute(select(GitHubConnection).where(GitHubConnection.id==f.connection).with_for_update(nowait=True))).scalar_one()
        assert row.id==f.connection
        await second.rollback()


async def test_concurrent_expired_token_refresh_exchanges_once(fixture,monkeypatch):
    f=fixture; calls=[]
    async with f.db() as db:
        row=await db.get(GitHubConnection,f.connection)
        row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        row.refresh_token_enc=encrypt('fixture-refresh')
        await db.commit()
    async def exchange(**values):
        calls.append(values)
        await asyncio.sleep(0.05)
        return {'access_token':'fresh-fixture-token','expires_in':3600}
    monkeypatch.setattr(github,'exchange_token',exchange)
    async def get_token():
        async with f.db() as db: return (await github.connection_token(db,f.connection,f.user))[1]
    tokens=await asyncio.gather(get_token(),get_token())
    assert tokens==['fresh-fixture-token']*2 and len(calls)==1


async def test_submission_idempotency_and_invalid_ids(fixture,monkeypatch):
    f=fixture
    async def authorize(*args): return 'fixture'
    async def target(*args,**kwargs): return {'head':{'sha':'a'*40},'title':'A change'}
    monkeypatch.setattr(reviews,'authorize_repo',authorize); monkeypatch.setattr(reviews,'github_request',target)
    body={'repo_id':str(f.repo),'pr_number':1}
    a,b=await asyncio.gather(f.client.post('/api/reviews',json=body,headers={'Idempotency-Key':'same'}),f.client.post('/api/reviews',json=body,headers={'Idempotency-Key':'same'}))
    assert a.status_code==b.status_code==202 and a.json()['id']==b.json()['id']
    changed=await f.client.post('/api/reviews',json={**body,'pr_number':2},headers={'Idempotency-Key':'same'})
    assert changed.status_code==409
    assert (await f.client.get('/api/reviews/bad-id')).status_code==422
    assert (await f.client.post('/api/reviews',json={**body,'pr_url':'https://evil.test/acme/widget/pull/1'})).status_code==422
    cancel=await f.client.post('/api/reviews/'+a.json()['id']+'/cancel'); assert cancel.json()['status']=='cancelled'
    history=await f.client.get('/api/reviews'); assert history.json()['total']==1


async def test_legacy_report_unknown_line_keeps_detail_and_history_readable(fixture):
    f=fixture; job=await add_job(f)
    from src.db.models import Finding as StoredFinding
    async with f.db() as db:
        db.add(StoredFinding(review_id=job.review_id,repo_id=f.repo,pr_number=1,agent='code_analyst',severity='medium',type='legacy',file='src/api.py',line=0,message='An earlier finding'))
        await db.commit()
    detail=await f.client.get('/api/reviews/'+str(job.review_id))
    history=await f.client.get('/api/reviews')
    assert detail.status_code==history.status_code==200
    assert detail.json()['findings'][0]['line'] is None
    assert history.json()['items'][0]['findings'][0]['message']=='An earlier finding'
    async with f.db() as db:
        assert (await db.execute(select(StoredFinding.line).where(StoredFinding.review_id==job.review_id))).scalar_one()==0


async def test_summary_history_keeps_counts_and_excludes_report_content(fixture):
    f=fixture; job=await add_job(f)
    from src.db.models import Finding as StoredFinding
    async with f.db() as db:
        review=await db.get(Review,job.review_id)
        review.report_markdown='Large private report '*10000
        db.add(StoredFinding(review_id=job.review_id,repo_id=f.repo,agent='code_analyst',severity='high',type='test',message='Private finding'))
        await db.commit()
    response=await f.client.get('/api/reviews?summary=true')
    assert response.status_code==200 and response.json()['total']==1
    row=response.json()['items'][0]
    assert row['finding_count']==1
    assert not {'findings','report_markdown','coverage','scope'} & row.keys()
    assert len(response.content)<2000
    empty=await f.client.get('/api/reviews?summary=true&page=99')
    assert empty.json()['items']==[] and empty.json()['total']==1
    detail=await f.client.get('/api/reviews/'+str(job.review_id))
    assert detail.json()['findings'][0]['message']=='Private finding'


async def test_refresh_verifies_each_account_once_and_preserves_union(fixture,monkeypatch):
    f=fixture; calls=[]
    second=uuid.uuid4()
    async with f.db() as db:
        db.add(GitHubConnection(id=second,clerk_user_id=f.user,github_user_id=8,login='other',access_token_enc=encrypt('other-token'),status='connected'))
        db.add(GitHubInstallation(connection_id=second,installation_id=123,account_login='acme',status='connected'))
        await db.commit()
    async def pages(token,path,**kwargs):
        calls.append((token,path))
        if path=='/user/installations': return [{'id':123,'account':{'login':'acme'}}]
        number=100 if token=='other-token' else 99
        return [{'id':number,'owner':{'login':'acme'},'name':'other-repo' if number==100 else 'widget','private':True}]
    monkeypatch.setattr(github_app,'paginate',pages)
    result=await f.client.post('/api/auth/github/refresh')
    assert result.status_code==200
    assert len(calls)==4 and len(set(calls))==4
    browse=(await f.client.get('/api/repos/browse')).json()
    assert {row['name'] for row in browse['items']}=={'widget','other-repo'}


async def test_revoked_refresh_hides_repos_but_preserves_reviews(fixture,monkeypatch):
    f=fixture; job=await add_job(f)
    async def no_installations(*args,**kwargs): return []
    monkeypatch.setattr(github_app,'paginate',no_installations)
    assert (await f.client.post('/api/auth/github/refresh')).status_code==200
    assert (await f.client.get('/api/repos/browse')).json()['total']==0
    assert (await f.client.get('/api/reviews/'+str(job.review_id))).status_code==200


async def test_rule_embedding_atomic_edit_delete_and_approved_filter(fixture,monkeypatch):
    f=fixture
    class Embed:
        async def aembed_query(self,value): return [0.0]*1536
    monkeypatch.setattr(memory_service,'get_embedder',lambda:Embed())
    import src.core.embeddings as embeddings
    monkeypatch.setattr(embeddings,'get_embedder',lambda:Embed())
    created=await f.client.post(f'/api/repos/{f.repo}/rules',json={'content':'A specific boundary'})
    assert created.status_code==201,created.text
    rid=created.json()['id']
    edited=await f.client.patch(f'/api/repos/{f.repo}/rules/{rid}',json={'content':'An edited boundary','status':'rejected'})
    assert edited.status_code==200 and edited.json()['content']=='An edited boundary'
    async with f.db() as db:
        assert (await db.execute(text('SELECT vector_dims(embedding) FROM arch_rules WHERE id=:id'),{'id':uuid.UUID(rid)})).scalar_one()==1536
    approved=await f.client.get(f'/api/repos/{f.repo}/rules?status=approved'); assert approved.json()==[]
    class BadEmbed:
        async def aembed_query(self,value): return [0.0]*4
    monkeypatch.setattr(memory_service,'get_embedder',lambda:BadEmbed())
    async with f.db() as db:
        with pytest.raises(ValueError): await memory_service.embed_and_store_rule(db,str(f.repo),'Must not persist')
        assert len(list((await db.execute(select(ArchRule).where(ArchRule.repo_id==f.repo))).scalars()))==1
    assert (await f.client.delete(f'/api/repos/{f.repo}/rules/{rid}')).status_code==204


async def test_scope_bounds_and_preview_order_match(monkeypatch):
    monkeypatch.setattr(settings,'review_max_files',2); monkeypatch.setattr(settings,'review_max_characters',12)
    async def contents(*args): return 'abcdefghij'
    monkeypatch.setattr(source_service,'file_content',contents)
    paths=['src/b.py','requirements.txt','src/a.py','vendor/x.py','README.md']
    files,coverage=await source_service.select_files('token','acme','widget','sha',paths,{})
    assert [f['path'] for f in files]==source_service.eligible_paths(paths)[:2]
    assert coverage['characters']==12 and coverage['truncated_files']==['src/a.py']
    assert coverage['eligible_files']==3 and coverage['scope_complete'] is False and coverage['next_offset']==2
    files,coverage=await source_service.select_files('token','acme','widget','sha',paths,{'paths':['src/b.py']})
    assert coverage['eligible_files']==3 and coverage['reviewed_files']==1 and not coverage['scope_complete']
    assert coverage['next_file_offsets']=={}


async def test_remaining_content_advances_at_same_commit_without_losing_files(monkeypatch):
    monkeypatch.setattr(settings,'review_max_files',2); monkeypatch.setattr(settings,'review_max_characters',5)
    async def contents(*args): return 'abcdefghij' if args[-1]=='src/a.py' else 'xy'
    monkeypatch.setattr(source_service,'file_content',contents)
    paths=['src/a.py','src/b.py']
    first,a=await source_service.select_files('token','acme','widget','sha',paths,{})
    assert first[0]['content']=='abcde' and a['budget_skipped_files']==['src/b.py'] and a['next_file_offsets']=={'src/a.py':5}
    second,b=await source_service.select_files('token','acme','widget','sha',paths,{'paths':['src/a.py','src/b.py'],'file_offsets':a['next_file_offsets']})
    assert second[0]['content']=='fghij' and b['next_file_offsets']=={} and b['budget_skipped_files']==['src/b.py']
    third,c=await source_service.select_files('token','acme','widget','sha',paths,{'paths':b['budget_skipped_files']})
    assert third[0]['content']=='xy' and c['reviewed_ranges'][0]=={'path':'src/b.py','start':0,'end':2,'total':2}
    assert not c['scope_complete'] and a['commit_sha']==b['commit_sha']==c['commit_sha']=='sha'


async def test_github_pagination_over_100(monkeypatch):
    from src.core import github_api
    calls=[]
    async def request(token,method,path,params):
        calls.append(params['page']); return list(range(100)) if params['page']==1 else [100,101]
    monkeypatch.setattr(github_api,'request',request)
    result=await github_api.paginate('token','/repos/files')
    assert len(result)==102 and calls==[1,2]


async def test_posting_retry_recovers_existing_comment_without_duplicate(fixture,monkeypatch):
    f=fixture; job=await add_job(f)
    async with f.db() as db:
        r=await db.get(Review,job.review_id); r.status='completed'; r.report_markdown='Saved report'; r.commit_sha='a'*40; await db.commit()
    async def authorize(*args): return 'fixture'
    calls=[]
    async def listing(*args): return [{'body':f'<!-- devreason-review:{job.review_id} -->','html_url':'https://github.com/acme/widget/review/1'}]
    async def request(*args,**kwargs): calls.append(1); raise AssertionError('Duplicate posting')
    monkeypatch.setattr(posting,'authorize_repo',authorize); monkeypatch.setattr(posting,'paginate',listing); monkeypatch.setattr(posting,'request',request)
    for _ in range(2):
        result=await f.client.post(f'/api/reviews/{job.review_id}/post'); assert result.status_code==200
    assert calls==[]


async def test_real_graph_job_saves_result_and_reuses_snapshot_cache(fixture,monkeypatch):
    f=fixture
    from src.agents.graph import compile_review_graph
    from src.agents.nodes import fetch_pr, report_writer, security_agent
    from src.agents import analysis
    from src.services import execution
    from src.tools import vector_search
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore
    calls=[]
    class Model:
        async def ainvoke(self,messages):
            calls.append(1)
            return SimpleNamespace(content='## Review\n\nSelected code analyzed.' if 'senior engineering lead' in messages[0].content else '[]')
    monkeypatch.setattr(analysis,'get_model',lambda **kwargs:Model())
    monkeypatch.setattr(report_writer,'get_model',lambda **kwargs:Model())
    async def authorize(*args): return 'fixture'
    async def rules(*args,**kwargs): return []
    async def tree(*args): return ['src/routes.py']
    async def contents(*args): return 'def endpoint(user_id):\n    return user_id\n'
    monkeypatch.setattr(execution,'authorize_repo',authorize)
    monkeypatch.setattr(vector_search,'search_arch_rules',rules)
    monkeypatch.setattr(fetch_pr,'tree_paths',tree)
    monkeypatch.setattr(source_service,'file_content',contents)
    graph=compile_review_graph(InMemorySaver(),InMemoryStore())
    for index in range(2):
        job=await add_job(f)
        async with f.db() as db:
            row=await db.get(Review,job.review_id); row.mode='snapshot'; row.branch='main'; row.commit_sha='a'*40; row.pr_url=None; row.pr_number=None; await db.commit()
        async def execute(claimed): return await execution.run_review(claimed.review_id,graph,f.redis,claimed.lease_token)
        assert await jobs.run_once(execute)
        async with f.db() as db:
            row=await db.get(Review,job.review_id)
            assert row.status=='completed', row.error_message
            assert row.report_markdown.startswith('## Review') and row.commit_sha=='a'*40
            assert row.coverage['reviewed_paths']==['src/routes.py']
            assert row.coverage['cache_reused']==(index==1)
            assert row.posting_status=='not_requested'
        if index==0: original_calls=len(calls)
    assert len(calls)==original_calls
    history=(await f.client.get('/api/reviews')).json()
    assert history['total']==2 and all(row['mode']=='snapshot' for row in history['items'])


async def test_webhook_rejects_bad_signature_and_handles_revoke_once(fixture,monkeypatch):
    import hmac,hashlib
    f=fixture; monkeypatch.setattr(settings,'github_app_webhook_secret','fixture-webhook')
    body=json.dumps({'action':'deleted','installation':{'id':123}}).encode()
    headers={'X-GitHub-Event':'installation','X-GitHub-Delivery':uuid.uuid4().hex,'X-Hub-Signature-256':'sha256=invalid'}
    assert (await f.client.post('/webhooks/github',content=body,headers=headers)).status_code==400
    headers['X-Hub-Signature-256']='sha256='+hmac.new(b'fixture-webhook',body,hashlib.sha256).hexdigest()
    response=await f.client.post('/webhooks/github',content=body,headers=headers)
    assert response.status_code==200,response.text
    again=await f.client.post('/webhooks/github',content=body,headers=headers)
    assert again.status_code==200
    async with f.db() as db: assert (await db.execute(select(GitHubInstallation).where(GitHubInstallation.connection_id==f.connection))).scalar_one().status=='revoked'
    await f.redis.delete('github_delivery:'+headers['X-GitHub-Delivery'])


async def test_osv_vulnerable_patched_and_cache_preserves_source_file(monkeypatch):
    from src.tools import osv_search
    from unittest.mock import AsyncMock
    cache={}; calls=[]
    class RedisFixture:
        async def get(self,key): return cache.get(key)
        async def setex(self,key,ttl,value): cache[key]=value
        async def aclose(self): pass
    async def redis(): return RedisFixture()
    class ClientFixture:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,json):
            calls.append(json['version'])
            value={'vulns':[{'id':'GHSA-fixture','aliases':['CVE-2026-1234'],'summary':'Unsafe version','severity':[{'type':'CVSS_V3','score':'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H'}],'affected':[{'ranges':[{'events':[{'introduced':'0'},{'fixed':'2.0.0'}]}]}]}]} if json['version']=='1.0.0' else {}
            return SimpleNamespace(raise_for_status=lambda:None,json=lambda:value)
    monkeypatch.setattr(osv_search,'create_redis_pool',redis); monkeypatch.setattr(osv_search.httpx,'AsyncClient',lambda **kw:ClientFixture())
    pkg={'name':'fixture-package','version':'1.0.0','ecosystem':'npm','source_file':'package-lock.json'}
    found=await osv_search.osv_batch_query([pkg,{**pkg,'version':'2.0.0'}])
    assert len(found)==1 and found[0]['cvss_score']==9.8 and found[0]['cve_id']=='CVE-2026-1234' and found[0]['fixed_versions']==['2.0.0']
    repeated=await osv_search.osv_batch_query([{**pkg,'source_file':'other/package-lock.json'}])
    assert repeated[0]['source_file']=='other/package-lock.json' and calls==['1.0.0','2.0.0']


async def test_postgres_checkpoint_resumes_after_worker_instance_is_replaced(fixture,monkeypatch):
    f=fixture
    from src.agents.graph import compile_review_graph
    from src.agents.state import ReviewState,RepoConfig
    from src.agents.nodes import fetch_pr,report_writer
    from src.agents import analysis
    from src.tools import vector_search
    from src.services import execution
    from src.core.checkpointer import get_postgres_checkpointer
    from langgraph.store.memory import InMemoryStore
    class Model:
        async def ainvoke(self,messages): return SimpleNamespace(content='## Saved resumed review' if 'senior engineering lead' in messages[0].content else '[]')
    monkeypatch.setattr(analysis,'get_model',lambda **kw:Model()); monkeypatch.setattr(report_writer,'get_model',lambda **kw:Model())
    fetched=[]
    async def context(*args):
        fetched.append(1)
        return {'title':'Recovery fixture','head':{'sha':'b'*40}},[{'path':'src/routes.py','content':'def route(user_id): return user_id'}],'diff',{'total_files':1,'eligible_files':1,'reviewed_files':1,'reviewed_paths':['src/routes.py'],'scope_complete':True}
    async def authorize(*args): return 'fresh-fixture-token'
    async def rules(*args,**kw): return []
    monkeypatch.setattr(fetch_pr,'pr_context',context); monkeypatch.setattr(execution,'authorize_repo',authorize); monkeypatch.setattr(vector_search,'search_arch_rules',rules)
    pending=await add_job(f); claimed=await jobs.claim_job()
    assert claimed.id==pending.id
    async with f.db() as db: row=await db.get(Review,pending.review_id); thread=row.thread_id
    config={'configurable':{'thread_id':thread}}
    initial=ReviewState(pr_url='https://github.com/acme/widget/pull/1',pr_number=1,repo_config=RepoConfig(repo_id=str(f.repo),review_id=str(row.id),owner='acme',name='widget',github_token='expired-fixture-token',lease_token=claimed.lease_token))
    async with get_postgres_checkpointer() as checkpoint:
        graph=compile_review_graph(checkpoint,InMemoryStore()); graph.interrupt_before_nodes=['code_analyst']
        await graph.ainvoke(initial,config)
        assert (await graph.aget_state(config)).next
    async with f.db() as db:
        job=await db.get(ReviewJob,claimed.id); job.lease_until=datetime.now(timezone.utc)-timedelta(seconds=1); await db.commit()
    recovered=await jobs.claim_job(); assert recovered.attempts==2
    async with get_postgres_checkpointer() as checkpoint:
        replacement=compile_review_graph(checkpoint,InMemoryStore())
        status=await execution.run_review(recovered.review_id,replacement,f.redis,recovered.lease_token)
        assert status=='completed'
        await jobs.finish_job(recovered,status)
        await checkpoint.adelete_thread(thread)
    async with f.db() as db:
        saved=await db.get(Review,row.id)
        assert saved.status=='completed' and saved.report_markdown=='## Saved resumed review'
    assert len(fetched)==1


async def test_metrics_refuse_code_credentials_and_arbitrary_events(fixture):
    client=fixture.client
    assert (await client.post('/api/metrics',json={'event':'review_opened','source_code':'private code'})).status_code==422
    assert (await client.post('/api/metrics',json={'event':'review_opened','token':'credential'})).status_code==422
    assert (await client.post('/api/metrics',json={'event':'arbitrary-event'})).status_code==422
    assert (await client.post('/api/metrics',json={'event':'review_opened','duration_ms':100})).status_code==202


async def test_legacy_approved_rules_without_vectors_remain_enforced(fixture,monkeypatch):
    from src.tools import vector_search
    async with fixture.db() as db:
        db.add(ArchRule(repo_id=fixture.repo,content='Legacy approved policy',status='approved',source='manual'))
        db.add(ArchRule(repo_id=fixture.repo,content='Unapproved candidate',status='suggested',source='suggested'))
        await db.commit()
        monkeypatch.setattr(vector_search,'get_embedder',lambda: (_ for _ in ()).throw(AssertionError('No embedding request needed')))
        rules=await vector_search.search_arch_rules(db,str(fixture.repo),'fixture code')
        assert rules==['Legacy approved policy']


async def test_suggested_rule_batch_failure_keeps_existing_candidates(fixture,monkeypatch):
    from src.services import architecture_rule_service as service
    f=fixture
    async with f.db() as db:
        db.add(ArchRule(repo_id=f.repo,content='Existing candidate',status='suggested',source='suggested')); await db.commit()
    async def authorized(*args): return 'fixture'
    async def snapshot(*args): return {}
    async def suggest(*args): return ['First new rule','Second new rule']
    class Embed:
        calls=0
        async def aembed_query(self,content):
            self.calls+=1
            if self.calls==2: raise RuntimeError('Fixture embedding failure')
            return [0.0]*1536
    embed=Embed()
    monkeypatch.setattr(github,'authorize_repo',authorized); monkeypatch.setattr(service,'_get_repo_access_token',authorized); monkeypatch.setattr(service,'_fetch_repo_snapshot',snapshot); monkeypatch.setattr(service,'_generate_rule_suggestions',suggest); monkeypatch.setattr(memory_service,'get_embedder',lambda:embed)
    response=await f.client.post(f'/api/repos/{f.repo}/rules/suggest',json={'refresh':True})
    assert response.status_code==502
    async with f.db() as db:
        contents=list((await db.execute(select(ArchRule.content).where(ArchRule.repo_id==f.repo))).scalars())
        assert contents==['Existing candidate']


async def test_multiple_accounts_share_installation_without_losing_repo_access(fixture,monkeypatch):
    f=fixture; other=uuid.uuid4()
    async with f.db() as db:
        db.add(GitHubConnection(id=other,clerk_user_id=f.user,github_user_id=8,login='other',access_token_enc=encrypt('fixture-second-token'),status='connected'))
        repo=await db.get(Repo,f.repo); repo.github_repo_id=101; await db.commit()
    async def listing(token,path,**kwargs):
        if path=='/user/installations': return [{'id':123,'account':{'login':'acme'}}]
        return [{'id':99 if token=='fixture-user-token' else 101,'owner':{'login':'acme'},'name':'first-widget' if token=='fixture-user-token' else 'widget'}]
    monkeypatch.setattr(github,'paginate',listing)
    async with f.db() as db:
        repo=await db.get(Repo,f.repo)
        assert await github.authorize_repo(db,f.user,repo)=='fixture-second-token'
        synced=await github_app.sync_verified(db,f.user,123,f.connection)
        assert {row['name'] for row in synced['repositories']}=={'first-widget','widget'}
    listing_response=await f.client.get('/api/repos/browse')
    assert listing_response.json()['total']==2


async def test_rerun_snapshot_resolves_latest_commit_without_old_preview_constraint(fixture,monkeypatch):
    f=fixture; job=await add_job(f)
    async with f.db() as db:
        row=await db.get(Review,job.review_id); row.mode='snapshot'; row.branch='main'; row.pr_url=None; row.pr_number=None; row.scope={'commit_sha':'a'*40,'offset':0}; row.status='completed'; await db.commit()
    monkeypatch.setattr(settings,'branch_reviews_enabled',True)
    async def authorize(*args): return 'fixture'
    async def target(*args,**kw): return {'sha':'b'*40}
    monkeypatch.setattr(reviews,'authorize_repo',authorize); monkeypatch.setattr(reviews,'github_request',target)
    response=await f.client.post(f'/api/reviews/{job.review_id}/rerun')
    assert response.status_code==202,response.text
    async with f.db() as db:
        new=await db.get(Review,uuid.UUID(response.json()['id']))
        assert new.commit_sha=='b'*40 and 'commit_sha' not in new.scope


async def test_all_pr_patches_keep_secret_checks_and_mark_unlisted_files(monkeypatch):
    from src.agents.nodes import fetch_pr,security_agent
    from src.agents.state import ReviewState,RepoConfig
    async def request(*args,**kw): return {'head':{'sha':'a'*40},'changed_files':4}
    async def pages(*args,**kw): return [{'filename':'src/api.py','status':'modified','patch':'+safe_code()'},{'filename':'.env','status':'added','patch':'+password="fixture-secret-value"'}]
    async def contents(*args): return 'safe_code()'
    monkeypatch.setattr(source_service,'request',request); monkeypatch.setattr(source_service,'paginate',pages); monkeypatch.setattr(source_service,'file_content',contents)
    state=ReviewState(pr_url='https://github.com/acme/widget/pull/1',repo_config=RepoConfig(repo_id=str(uuid.uuid4()),review_id=str(uuid.uuid4()),owner='acme',name='widget',github_token='fixture',commit_sha='a'*40))
    fetched=await fetch_pr.run(state)
    assert 'fixture-secret-value' in fetched['pr_diff'] and 'fixture-secret-value' not in fetched['analysis_diff']
    assert fetched['coverage']['unlisted_changed_files']==2 and not fetched['coverage']['scope_complete']
    assert '_analysis_diff' not in fetched['coverage']
    updated=state.model_copy(update={key:value for key,value in fetched.items() if key!='agent_status'})
    result=await security_agent.run(updated)
    assert any(finding.type=='hardcoded_secret' for finding in result['security_findings'])
