
from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class GitHubAppInstallStart(BaseModel):
    repo_id: UUID | None = None


class GitHubAppInstallStartResponse(BaseModel):
    install_url: str
    existing_installation_id: int | None = None
    existing_installation_manage_url: str | None = None


class GitHubAppInstallComplete(BaseModel):
    installation_id: int
    state: str
    owner: str
    name: str


class GitHubAppAccessibleRepo(BaseModel):
    id: int
    owner: str
    name: str
    full_name: str


class GitHubAppAccessibleReposResponse(BaseModel):
    installation_id: int
    repositories: list[GitHubAppAccessibleRepo]


class GitHubAppInstallSync(BaseModel):
    installation_id: int
    state: str | None = None
    connection_id: UUID | None = None


class GitHubAppInstallSyncResponse(BaseModel):
    installation_id: int
    repositories: list["RepoRead"]
    imported_count: int


class RepoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner: str
    name: str
    github_installation_id: int | None = None
    details: dict | None = None
    created_at: datetime


class ArchRuleCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000, pattern=r'\S')


class ArchRuleUpdate(BaseModel):
    status: Literal["suggested", "approved", "rejected"] | None = None
    content: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode='after')
    def has_change(self):
        if self.status is None and self.content is None: raise ValueError('Provide a status or rule content')
        if self.content is not None and not self.content.strip(): raise ValueError('Rule content cannot be blank')
        return self


class ArchRuleSuggestionRequest(BaseModel):
    refresh: bool = False


class ArchRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content: str
    status: str
    source: str
    created_at: datetime
