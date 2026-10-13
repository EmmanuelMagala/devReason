
import structlog
from src.agents.state import ReviewState, Finding

log = structlog.get_logger()

MAX_PRIOR_FINDINGS = 12


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _finding_key(finding: Finding) -> tuple[str, str, str]:
    return (
        _normalize_text(finding.file),
        _normalize_text(finding.type),
        _normalize_text(finding.message),
    )


def _dedupe_prior_findings(findings: list[Finding], limit: int = MAX_PRIOR_FINDINGS) -> list[Finding]:
    unique_findings: list[Finding] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for finding in findings:
        key = _finding_key(finding)
        if key in seen_keys:
            continue

        seen_keys.add(key)
        unique_findings.append(finding)
        if len(unique_findings) >= limit:
            break

    return unique_findings


async def run(state: ReviewState, store) -> dict:
    """
    Queries LangGraph Store for all previous reviews of this exact PR.
    Namespace: ("repos", repo_id, "prs", str(pr_number))
    Returns empty list if this PR has never been reviewed before.
    Returns prior findings if it has — agents will use these for comparison.
    """
    if state.pr_number == 0 and state.repo_config.mode!='snapshot':
        return {"prior_findings": []}

    namespace = ("repos", state.repo_config.repo_id, "prs" if state.repo_config.mode=='pr' else 'branches', str(state.pr_number) if state.repo_config.mode=='pr' else state.repo_config.branch or 'snapshot')

    try:
        past_reviews = await store.asearch(namespace, limit=3)
        raw_prior_findings = []
        for review in past_reviews:
            raw_findings = review.value.get("merged_findings", [])
            for f in raw_findings:
                try:
                    raw_prior_findings.append(Finding(**f))
                except Exception:
                    pass

        prior_findings = _dedupe_prior_findings(raw_prior_findings)

        log.info(
            "load_pr_history complete",
            pr_number=state.pr_number,
            raw_prior_count=len(raw_prior_findings),
            prior_count=len(prior_findings),
        )
        return {"prior_findings": prior_findings}

    except Exception as e:
        log.error("load_pr_history failed", error=str(e))
        return {"prior_findings": []}
