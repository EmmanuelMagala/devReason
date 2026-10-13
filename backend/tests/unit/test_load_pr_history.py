import pytest

from src.agents.nodes.load_pr_history import _dedupe_prior_findings, run
from src.agents.state import Finding, RepoConfig, ReviewState


class DummyStore:
    def __init__(self, reviews):
        self._reviews = reviews

    async def asearch(self, namespace, limit=3):
        return self._reviews


class DummyReview:
    def __init__(self, findings):
        self.value = {"merged_findings": findings}


def _state(pr_number=7):
    return ReviewState(
        pr_url="https://github.com/octo/repo/pull/7",
        pr_number=pr_number,
        repo_config=RepoConfig(
            repo_id="11111111-1111-1111-1111-111111111111",
            review_id="22222222-2222-2222-2222-222222222222",
            owner="octo",
            name="repo",
            github_token="secret-token",
            post_to_github=False,
        ),
    )


def test_dedupe_prior_findings_removes_repeated_issues():
    findings = [
        Finding(
            agent="code_analyst",
            severity="high",
            type="authorization",
            file="backend/src/socket/index.ts",
            message="Authorization checks are missing.",
        ),
        Finding(
            agent="semantic_security_agent",
            severity="high",
            type="authorization",
            file="backend/src/socket/index.ts",
            message="Authorization checks are missing.",
        ),
        Finding(
            agent="code_analyst",
            severity="medium",
            type="validation",
            file="backend/src/socket/index.ts",
            message="Input validation is weak.",
        ),
    ]

    unique_findings = _dedupe_prior_findings(findings)

    assert len(unique_findings) == 2
    assert unique_findings[0].message == "Authorization checks are missing."
    assert unique_findings[1].message == "Input validation is weak."


@pytest.mark.asyncio
async def test_load_pr_history_dedupes_findings_across_recent_reviews():
    store = DummyStore(
        [
            DummyReview(
                [
                    {
                        "agent": "code_analyst",
                        "severity": "high",
                        "type": "authorization",
                        "file": "backend/src/socket/index.ts",
                        "message": "Authorization checks are missing.",
                    },
                    {
                        "agent": "semantic_security_agent",
                        "severity": "high",
                        "type": "authorization",
                        "file": "backend/src/socket/index.ts",
                        "message": "Authorization checks are missing.",
                    },
                ]
            ),
            DummyReview(
                [
                    {
                        "agent": "code_analyst",
                        "severity": "medium",
                        "type": "validation",
                        "file": "backend/src/socket/index.ts",
                        "message": "Input validation is weak.",
                    }
                ]
            ),
        ]
    )

    result = await run(_state(), store=store)

    assert len(result["prior_findings"]) == 2
    assert [finding.message for finding in result["prior_findings"]] == [
        "Authorization checks are missing.",
        "Input validation is weak.",
    ]


@pytest.mark.asyncio
async def test_load_pr_history_skips_lookup_for_unknown_pr_number():
    result = await run(_state(pr_number=0), store=DummyStore([]))

    assert result == {"prior_findings": []}
