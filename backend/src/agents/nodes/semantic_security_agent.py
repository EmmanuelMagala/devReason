import json
import asyncio
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.state import ReviewState, Finding
from src.core.llm import get_model

log = structlog.get_logger()

SYSTEM_PROMPT = """You are a senior application security reviewer.
Review the provided code changes for security issues such as:
1. Missing or weak authorization checks
2. Trust boundary mistakes around user_id, project_id, workspace_id, repo-scoped access, or role checks
3. WebSocket or realtime event authorization mistakes
4. Sensitive data exposure via events, controllers, or API responses
5. Validation gaps that could allow malicious input or broken access control

Focus on concrete security risks in the changed source files. Ignore lockfile-only noise unless it directly impacts security.

Return ONLY a JSON array. No markdown. No explanation. No backticks.
Each object must have: severity (critical/high/medium/low), type, file, line (integer or null), message, suggestion.
If no issues found, return [].
"""


async def run(state: ReviewState) -> dict:
    from src.agents.analysis import analyze
    return await analyze(state, 'semantic_security_agent', SYSTEM_PROMPT, _build_context(state), 'semantic_security_findings')


def _build_context(state: ReviewState) -> str:
    diff = (state.analysis_diff or state.pr_diff)
    files = "\n\n".join(
        f"=== {f['path']} (first source line: {f.get('start_line',1)}) ===\n{f['content']}"
        for f in state.changed_files
    )
    if state.repo_config.mode=='snapshot': return f"SNAPSHOT SOURCE:\n{files}"
    return f"PR DIFF:\n{diff}\n\nCHANGED SOURCE FILES:\n{files}"


def _parse_findings(raw: str) -> list[Finding]:
    from src.agents.analysis import parse_findings
    return parse_findings(raw, 'semantic_security_agent')
