
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class Finding(BaseModel):
    """Single issue found by any agent."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    agent: Literal[
        "code_analyst",
        "security_agent",
        "semantic_security_agent",
        "architecture_agent",
    ]
    severity: Literal["critical", "high", "medium", "low"]
    type: str
    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    message: str
    suggestion: str | None = None
    cwe_id: str | None = None
    cvss_score: float | None = None


class FindingRead(Finding):
    """Old reports used zero for an unknown line. Keep those reports readable."""
    @field_validator('line', mode='before')
    @classmethod
    def historical_line(cls,value):
        return None if isinstance(value,int) and value<1 else value


class ReviewCreate(BaseModel):
    """What the frontend sends when submitting a PR for review."""
    pr_url: str | None = None
    repo_id: UUID
    post_to_github: bool = False
    mode: Literal['pr','snapshot'] = 'pr'
    pr_number: int | None = Field(default=None, gt=0)
    branch: str | None = Field(default=None, max_length=255)
    commit_sha: str | None = Field(default=None, pattern=r'^[0-9a-f]{40}$')
    scope: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def valid_target(self):
        if self.mode == 'pr' and not (self.pr_url or self.pr_number): raise ValueError('Choose a pull request or enter its URL')
        if self.mode == 'snapshot' and (not self.branch or self.post_to_github): raise ValueError('Choose a branch; snapshot reviews cannot be posted to a PR')
        if self.mode=='snapshot' and (self.pr_url or self.pr_number): raise ValueError('Snapshot reviews cannot include a pull request')
        if self.mode=='pr' and (self.branch or self.commit_sha): raise ValueError('Pull request commits are resolved automatically')
        return self


class ReviewRead(BaseModel):
    """What the backend returns — a complete review record."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pr_url: str | None
    pr_number: int | None
    repo_id: UUID | None = None
    mode: str = 'pr'
    branch: str | None = None
    commit_sha: str | None = None
    title: str | None = None
    scope: dict | None = None
    coverage: dict | None = None
    check_outcomes: dict | None = None
    recommendation: str | None = None
    posting_status: str = 'not_requested'
    status: Literal["pending", "running", "completed", "partial", "failed", "cancelled"]
    created_at: datetime
    completed_at: datetime | None = None
    findings: list[FindingRead] = Field(default_factory=list)
    report_markdown: str | None = None
    github_comment_url: str | None = None
    error_message: str | None = None


class ReviewSummary(BaseModel):
    """History rows exclude reports, source coverage and finding text."""
    id: UUID
    repo_id: UUID
    pr_url: str | None
    pr_number: int | None
    mode: str
    branch: str | None
    commit_sha: str | None
    title: str | None
    status: str
    created_at: datetime
    completed_at: datetime | None
    recommendation: str | None
    posting_status: str
    finding_count: int
