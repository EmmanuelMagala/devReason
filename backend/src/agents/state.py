
from operator import add, or_
from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, Field, ConfigDict, SecretStr
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


class Finding(BaseModel):
    """
    A single issue found by any agent.
    Identical to schemas/review.py Finding — kept separate to avoid circular imports.
    """
    agent: str
    severity: Literal["critical", "high", "medium", "low"]
    type: str
    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    message: str
    suggestion: str | None = None
    cwe_id: str | None = None
    cvss_score: float | None = None


class RepoConfig(BaseModel):
    """Configuration for the repo being reviewed — passed in at graph start."""
    repo_id: str
    review_id: str          # UUID of the reviews table row — used as Store key
    owner: str
    name: str
    github_token: SecretStr  # Masked in traces/checkpoints while still available to nodes
    post_to_github: bool = False
    lease_token: str | None = None
    architecture_rules: list[str] | None = None
    mode: str = 'pr'
    branch: str | None = None
    commit_sha: str | None = None
    scope: dict = Field(default_factory=dict)


class ReviewState(BaseModel):
    """
    The complete state shared across all 12 nodes.
    LangGraph passes this through every node and merges partial returns.

    IMPORTANT: Each node returns a dict of only the keys it changes.
    Keys not returned are left unchanged. LangGraph handles the merge.
    The add_messages annotation on 'messages' means new messages are
    appended, not replaced — all other fields replace on update.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # ── Input (set before graph starts) ──────────────────────────────
    pr_url: str
    repo_config: RepoConfig

    # ── Fetched context (fetch_pr node) ──────────────────────────────
    pr_metadata: dict = Field(default_factory=dict)
    coverage: dict = Field(default_factory=dict)
    pr_number: int = 0                              # Parsed from pr_url
    pr_diff: str = ""                               # Raw unified diff
    analysis_diff: str = ""                         # Focused diff for LLM review
    changed_files: list[dict] = Field(default_factory=list)  # [{path, content}]

    # ── LLM message history ──────────────────────────────────────────
    messages: Annotated[list[AnyMessage], add_messages] = Field(default_factory=list)

    # ── Memory injection (loaded before agents run) ───────────────────
    prior_findings: list[Finding] = Field(default_factory=list)
    # ^ From Store: previous reviews of this same PR number
    # ^ Empty list = first time this PR has been reviewed
    # ^ Non-empty = agents will compare and show what changed

    project_insights: dict = Field(default_factory=dict)
    # ^ From Store: aggregated patterns for this repo
    # ^ e.g. {"common_issue_types": {"complexity": 12}, "total_reviews": 5}
    # ^ Injected only if non-empty — first few reviews will not have this

    # ── Per-agent findings (each agent writes its own key) ────────────
    code_findings: list[Finding] = Field(default_factory=list)
    security_findings: list[Finding] = Field(default_factory=list)
    semantic_security_findings: list[Finding] = Field(default_factory=list)
    arch_findings: list[Finding] = Field(default_factory=list)
    # ^ These three run in PARALLEL — they each write a different key
    # ^ so there are no write conflicts between them

    # ── Control flow ─────────────────────────────────────────────────
    completed_agents: Annotated[list[str], add] = Field(default_factory=list)
    agent_status: Annotated[dict[str, dict], or_] = Field(default_factory=dict)
    retry_count: dict[str, int] = Field(default_factory=dict)

    # ── Final output ─────────────────────────────────────────────────
    merged_findings: list[Finding] = Field(default_factory=list)
    final_report: str | None = None
    github_comment_url: str | None = None
    error: str | None = None
