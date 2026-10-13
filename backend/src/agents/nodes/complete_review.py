import uuid

import structlog

from src.agents.state import ReviewState
from src.db.base import AsyncSessionLocal
from src.db.repositories.review_repo import update_review_status
from src.services.outcomes import review_outcome

log = structlog.get_logger()


async def run(state: ReviewState) -> dict:
    review_id = uuid.UUID(state.repo_config.review_id)

    if state.repo_config.lease_token:
        # The worker commits terminal state atomically with coverage and checks.
        return {"agent_status": {"complete_review": {"status": "completed"}}}
    async with AsyncSessionLocal() as db:
        await update_review_status(
            db,
            review_id,
            review_outcome(state.agent_status, state.error, state.coverage),
            report_markdown=state.final_report,
            github_comment_url=state.github_comment_url,
        )

    log.info(
        "complete_review complete",
        review_id=state.repo_config.review_id,
        github_comment_url=state.github_comment_url,
    )
    return {
        "agent_status": {
            "complete_review": {
                "status": "completed",
                "github_comment_url": state.github_comment_url,
            }
        }
    }
