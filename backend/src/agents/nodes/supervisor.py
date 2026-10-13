
import structlog
from langgraph.types import Send
from src.agents.state import ReviewState

log = structlog.get_logger()


async def run(state: ReviewState) -> dict:
    """
    Reads the PR context and decides which agents to dispatch.
    Currently always dispatches all three — could be made conditional
    (e.g. skip security if no dependency files changed).
    Returns nothing to state — the routing is done via the router function.
    """
    log.info(
        "supervisor dispatching agents",
        pr_number=state.pr_number,
        has_prior=len(state.prior_findings) > 0,
        semantic_security=_should_run_semantic_security(state),
    )
    return {} if _should_run_semantic_security(state) else {'agent_status':{'semantic_security_agent':{'status':'skipped','reason':'No application-security-sensitive source was identified in this scope.'}}}


def _should_run_semantic_security(state: ReviewState) -> bool:
    if state.repo_config.mode=='snapshot': return True
    risky_path_markers = (
        "/auth",
        "/middleware",
        "/socket",
        "/sockets",
        "/permission",
        "/permissions",
        "/member",
        "/members",
        "/workspace",
        "/project",
        "/controller",
        "/route",
        "/guard",
    )
    risky_tokens = (
        "socket",
        "websocket",
        "emit(",
        "authorization",
        "authorize",
        "permission",
        "workspace_id",
        "project_id",
        "user_id",
        "clerk",
        "member",
        "role",
        "password", "login", "token", "cookie", "session", "csrf", "cors", "innerhtml", "eval(", "execute(", "query(",
    )

    for changed_file in state.changed_files:
        path = changed_file.get("path", "").lower()
        content = changed_file.get("content", "").lower()
        if any(marker in path for marker in risky_path_markers):
            return True
        if any(token in content for token in risky_tokens):
            return True

    diff = (state.analysis_diff or state.pr_diff).lower()
    return any(token in diff for token in risky_tokens)


def supervisor_router(state: ReviewState) -> list[Send]:
    """
    Issues Send() commands to run all three agents in parallel.
    LangGraph executes all three simultaneously.
    All must complete before merge_findings runs.
    """
    if state.error:
        return [Send('security_agent',state)] if state.pr_diff else [Send('merge_findings',state)]
    targets = [
        Send("code_analyst", state),
        Send("security_agent", state),
        Send("architecture_agent", state),
    ]
    if _should_run_semantic_security(state):
        targets.append(Send("semantic_security_agent", state))
    return targets
