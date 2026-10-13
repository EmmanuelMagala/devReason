
import json
import asyncio
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.state import ReviewState, Finding
from src.core.llm import get_model

log = structlog.get_logger()

SYSTEM_PROMPT = """You are a senior code reviewer. Analyse the provided code diff for:
1. High cyclomatic complexity (flag functions with > 10 branches)
2. Missing error handling (uncaught exceptions, unhandled promise rejections)
3. Code duplication and anti-patterns
4. Missing or inadequate test coverage for changed logic
5. Poor naming or unclear variable/function names

If prior_findings are provided, check each one against the current diff:
- If the issue is no longer present: do NOT include it in your output
- If the issue is still present: include it and note "recurring issue"
- New issues not in prior_findings: include normally

Return ONLY a JSON array. No markdown. No explanation. No backticks.
Each object must have: severity (critical/high/medium/low), type, file, line (integer or null), message, suggestion.
If no issues found, return [].
"""


async def run(state: ReviewState) -> dict:
    from src.agents.analysis import analyze
    return await analyze(state, 'code_analyst', SYSTEM_PROMPT, _build_context(state), 'code_findings')


def _build_context(state: ReviewState) -> str:
    diff = (state.analysis_diff or state.pr_diff)
    files = "\n\n".join(
        f"=== {f['path']} (first source line: {f.get('start_line',1)}) ===\n{f['content']}"
        for f in state.changed_files
    )
    prior = ""
    if state.prior_findings:
        prior = "\n\nPRIOR REVIEW FINDINGS (check if still present):\n" + "\n".join(
            f"- [{f.severity.upper()}] {f.message} (file: {f.file})" for f in state.prior_findings[:20]
        )
    if state.repo_config.mode=='snapshot': return f"SNAPSHOT SOURCE:\n{files}{prior}"
    return f"PR DIFF:\n{diff}\n\nFILE CONTENTS:\n{files}{prior}"


def _parse_findings(raw: str) -> list[Finding]:
    from src.agents.analysis import parse_findings
    return parse_findings(raw, 'code_analyst')
