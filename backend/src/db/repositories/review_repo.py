
import uuid
from datetime import datetime, timezone
from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Review, Finding as FindingModel
from src.schemas.review import Finding


async def create_review(
    db: AsyncSession,
    review_id: uuid.UUID,
    clerk_user_id: str,
    repo_id: uuid.UUID,
    pr_url: str,
    pr_number: int,
    thread_id: str,
) -> Review:
    review = Review(
        id=review_id,
        clerk_user_id=clerk_user_id,
        repo_id=repo_id,
        pr_url=pr_url,
        pr_number=pr_number,
        thread_id=thread_id,
        status="pending",
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def get_review(db: AsyncSession, review_id: uuid.UUID) -> Review | None:
    result = await db.execute(
        select(Review)
        .options(selectinload(Review.findings))
        .where(Review.id == review_id)
    )
    return result.scalar_one_or_none()


async def update_review_status(
    db: AsyncSession,
    review_id: uuid.UUID,
    status: str,
    report_markdown: str | None = None,
    github_comment_url: str | None = None,
    error_message: str | None = None,
    commit: bool = True,
) -> None:
    values = {"status": status}
    if status in ('completed','partial','failed','cancelled'):
        values["completed_at"] = datetime.now(timezone.utc)
    if report_markdown is not None:
        values["report_markdown"] = report_markdown
    if github_comment_url is not None:
        values["github_comment_url"] = github_comment_url
    if error_message is not None:
        values["error_message"] = error_message

    await db.execute(update(Review).where(Review.id == review_id).values(**values))
    if commit:
        await db.commit()


async def save_findings(
    db: AsyncSession,
    review_id: uuid.UUID,
    repo_id: uuid.UUID,
    pr_number: int,
    findings: list[Finding],
    commit: bool = True,
) -> None:
    await db.execute(delete(FindingModel).where(FindingModel.review_id == review_id))

    for f in findings:
        row = FindingModel(
            id=uuid.uuid4(),
            review_id=review_id,
            repo_id=repo_id,
            pr_number=pr_number,
            agent=f.agent,
            severity=f.severity,
            type=f.type,
            file=f.file,
            line=f.line,
            message=f.message,
            suggestion=f.suggestion,
            cwe_id=f.cwe_id,
            cvss_score=f.cvss_score,
        )
        db.add(row)
    if commit:
        await db.commit()
