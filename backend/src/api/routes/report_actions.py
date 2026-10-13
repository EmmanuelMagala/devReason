import re
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.api.deps import get_db, get_current_user
from src.api.routes.reviews import owned_review
from src.db.models import Review
from src.services.posting import post_report, preview

router=APIRouter()


@router.get('/{review_id}/posting-preview')
async def posting_preview(review_id: uuid.UUID,user=Depends(get_current_user),db=Depends(get_db)):
    row=await owned_review(db,review_id,user['clerk_user_id'])
    return {'body':preview(row),'target_url':row.pr_url,'posting_status':row.posting_status}


@router.post('/{review_id}/post')
async def post(review_id: uuid.UUID,user=Depends(get_current_user),db=Depends(get_db)):
    return await post_report(db,review_id,user['clerk_user_id'])


def finding_key(f):
    return (f.agent,f.type,f.file or '',re.sub(r'\s+',' ',f.message).strip().lower())


@router.get('/{review_id}/comparison')
async def compare(review_id: uuid.UUID,user=Depends(get_current_user),db=Depends(get_db)):
    current=await owned_review(db,review_id,user['clerk_user_id'])
    prior=(await db.execute(select(Review).options(selectinload(Review.findings)).where(Review.clerk_user_id==user['clerk_user_id'],Review.repo_id==current.repo_id,Review.mode==current.mode,Review.pr_number==current.pr_number,Review.branch==current.branch,Review.created_at<current.created_at,Review.status.in_(['completed','partial'])).order_by(Review.created_at.desc()).limit(1))).scalar_one_or_none()
    if not prior: return {'previous_review_id':None,'new':len(current.findings),'recurring':0,'resolved':0,'coverage_comparable':False}
    now={finding_key(f) for f in current.findings}; before={finding_key(f) for f in prior.findings}
    comparable=current.status=='completed' and prior.status=='completed' and (current.scope or {})==(prior.scope or {}) and set((current.coverage or {}).get('reviewed_paths',[]))==set((prior.coverage or {}).get('reviewed_paths',[]))
    return {'previous_review_id':str(prior.id),'new':len(now-before),'recurring':len(now&before),'resolved':len(before-now) if comparable else None,'coverage_comparable':comparable}
