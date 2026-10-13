import asyncio
import json
import re
import uuid
from urllib.parse import quote
from fastapi import APIRouter, Depends, Request, HTTPException, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from src.api.deps import get_db, get_redis, get_current_user
from src.db.models import Review, ReviewJob, Repo, Finding
from src.db.repositories.review_repo import get_review
from src.db.repositories.repo_repo import get_repo_by_id
from src.schemas.review import ReviewCreate, ReviewRead, ReviewSummary
from src.core.settings import settings
from src.core.urls import parse_pr_url
from src.services.github_connection_service import authorize_repo
from src.services.stream_service import read_events, TERMINAL
from src.core.github_api import request as github_request
from src.core.github_app import mint_installation_token

router=APIRouter()


async def owned_review(db,review_id,user_id):
    review=await get_review(db,review_id)
    if not review or review.clerk_user_id!=user_id: raise HTTPException(404,'Review not found')
    return review


@router.post('',status_code=202)
async def submit_review(body: ReviewCreate,user=Depends(get_current_user),db=Depends(get_db),idempotency_key: str|None=Header(default=None,max_length=200)):
    if not settings.durable_reviews_enabled: raise HTTPException(503,'Review processing is temporarily disabled')
    if body.mode=='snapshot' and not settings.branch_reviews_enabled: raise HTTPException(409,'Branch reviews are not enabled yet')
    repo=await get_repo_by_id(db,body.repo_id)
    if not repo or repo.clerk_user_id!=user['clerk_user_id']: raise HTTPException(404,'Repository not found')
    token=await authorize_repo(db,user['clerk_user_id'],repo)
    url=None; number=body.pr_number
    if body.mode=='pr':
        url=body.pr_url or f'https://github.com/{repo.owner}/{repo.name}/pull/{number}'
        try: owner,name,number,url=parse_pr_url(url)
        except ValueError as error: raise HTTPException(422,str(error)) from None
        if (owner.lower(),name.lower())!=(repo.owner.lower(),repo.name.lower()): raise HTTPException(422,'This pull request belongs to a different repository')
    scope=body.scope
    if set(scope)-{'offset','paths','commit_sha','file_offsets'}: raise HTTPException(422,'Unknown scope option')
    offsets=scope.get('file_offsets',{})
    if not isinstance(offsets,dict) or len(offsets)>settings.review_max_files or any(not isinstance(path,str) or not isinstance(start,int) or isinstance(start,bool) or start<0 for path,start in offsets.items()): raise HTTPException(422,'Invalid file content offsets')
    if 'paths' in scope and (not isinstance(scope['paths'],list) or len(scope['paths'])>5000 or any(not isinstance(path,str) or len(path)>1000 for path in scope['paths'])): raise HTTPException(422,'Invalid selected paths')
    offset=scope.get('offset',0)
    if not isinstance(offset,int) or isinstance(offset,bool) or offset<0: raise HTTPException(422,'Scope offset must be a non-negative integer')
    target=await github_request(token,'GET',f'/repos/{repo.owner}/{repo.name}/pulls/{number}' if body.mode=='pr' else f'/repos/{repo.owner}/{repo.name}/commits/{quote(body.commit_sha or body.branch,safe="")}')
    sha=target['head']['sha'] if body.mode=='pr' else target['sha']
    if scope.get('commit_sha') and scope['commit_sha']!=sha: raise HTTPException(409,'This branch changed after the scope preview. Refresh the preview.')
    key=idempotency_key or str(uuid.uuid4())
    existing=(await db.execute(select(ReviewJob).where(ReviewJob.clerk_user_id==user['clerk_user_id'],ReviewJob.request_key==key))).scalar_one_or_none()
    if existing:
        prior=await get_review(db,existing.review_id)
        if prior.repo_id!=repo.id or prior.mode!=body.mode or prior.pr_number!=number or prior.branch!=body.branch or (prior.scope or {})!=scope: raise HTTPException(409,'Idempotency key was used for a different review')
        return {'id':str(existing.review_id),'status':prior.status}
    review_id=uuid.uuid4()
    row=Review(id=review_id,clerk_user_id=user['clerk_user_id'],repo_id=repo.id,pr_url=url,pr_number=number if body.mode=='pr' else None,mode=body.mode,branch=body.branch,commit_sha=sha,title=target.get('title') or f'{repo.name} · {body.branch}',scope=scope,status='pending',thread_id=f"{user['clerk_user_id']}::{repo.id}::{review_id}",posting_status='pending' if body.post_to_github else 'not_requested')
    db.add(row); db.add(ReviewJob(id=uuid.uuid4(),review_id=review_id,clerk_user_id=user['clerk_user_id'],request_key=key,status='pending'))
    try: await db.commit()
    except IntegrityError:
        await db.rollback()
        await db.refresh(repo)
        existing=(await db.execute(select(ReviewJob).where(ReviewJob.clerk_user_id==user['clerk_user_id'],ReviewJob.request_key==key))).scalar_one_or_none()
        if not existing: raise
        prior=await get_review(db,existing.review_id)
        if prior.repo_id!=repo.id or prior.mode!=body.mode or prior.pr_number!=number or prior.branch!=body.branch or (prior.scope or {})!=scope: raise HTTPException(409,'Idempotency key was used for a different review')
        return {'id':str(existing.review_id),'status':prior.status}
    return {'id':str(review_id),'status':'pending'}


@router.get('')
async def list_reviews(repo_id: uuid.UUID|None=None,status: str|None=None,q: str='',page: int=Query(1,ge=1),page_size: int=Query(20,ge=1,le=100),summary: bool=False,user=Depends(get_current_user),db=Depends(get_db)):
    filters=[Review.clerk_user_id==user['clerk_user_id']]
    if repo_id: filters.append(Review.repo_id==repo_id)
    if status: filters.append(Review.status==status)
    if q: filters.append(Review.title.ilike('%'+q.replace('%','\\%').replace('_','\\_')+'%',escape='\\'))
    if summary:
        fields=[getattr(Review,name) for name in ReviewSummary.model_fields if name!='finding_count']
        finding_count=select(func.count(Finding.id)).where(Finding.review_id==Review.id).correlate(Review).scalar_subquery().label('finding_count')
        rows=(await db.execute(select(*fields,finding_count,func.count().over().label('total_count')).where(*filters).order_by(Review.created_at.desc(),Review.id).offset((page-1)*page_size).limit(page_size))).mappings().all()
        total=rows[0]['total_count'] if rows else (await db.execute(select(func.count()).select_from(Review).where(*filters))).scalar_one()
        return {'items':[ReviewSummary.model_validate(dict(row)) for row in rows],'total':total,'page':page,'page_size':page_size}
    from sqlalchemy.orm import selectinload
    total=(await db.execute(select(func.count()).select_from(Review).where(*filters))).scalar_one()
    rows=(await db.execute(select(Review).options(selectinload(Review.findings)).where(*filters).order_by(Review.created_at.desc(),Review.id).offset((page-1)*page_size).limit(page_size))).scalars().all()
    return {'items':[ReviewRead.model_validate(row) for row in rows],'total':total,'page':page,'page_size':page_size}


@router.get('/{review_id}/stream')
async def stream_review(review_id: uuid.UUID,request: Request,last_event_id: str|None=Header(default=None),cursor: str='0-0',user=Depends(get_current_user),db=Depends(get_db),redis=Depends(get_redis)):
    owned=(await db.execute(select(Review.id).where(Review.id==review_id,Review.clerk_user_id==user['clerk_user_id']))).scalar_one_or_none()
    if not owned: raise HTTPException(404,'Review not found')
    # The initial ownership read must not occupy a connection for an entire SSE
    # session. Each fallback status poll uses a separate, short session.
    await db.close()
    position=last_event_id or cursor
    if not re.fullmatch(r'\d+-\d+',position): raise HTTPException(422,'Invalid event cursor')
    async def events():
        nonlocal position
        from src.db.base import AsyncSessionLocal
        while not await request.is_disconnected():
            try: entries=await read_events(redis,str(review_id),position)
            except Exception: entries=[]; await asyncio.sleep(2)
            for event_id,payload in entries:
                position=event_id
                yield f'id: {event_id}\ndata: {payload}\n\n'
            # Drain all available batches before emitting authoritative terminal state.
            if entries: continue
            async with AsyncSessionLocal() as current_db:
                current=(await current_db.execute(select(Review.status,Review.report_markdown,Review.github_comment_url,Review.error_message).where(Review.id==review_id))).first()
            if current and current.status in TERMINAL:
                payload={'event':'complete','data':{'status':current.status,'report':current.report_markdown,'github_url':current.github_comment_url,'error':current.error_message}}
                yield 'data: '+json.dumps(payload)+'\n\n'; break
            yield ': keepalive\n\n'
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


@router.get('/{review_id}')
async def detail(review_id: uuid.UUID,user=Depends(get_current_user),db=Depends(get_db)) -> ReviewRead:
    return ReviewRead.model_validate(await owned_review(db,review_id,user['clerk_user_id']))


@router.post('/{review_id}/cancel')
async def cancel(review_id: uuid.UUID,user=Depends(get_current_user),db=Depends(get_db)):
    review=await owned_review(db,review_id,user['clerk_user_id'])
    if review.status in TERMINAL: return {'status':review.status}
    job=(await db.execute(select(ReviewJob).where(ReviewJob.review_id==review_id).with_for_update())).scalar_one_or_none()
    if not job: raise HTTPException(409,'This legacy review has no active job')
    job.cancel_requested=True
    if job.status=='pending':
        from datetime import datetime, timezone
        job.status='cancelled'; review.status='cancelled'; review.completed_at=datetime.now(timezone.utc)
    await db.commit(); return {'status':review.status,'cancel_requested':True}


@router.post('/{review_id}/rerun',status_code=202)
async def rerun(review_id: uuid.UUID,user=Depends(get_current_user),db=Depends(get_db),idempotency_key: str|None=Header(default=None)):
    row=await owned_review(db,review_id,user['clerk_user_id'])
    fresh_scope={key:value for key,value in (row.scope or {}).items() if key not in ('commit_sha','file_offsets')}
    return await submit_review(ReviewCreate(repo_id=row.repo_id,pr_url=row.pr_url,pr_number=row.pr_number,mode=row.mode,branch=row.branch,scope=fresh_scope),user,db,idempotency_key)
