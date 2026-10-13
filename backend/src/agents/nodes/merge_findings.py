
import structlog
from src.agents.state import ReviewState, Finding

log = structlog.get_logger()

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


async def run(state: ReviewState) -> dict:
    """
    Deterministic node — no LLM call.
    Collects all findings from all three agents,
    deduplicates, and sorts by severity.
    This node writes to Postgres (findings table) via the review service.
    """
    all_findings = (
        state.code_findings +
        state.security_findings +
        state.semantic_security_findings +
        state.arch_findings
    )

    # Deduplicate: same file + same message = same finding
    seen = set()
    unique_findings = []
    for f in all_findings:
        key = (f.file, f.message[:80])
        if key not in seen:
            seen.add(key)
            unique_findings.append(f)

    # Sort by severity
    sorted_findings = sorted(
        unique_findings,
        key=lambda f: SEVERITY_ORDER.get(f.severity, 99),
    )

    log.info(
        "merge_findings complete",
        total=len(all_findings),
        unique=len(sorted_findings),
        critical=sum(1 for f in sorted_findings if f.severity == "critical"),
        high=sum(1 for f in sorted_findings if f.severity == "high"),
    )

    return {"merged_findings": sorted_findings}