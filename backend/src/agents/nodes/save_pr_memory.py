
from datetime import datetime, timezone
import structlog
from src.agents.state import ReviewState

log = structlog.get_logger()


async def run(state: ReviewState, store) -> dict:
    """
    Writes this review's merged findings to LangGraph Store.
    Namespace: ("repos", repo_id, "prs", pr_number)
    Key: review_id (unique per submission — never reused)

    This is what load_pr_history will return on the next review of this PR.
    """
    if state.error: return {}
    namespace = ("repos", state.repo_config.repo_id, "prs" if state.repo_config.mode=='pr' else 'branches', str(state.pr_number) if state.repo_config.mode=='pr' else state.repo_config.branch or 'snapshot')

    try:
        await store.aput(
            namespace,
            state.repo_config.review_id,
            {
                "merged_findings": [f.model_dump() for f in state.merged_findings],
                "report_summary": (state.final_report or "")[:500],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pr_url": state.pr_url,
            },
        )
        log.info(
            "save_pr_memory complete",
            pr_number=state.pr_number,
            findings_count=len(state.merged_findings),
        )
    except Exception as e:
        log.error("save_pr_memory failed", error=str(e))

    return {}
