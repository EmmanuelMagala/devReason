
from typing import Literal
from pydantic import BaseModel, Field


class StreamEvent(BaseModel):
    """
    Typed payload for every SSE event sent to the browser.
    The frontend switches on the 'event' field to update the UI.
    """
    event: Literal[
        "agent_start",      # an agent began executing
        "agent_complete",   # an agent finished, data contains finding count
        "tool_call",        # an agent called a tool
        "tool_result",      # a tool returned a result
        "findings_ready",   # merge_findings completed — send all findings to UI
        "token",            # a single LLM output token (for streaming text)
        "report_token",     # a report-writer token for live report generation state
        "report_ready",     # final markdown report is ready before full review completion
        "complete",         # entire review finished
        "error",            # something failed
    ]
    agent: str | None = None
    data: dict = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Serialise to SSE wire format."""
        return f"data: {self.model_dump_json()}\n\n"