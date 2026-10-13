import uuid

import structlog

from src.agents.state import ReviewState
from src.db.base import AsyncSessionLocal
from src.db.repositories.review_repo import save_findings, update_review_status
from src.schemas.review import Finding

log = structlog.get_logger()


def _to_schema_finding(finding) -> Finding:
    return Finding(
        agent=finding.agent if hasattr(finding, "agent") else finding.get("agent"),
        severity=finding.severity if hasattr(finding, "severity") else finding.get("severity"),
        type=finding.type if hasattr(finding, "type") else finding.get("type"),
        file=finding.file if hasattr(finding, "file") else finding.get("file"),
        line=finding.line if hasattr(finding, "line") else finding.get("line"),
        message=finding.message if hasattr(finding, "message") else finding.get("message"),
        suggestion=finding.suggestion if hasattr(finding, "suggestion") else finding.get("suggestion"),
        cwe_id=finding.cwe_id if hasattr(finding, "cwe_id") else finding.get("cwe_id"),
        cvss_score=(
            finding.cvss_score if hasattr(finding, "cvss_score") else finding.get("cvss_score")
        ),
    )


async def run(state: ReviewState) -> dict:
    review_id = uuid.UUID(state.repo_config.review_id)
    repo_id = uuid.UUID(state.repo_config.repo_id)
    schema_findings = [_to_schema_finding(finding) for finding in state.merged_findings]

    async with AsyncSessionLocal() as db:
        if state.repo_config.lease_token:
            from src.services.jobs import fence
            await fence(db, review_id, state.repo_config.lease_token)
        await update_review_status(
            db,
            review_id,
            "running",
            report_markdown=state.final_report,
            commit=False,
        )
        await save_findings(
            db,
            review_id,
            repo_id,
            state.pr_number,
            schema_findings,
            commit=False,
        )
        await db.commit()

    log.info("persist_review complete", review_id=state.repo_config.review_id, findings=len(schema_findings))
    return {
        "agent_status": {
            "persist_review": {
                "status": "completed",
                "finding_count": len(schema_findings),
            }
        }
    }
