
import structlog
from langchain_mcp_adapters.client import MultiServerMCPClient

log = structlog.get_logger()

GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"


async def get_mcp_tools(github_token: str) -> dict:
    """
    Connects to GitHub's hosted MCP endpoint.
    No server to run — GitHub hosts it. The provided token authenticates the caller.
    Returns a dict of tool_name → LangChain-compatible tool object.
    Called per review with either a GitHub App installation token or a legacy repo PAT.
    """
    if not github_token:
        raise ValueError("A GitHub token is required to initialize MCP tools")

    try:
        client = MultiServerMCPClient({
            "github": {
                "url": GITHUB_MCP_URL,
                "transport": "streamable_http",
                "headers": {
                    "Authorization": f"Bearer {github_token}"
                },
            }
        })
        tools = await client.get_tools()
        tool_dict = {tool.name: tool for tool in tools}
        log.info("GitHub MCP tools loaded", tools=list(tool_dict.keys()))
        return tool_dict
    except Exception as e:
        log.error("Failed to load GitHub MCP tools", error=str(e))
        # Return empty dict — nodes will handle missing tools gracefully
        return {}