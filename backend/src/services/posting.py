"""Explicit, serialized, idempotent GitHub publication; analysis stays saved."""
from sqlalchemy import select
from fastapi import HTTPException
from src.db.models import Review, Repo
from src.core.github_api import request, paginate
from src.services.github_connection_service import authorize_repo


def preview(review):
    if review.mode!='pr': raise HTTPException(409,'Snapshot reviews cannot be posted to a pull request')
    if review.status not in ('completed','partial') or not review.report_markdown:
        raise HTTPException(409,'A saved report is required before posting')
    if not review.commit_sha: raise HTTPException(409,'This historical report has no commit reference. Rerun it before posting.')
    marker=f'<!-- devreason-review:{review.id} -->'
    return f'{marker}\n## DevReason review\nCommit: `{review.commit_sha or "unknown"}`\nStatus: **{review.status}**\n\n{review.report_markdown}'


async def post_report(db, review_id, user_id):
    row=(await db.execute(select(Review).where(Review.id==review_id,Review.clerk_user_id==user_id).with_for_update())).scalar_one_or_none()
    if not row: raise HTTPException(404,'Review not found')
    body=preview(row)
    if row.posting_status=='posted' and row.github_comment_url:
        return {'status':'posted','url':row.github_comment_url}
    repo=(await db.execute(select(Repo).where(Repo.id==row.repo_id))).scalar_one()
    try:
        # Publish with the user's App token, preserving their current permissions.
        token=await authorize_repo(db,user_id,repo)
        # authorize_repo may commit a verified binding; reacquire the publication lock.
        row=(await db.execute(select(Review).where(Review.id==review_id).with_for_update())).scalar_one()
        if row.posting_status=='posted': return {'status':'posted','url':row.github_comment_url}
        base=f'/repos/{repo.owner}/{repo.name}/pulls/{row.pr_number}'
        reviews=await paginate(token,base+'/reviews')
        marker=f'<!-- devreason-review:{row.id} -->'
        existing=next((item for item in reviews if marker in (item.get('body') or '')),None)
        result=existing or await request(token,'POST',base+'/reviews',json={'body':body,'event':'COMMENT','commit_id':row.commit_sha})
        row.github_comment_url=result['html_url']; row.posting_status='posted'
        await db.commit()
        return {'status':'posted','url':row.github_comment_url}
    except Exception:
        await db.rollback()
        row=(await db.execute(select(Review).where(Review.id==review_id).with_for_update())).scalar_one()
        if row.posting_status!='posted': row.posting_status='failed'
        await db.commit()
        raise HTTPException(502,'The report is saved, but GitHub posting failed. Check permissions and retry.') from None
