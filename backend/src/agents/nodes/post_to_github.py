
import json
import structlog
from src.agents.state import ReviewState
from src.tools.github_mcp import get_mcp_tools

log = structlog.get_logger()


def _parse_review_result(result) -> dict:
    if isinstance(result, dict):
        return result

    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                try:
                    return json.loads(item["text"])
                except json.JSONDecodeError:
                    return {"raw": item["text"]}

    return {"raw": str(result)}


async def run(state: ReviewState) -> dict:
    """
    Posts the final review report as a GitHub PR review comment.
    Only runs if repo_config.post_to_github is True.
    Uses GitHub hosted MCP tool: pull_request_review_write.
    """
    if not state.repo_config.post_to_github:
        return {}

    mcp_tools = await get_mcp_tools(state.repo_config.github_token.get_secret_value())
    if "pull_request_review_write" not in mcp_tools:
        log.warning("post_to_github: MCP tool not available")
        return {
            "agent_status": {
                "post_to_github": {
                    "status": "missing_tool",
                }
            }
        }

    try:
        parts = state.pr_url.rstrip("/").split("/")
        owner = parts[-4]
        repo = parts[-3]
        pull_number = state.pr_number

        review_tool = mcp_tools["pull_request_review_write"]
        result = await review_tool.ainvoke({
            "method": "create",
            "owner": owner,
            "repo": repo,
            "pullNumber": pull_number,
            "body": state.final_report or "Review completed. See findings.",
            "event": "COMMENT",
        })

        payload = _parse_review_result(result)
        github_url = payload.get("html_url")
        log.info("post_to_github complete", url=github_url)
        return {
            "github_comment_url": github_url,
            "agent_status": {
                "post_to_github": {
                    "status": "completed",
                    "github_comment_url": github_url,
                }
            },
        }

    except Exception as e:
        log.error("post_to_github failed", error=str(e))
        return {
            "agent_status": {
                "post_to_github": {
                    "status": "failed",
                    "error": str(e),
                }
            }
        }