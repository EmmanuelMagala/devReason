import uuid

import pytest

from src.db.models import Repo
from src.db.repositories.repo_repo import get_repos_for_user, upsert_installation_repositories


class _FakeScalarResult:
    def __init__(self, repos: list[Repo]):
        self._repos = repos

    def all(self) -> list[Repo]:
        return list(self._repos)


class _FakeExecuteResult:
    def __init__(self, repos: list[Repo]):
        self._repos = repos

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._repos)


class _FakeAsyncSession:
    def __init__(self, repos: list[Repo]):
        self.repos = repos

    async def execute(self, statement):
        params = statement.compile().params
        clerk_user_id = next(
            (value for key, value in params.items() if "clerk_user_id" in key),
            None,
        )
        repos = [
            repo
            for repo in self.repos
            if clerk_user_id is None or repo.clerk_user_id == clerk_user_id
        ]

        if "github_installation_id IS NOT NULL OR repos.github_token_enc IS NOT NULL" in str(statement):
            repos = [
                repo
                for repo in repos
                if repo.github_installation_id is not None or repo.github_token_enc is not None
            ]

        return _FakeExecuteResult(repos)

    def add(self, repo: Repo):
        self.repos.append(repo)

    async def commit(self):
        return None

    async def refresh(self, repo: Repo):
        return None


@pytest.mark.asyncio
async def test_sync_disconnects_removed_installation_repositories():
    removed_repo = Repo(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        owner="EmmanuelMagala",
        name="live-debate-arena",
        github_installation_id=136748295,
        github_repo_id=1,
        github_token_enc=None,
    )
    kept_repo = Repo(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        owner="EmmanuelMagala",
        name="music-player",
        github_installation_id=136748295,
        github_repo_id=2,
        github_token_enc=None,
    )
    legacy_repo = Repo(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        owner="EmmanuelMagala",
        name="legacy-pat-repo",
        github_installation_id=None,
        github_repo_id=None,
        github_token_enc="encrypted-token",
    )
    db = _FakeAsyncSession([removed_repo, kept_repo, legacy_repo])

    synced_repos, imported_count = await upsert_installation_repositories(
        db=db,
        clerk_user_id="user_123",
        installation_id=136748295,
        repositories=[
            {
                "id": 2,
                "owner": "EmmanuelMagala",
                "name": "music-player",
            },
            {
                "id": 3,
                "owner": "EmmanuelMagala",
                "name": "notes-app",
            },
        ],
    )

    connected_repos = await get_repos_for_user(db, "user_123")

    assert imported_count == 1
    assert {(repo.owner, repo.name) for repo in synced_repos} == {
        ("EmmanuelMagala", "music-player"),
        ("EmmanuelMagala", "notes-app"),
    }
    assert removed_repo.github_installation_id is None
    assert removed_repo.github_repo_id is None
    assert {(repo.owner, repo.name) for repo in connected_repos} == {
        ("EmmanuelMagala", "music-player"),
        ("EmmanuelMagala", "notes-app"),
        ("EmmanuelMagala", "legacy-pat-repo"),
    }