from src.agents.nodes.report_writer import (
    _build_findings_context,
    _build_prior_context,
    _build_system_prompt,
)
from src.agents.state import Finding


def test_build_system_prompt_prefers_concise_output():
    prompt = _build_system_prompt(has_prior=True)

    assert "concise markdown code review report" in prompt
    assert "Keep the report under 400 words" in prompt
    assert "Use the prior issue list only for change detection" in prompt


def test_build_findings_context_caps_medium_and_low_findings():
    findings = [
        Finding(
            agent="code_analyst",
            severity="medium",
            type=f"type-{index}",
            file="backend/src/socket/index.ts",
            message=f"Medium issue {index}",
        )
        for index in range(5)
    ]

    context = _build_findings_context(findings)

    assert "MEDIUM (5):" in context
    assert "3 additional medium finding(s) omitted for brevity." not in context
    assert "2 additional medium finding(s) omitted for brevity." in context
    assert "Medium issue 0" in context
    assert "Medium issue 4" not in context


def test_build_prior_context_caps_history_payload():
    findings = [
        Finding(
            agent="code_analyst",
            severity="high",
            type="authorization",
            file="backend/src/socket/index.ts",
            message=f"Issue {index}",
        )
        for index in range(8)
    ]

    context = _build_prior_context(findings)

    assert "Previous review issue keys:" in context
    assert "Issue 0" in context
    assert "Issue 5" in context
    assert "Issue 6" not in context
    assert "2 additional prior issue(s) omitted for brevity." in context
