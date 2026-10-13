
import structlog
from src.agents.state import ReviewState

log = structlog.get_logger()


async def run(state: ReviewState, store) -> dict:
    """
    Loads aggregated repo-level patterns from the Store.
    Only injects context if insights exist — new repos will have nothing here.
    After a repo has 5+ reviews this becomes genuinely valuable context.
    """
    namespace = ("repos", state.repo_config.repo_id, "insights")

    try:
        item = await store.aget(namespace, "aggregated")
        if item and item.value:
            log.info("project_insights loaded", repo_id=state.repo_config.repo_id)
            return {"project_insights": item.value}
        return {"project_insights": {}}
    except Exception as e:
        log.warning("load_project_insights failed", error=str(e))
        return {"project_insights": {}}