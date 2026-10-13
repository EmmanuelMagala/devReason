"""Execute saved targets; database state survives worker and stream failures."""
import uuid
import time
from sqlalchemy import select, update
from src.db.base import AsyncSessionLocal
from src.db.models import Review, Repo, ArchRule
from src.agents.state import ReviewState, RepoConfig
from src.core.github_app import mint_installation_token
from src.services.github_connection_service import authorize_repo
from src.services.stream_service import push_event, set_status
from src.services.outcomes import review_outcome
from src.schemas.stream import StreamEvent
from src.services.jobs import fence
from src.services.review_cache import key_for, get_cached, save_cached
from src.db.repositories.review_repo import save_findings
from src.schemas.review import Finding
from datetime import datetime, timezone
import structlog


async def run_review(review_id, graph, redis, lease_token=None):
    started=time.perf_counter()
    async with AsyncSessionLocal() as db:
        review=(await db.execute(select(Review).where(Review.id==review_id))).scalar_one()
        repo=(await db.execute(select(Repo).where(Repo.id==review.repo_id))).scalar_one()
    config={'configurable':{'thread_id':review.thread_id},'run_name':f'review:{review_id}'}
    try:
        checkpoint=await graph.aget_state(config)
        async with AsyncSessionLocal() as db:
            token=await authorize_repo(db,review.clerk_user_id,repo)
            rules=list((await db.execute(select(ArchRule.content).where(ArchRule.repo_id==repo.id,ArchRule.status=='approved').order_by(ArchRule.content))).scalars())
            if checkpoint and checkpoint.next:
                prior_config=checkpoint.values.get('repo_config')
                prior_rules=prior_config.get('architecture_rules') if isinstance(prior_config,dict) else getattr(prior_config,'architecture_rules',None)
                if prior_rules is not None: rules=prior_rules
            cache_key=await key_for(db,review,rules) if review.mode=='snapshot' else None
            cached=await get_cached(db,cache_key) if cache_key else None
            if checkpoint and checkpoint.next: cached=None
        repo_config=RepoConfig(repo_id=str(repo.id),review_id=str(review.id),owner=repo.owner,name=repo.name,github_token=token,post_to_github=False,mode=review.mode,branch=review.branch,commit_sha=review.commit_sha,scope=review.scope or {},lease_token=lease_token,architecture_rules=rules)
        if checkpoint and checkpoint.next:
            # Tokens in old checkpoints may have expired; refresh before resume.
            await graph.aupdate_state(config,{'repo_config':repo_config})
            initial=None
        else:
            initial=ReviewState(pr_url=review.pr_url or '',pr_number=review.pr_number or 0,repo_config=repo_config)
        async with AsyncSessionLocal() as db:
            if lease_token: await fence(db,review_id,lease_token)
            await db.execute(update(Review).where(Review.id==review_id).values(status='running',error_message=None)); await db.commit()
        await set_status(redis,str(review_id),'running')
        async def stream():
            if cached or (checkpoint and not checkpoint.next and checkpoint.values.get('final_report')): return
            async for item in graph.astream_events(initial,config=config,version='v2'): yield item
        async for event in stream():
            node=event.get('metadata',{}).get('langgraph_node') or event.get('name')
            kind=event.get('event')
            if kind=='on_chain_start' and event.get('name') in graph.nodes:
                await push_event(redis,str(review_id),StreamEvent(event='agent_start',agent=event['name']))
            elif kind=='on_chain_end' and event.get('name') in graph.nodes:
                output=event.get('data',{}).get('output') or {}
                status=output.get('agent_status',{}).get(event['name'],{}) if isinstance(output,dict) else {}
                await push_event(redis,str(review_id),StreamEvent(event='agent_complete',agent=event['name'],data=status))
                async with AsyncSessionLocal() as db:
                    if lease_token: await fence(db,review_id,lease_token)
                    current=(await db.execute(select(Review).where(Review.id==review_id))).scalar_one()
                    current.check_outcomes={**(current.check_outcomes or {}),event['name']:status or {'status':'completed'}}
                    if isinstance(output,dict) and output.get('coverage'): current.coverage=output['coverage']
                    await db.commit()
                if node=='merge_findings':
                    findings=output.get('merged_findings',[])
                    await push_event(redis,str(review_id),StreamEvent(event='findings_ready',data={'findings':[f.model_dump() for f in findings]}))
                if node=='report_writer' and output.get('final_report'):
                    await push_event(redis,str(review_id),StreamEvent(event='report_ready',data={'report':output['final_report']}))
            elif kind=='on_chat_model_stream' and node=='report_writer':
                from src.services.review_service import _extract_stream_token_text
                chunk=event.get('data',{}).get('chunk')
                text=_extract_stream_token_text(getattr(chunk,'content',None))
                if text: await push_event(redis,str(review_id),StreamEvent(event='report_token',agent=node,data={'token':text}))
        values=cached or (await graph.aget_state(config)).values
        outcome=review_outcome(values.get('agent_status',{}),values.get('error'),values.get('coverage'))
        findings=values.get('merged_findings',[])
        recommendation='incomplete' if outcome!='completed' else 'request_changes' if any((f.get('severity') if isinstance(f,dict) else f.severity) in ('critical','high') for f in findings) else 'approve'
        metadata=values.get('pr_metadata',{})
        async with AsyncSessionLocal() as db:
            if lease_token: await fence(db,review_id,lease_token)
            current=(await db.execute(select(Review).where(Review.id==review_id))).scalar_one()
            checks={**(current.check_outcomes or {}),**values.get('agent_status',{})}
            if cached: await save_findings(db,review_id,repo.id,review.pr_number,[Finding.model_validate(f) for f in findings],commit=False)
            await db.execute(update(Review).where(Review.id==review_id).values(status=outcome,completed_at=datetime.now(timezone.utc),report_markdown=values.get('final_report'),error_message=values.get('error'),check_outcomes=checks,coverage={**(values.get('coverage') or {}),'cache_reused':bool(cached)},recommendation=recommendation,commit_sha=metadata.get('head',{}).get('sha') or review.commit_sha,title=metadata.get('title') or review.title))
            if cache_key and not cached and not (checkpoint and checkpoint.next) and outcome in ('completed','partial') and all(s.get('status') not in ('failed','partial','timeout','rule_lookup_failed') for s in values.get('agent_status',{}).values()): await save_cached(db,cache_key,repo.id,values)
            await db.commit()
        if review.posting_status=='pending' and outcome in ('completed','partial'):
            from src.services.posting import post_report
            async with AsyncSessionLocal() as db:
                try: await post_report(db,review_id,review.clerk_user_id)
                except Exception: pass
        await set_status(redis,str(review_id),outcome)
        await push_event(redis,str(review_id),StreamEvent(event='complete',data={'status':outcome,'report':values.get('final_report'),'elapsed_ms':round((time.perf_counter()-started)*1000)}))
        structlog.get_logger().info('review_finished',status=outcome,elapsed_ms=round((time.perf_counter()-started)*1000),attempt_recovered=bool(checkpoint and checkpoint.next))
        return outcome
    except Exception:
        structlog.get_logger().info('review_finished',status='failed',elapsed_ms=round((time.perf_counter()-started)*1000))
        async with AsyncSessionLocal() as db:
            if lease_token: await fence(db,review_id,lease_token)
            await db.execute(update(Review).where(Review.id==review_id).values(status='failed',error_message='Review failed. Verify repository access and retry.')); await db.commit()
        await set_status(redis,str(review_id),'failed')
        await push_event(redis,str(review_id),StreamEvent(event='error',data={'message':'Review failed. Verify repository access and retry.'}))
        return 'failed'
