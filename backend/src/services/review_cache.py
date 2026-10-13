import hashlib
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from src.db.models import ReviewCache, ArchRule
from src.core.settings import settings


async def key_for(db, review, rules=None):
    if rules is None: rules=list((await db.execute(select(ArchRule.content).where(ArchRule.repo_id==review.repo_id,ArchRule.status=='approved').order_by(ArchRule.content))).scalars())
    config={'version':3,'repo':str(review.repo_id),'commit':review.commit_sha,'mode':review.mode,'scope':review.scope or {},'model':settings.openai_model,'rules':rules,'limits':[settings.review_max_files,settings.review_max_characters,settings.review_chunk_characters]}
    return hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()


async def get_cached(db,key):
    row=(await db.execute(select(ReviewCache).where(ReviewCache.key==key,ReviewCache.created_at>datetime.now(timezone.utc)-timedelta(hours=1)))).scalar_one_or_none()
    return row.payload if row else None


async def save_cached(db,key,repo_id,values):
    payload={name:values.get(name) for name in ('merged_findings','final_report','coverage','agent_status','pr_metadata','error')}
    payload['merged_findings']=[f if isinstance(f,dict) else f.model_dump() for f in payload['merged_findings'] or []]
    stmt=insert(ReviewCache).values(key=key,repo_id=repo_id,payload=payload,created_at=datetime.now(timezone.utc))
    await db.execute(stmt.on_conflict_do_update(index_elements=['key'],set_={'payload':payload,'created_at':datetime.now(timezone.utc)}))
