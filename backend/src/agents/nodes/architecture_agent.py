
import json
import asyncio
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.state import ReviewState, Finding
from src.core.llm import get_model

log = structlog.get_logger()

SYSTEM_PROMPT = """You are a software architect reviewing a code change for architecture compliance.

You will be given:
1. A list of architecture rules that apply to this repository
2. The PR diff to analyse

For each rule violation you find, return a JSON object with:
severity (critical/high/medium/low), type (always "arch_violation"), file (or null), line (integer or null), message (what rule is violated and how), suggestion (how to fix it).

Return ONLY a JSON array. No markdown. No explanation. If no violations, return [].
"""


async def run(state: ReviewState) -> dict:
    try:
        # Get arch rules from DB via vector search
        # We import here to avoid circular imports at module level
        from src.db.base import AsyncSessionLocal
        from src.tools.vector_search import search_arch_rules

        analysis_diff = state.analysis_diff or state.pr_diff
        query = f"PR diff for {state.repo_config.owner}/{state.repo_config.name}: {analysis_diff[:500]}"

        try:
            rules=state.repo_config.architecture_rules
            if rules is None:
                async with AsyncSessionLocal() as db:
                    rules = await search_arch_rules(db, state.repo_config.repo_id, query, limit=10000)
        except Exception as e:
            log.error("architecture_agent rule lookup failed", error=str(e))
            return {
                "arch_findings": [],
                "completed_agents": ["architecture_agent"],
                "agent_status": {
                    "architecture_agent": {
                        "status": "rule_lookup_failed",
                        "error": str(e),
                    }
                },
            }

        if not rules:
            log.info("architecture_agent: no rules found for repo, skipping")
            return {
                "arch_findings": [],
                "completed_agents": ["architecture_agent"],
                "agent_status": {
                    "architecture_agent": {
                        "status": "no_rules",
                        "rule_count": 0,
                    }
                },
            }

        rules_text = "\n".join(f"- {r}" for r in rules)

        from src.agents.analysis import analyze
        return await analyze(state,'architecture_agent',SYSTEM_PROMPT+'\nAPPROVED ARCHITECTURE RULES:\n'+rules_text,analysis_diff, 'arch_findings')

    except asyncio.TimeoutError:
        log.warning("architecture_agent timed out")
        return {
            "arch_findings": [],
            "completed_agents": ["architecture_agent"],
            "agent_status": {
                "architecture_agent": {
                    "status": "timeout",
                }
            },
        }
    except Exception as e:
        log.error("architecture_agent failed", error=str(e))
        return {
            "arch_findings": [],
            "completed_agents": ["architecture_agent"],
            "agent_status": {
                "architecture_agent": {
                    "status": "failed",
                    "error": str(e),
                }
            },
        }


def _parse_findings(raw: str) -> list[Finding]:
    from src.agents.analysis import parse_findings
    return parse_findings(raw, 'architecture_agent')
