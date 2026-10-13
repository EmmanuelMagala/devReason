
from datetime import datetime, timezone
import structlog
from src.agents.state import ReviewState

log = structlog.get_logger()


async def run(state: ReviewState, store) -> dict:
    """
    Updates repo-level aggregated statistics after every completed review.
    Namespace: ("repos", repo_id, "insights")
    Key: "aggregated" (single document, updated in place)

    Over time this builds a picture of which issue types recur most
    and which files are most frequently flagged.
    """
    if state.error: return {}
    namespace = ("repos", state.repo_config.repo_id, "insights")

    try:
        existing = await store.aget(namespace, "aggregated")
        insights = existing.value if existing else {
            "common_issue_types": {},
            "hot_files": {},
            "total_reviews": 0,
        }

        processed=insights.setdefault('review_ids',[])
        if state.repo_config.review_id in processed: return {}
        processed.append(state.repo_config.review_id)
        # Count from deduplicated merged_findings only (not raw agent outputs)
        for finding in state.merged_findings:
            key = finding.type
            insights["common_issue_types"][key] = insights["common_issue_types"].get(key, 0) + 1
            if finding.file:
                insights["hot_files"][finding.file] = insights["hot_files"].get(finding.file, 0) + 1

        insights["total_reviews"] = insights.get("total_reviews", 0) + 1
        insights["last_updated"] = datetime.now(timezone.utc).isoformat()

        await store.aput(namespace, "aggregated", insights)
        log.info("update_project_insights complete", total_reviews=insights["total_reviews"])

    except Exception as e:
        log.error("update_project_insights failed", error=str(e))

    return {}
