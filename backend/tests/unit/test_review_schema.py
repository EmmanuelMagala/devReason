from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from src.schemas.review import ReviewRead


def test_review_read_validates_nested_orm_findings():
    finding = SimpleNamespace(
        id=uuid4(),
        agent="security_agent",
        severity="high",
        type="auth",
        file="app.py",
        line=12,
        message="Missing authorization check",
        suggestion="Add the missing guard.",
        cwe_id="CWE-285",
        cvss_score=7.5,
    )
    review = SimpleNamespace(
        id=uuid4(),
        pr_url="https://github.com/octo/repo/pull/1",
        pr_number=1,
        status="completed",
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        findings=[finding],
        report_markdown="done",
        github_comment_url=None,
        error_message=None,
    )

    validated = ReviewRead.model_validate(review)

    assert validated.findings[0].message == "Missing authorization check"
