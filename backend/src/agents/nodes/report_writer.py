
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.state import Finding, ReviewState
from src.core.llm import get_model

log = structlog.get_logger()

SEVERITY_ORDER = ("critical", "high", "medium", "low")
PROMPT_LIMITS = {
    "critical": 4,
    "high": 4,
    "medium": 3,
    "low": 2,
}
MAX_PRIOR_CONTEXT_FINDINGS = 6


def _build_system_prompt(has_prior: bool) -> str:
    base = """You are a senior engineering lead writing a concise markdown code review report.
Keep the report compact and decision-oriented.

Required structure:
1. Executive summary (2-3 sentences)
2. Key findings by severity (Critical -> High -> Medium -> Low)
3. Overall recommendation (approve / request changes / block)

Writing rules:
- Collapse duplicate or overlapping findings across agents into one report item.
- For critical and high findings, give a short issue / impact / fix explanation.
- For medium and low findings, use brief bullets and avoid repetitive boilerplate.
- Prefer brevity over exhaustiveness and avoid repeating the same file path or message.
- Keep the report under 400 words unless there are many critical or high findings.
"""
    if has_prior:
        base += """
4. Comparison with previous review:
   - Issues FIXED since last review
   - Issues STILL PRESENT
   - NEW issues not in previous review

Use the prior issue list only for change detection. Do not restate duplicate history verbatim.
"""
    return base


def _format_location(finding: Finding) -> str:
    if finding.file and finding.line:
        return f"{finding.file}:{finding.line}"
    if finding.file:
        return finding.file
    return "unknown location"


def _build_findings_context(findings: list[Finding]) -> str:
    if not findings:
        return "No issues found in this review."

    lines = ["Current findings summary:"]
    for severity in SEVERITY_ORDER:
        severity_findings = [finding for finding in findings if finding.severity == severity]
        if not severity_findings:
            continue

        lines.append(f"{severity.upper()} ({len(severity_findings)}):")
        limit = PROMPT_LIMITS[severity]
        for finding in severity_findings[:limit]:
            lines.append(
                f"- {finding.type}: {finding.message} [{_format_location(finding)}]"
            )
            if finding.suggestion and severity in {"critical", "high"}:
                lines.append(f"  Fix: {finding.suggestion}")

        remaining = len(severity_findings) - limit
        if remaining > 0:
            lines.append(f"- {remaining} additional {severity} finding(s) omitted for brevity.")

    return "\n".join(lines)


def _build_prior_context(findings: list[Finding]) -> str:
    if not findings:
        return ""

    lines = ["Previous review issue keys:"]
    for finding in findings[:MAX_PRIOR_CONTEXT_FINDINGS]:
        lines.append(
            f"- [{finding.severity.upper()}] {finding.type}: {finding.message}"
        )

    remaining = len(findings) - MAX_PRIOR_CONTEXT_FINDINGS
    if remaining > 0:
        lines.append(f"- {remaining} additional prior issue(s) omitted for brevity.")

    return "\n".join(lines)


async def run(state: ReviewState) -> dict:
    if state.error:
        return {'final_report':state.error,'agent_status':{'report_writer':{'status':'skipped'}}}
    try:
        model = get_model(temperature=0.3)
        findings_text = _build_findings_context(state.merged_findings)
        prior_text = _build_prior_context(state.prior_findings)
        context = findings_text if not prior_text else f"{findings_text}\n\n{prior_text}"
        context += '\nAnalysis check outcomes: '+str(state.agent_status)+'\nCoverage: '+str(state.coverage)+'\nDo not recommend approval when required checks failed or analysis is incomplete.'

        response = await model.ainvoke([
            SystemMessage(content=_build_system_prompt(bool(state.prior_findings))),
            HumanMessage(content=context),
        ])

        log.info("report_writer complete", length=len(response.content))
        return {"final_report": response.content, "agent_status": {"report_writer": {"status": "completed"}}}

    except Exception as e:
        log.error("report_writer failed", error=str(e))
        return {"final_report": "The report could not be generated. Findings may still be available.", "agent_status": {"report_writer": {"status": "failed", "error": "Report generation failed"}}}
