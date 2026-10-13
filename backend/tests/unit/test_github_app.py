from types import SimpleNamespace

import pytest

from src.api.routes.github_app import router as github_app_router
from src.core import github_app


def _repository(repo_id: int, owner: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=repo_id,
        name=name,
        owner=SimpleNamespace(login=owner),
    )


def _installation(account: str, repository_selection: str) -> SimpleNamespace:
    return SimpleNamespace(
        account=SimpleNamespace(login=account),
        repository_selection=repository_selection,
    )


class _FakeAppClient:
    def __init__(
        self,
        installation: SimpleNamespace | None = None,
        permissions: dict[str, str] | None = None,
    ):
        self.rest = SimpleNamespace(
            apps=SimpleNamespace(
                async_get_installation=self.async_get_installation,
                async_get_authenticated=self.async_get_authenticated,
            )
        )
        self._installation = installation
        self._permissions = permissions or {}

    async def async_get_installation(self, installation_id: int) -> SimpleNamespace:
        return SimpleNamespace(parsed_data=self._installation)

    async def async_get_authenticated(self) -> SimpleNamespace:
        return SimpleNamespace(
            parsed_data=SimpleNamespace(
                permissions=SimpleNamespace(
                    model_dump=lambda exclude_unset=True: self._permissions
                )
            )
        )


class _FakeInstallationClient:
    def __init__(self, repositories: list[SimpleNamespace]):
        self.rest = SimpleNamespace(
            apps=SimpleNamespace(
                async_list_repos_accessible_to_installation=(
                    self.async_list_repos_accessible_to_installation
                ),
            )
        )
        self._repositories = repositories

    async def async_list_repos_accessible_to_installation(self, per_page: int) -> SimpleNamespace:
        return SimpleNamespace(
            parsed_data=SimpleNamespace(repositories=self._repositories)
        )


@pytest.mark.asyncio
async def test_validate_installation_access_returns_matching_repo_id(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        github_app,
        "_get_app_client",
        lambda: _FakeAppClient(_installation("EmmanuelMagala", "selected")),
    )
    monkeypatch.setattr(
        github_app,
        "_get_installation_client",
        lambda installation_id: _FakeInstallationClient(
            [
                _repository(42, "EmmanuelMagala", "live-debate-arena"),
                _repository(77, "SomeoneElse", "other-repo"),
            ]
        ),
    )

    repo_id = await github_app.validate_installation_access(
        installation_id=136745448,
        owner="emmanuelmagala",
        repo="LIVE-DEBATE-ARENA",
    )

    assert repo_id == 42


@pytest.mark.asyncio
async def test_list_installation_repositories_returns_normalized_repo_entries(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        github_app,
        "_get_installation_client",
        lambda installation_id: _FakeInstallationClient(
            [
                _repository(42, "EmmanuelMagala", "live-debate-arena"),
            ]
        ),
    )

    repositories = await github_app.list_installation_repositories(136745448)

    assert repositories == [
        {
            "id": 42,
            "owner": "EmmanuelMagala",
            "name": "live-debate-arena",
            "full_name": "EmmanuelMagala/live-debate-arena",
        }
    ]


@pytest.mark.asyncio
async def test_validate_installation_access_requires_selected_repo_access(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        github_app,
        "_get_app_client",
        lambda: _FakeAppClient(_installation("EmmanuelMagala", "selected")),
    )
    monkeypatch.setattr(
        github_app,
        "_get_installation_client",
        lambda installation_id: _FakeInstallationClient([]),
    )

    with pytest.raises(ValueError) as exc_info:
        await github_app.validate_installation_access(
            installation_id=136745448,
            owner="EmmanuelMagala",
            repo="live-debate-arena",
        )

    assert "does not have access" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verify_app_configured_requires_permissions(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(github_app, "_load_private_key", lambda: "private-key")
    monkeypatch.setattr(
        github_app,
        "_get_app_client",
        lambda: _FakeAppClient(permissions={}),
    )
    monkeypatch.setattr(github_app.settings, "github_app_id", "123")
    monkeypatch.setattr(github_app.settings, "github_app_slug", "devreason")

    assert await github_app.verify_app_configured() is False


@pytest.mark.asyncio
async def test_verify_app_configured_accepts_present_permissions(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(github_app, "_load_private_key", lambda: "private-key")
    monkeypatch.setattr(
        github_app,
        "_get_app_client",
        lambda: _FakeAppClient(permissions={"pull_requests": "write", "contents": "read"}),
    )
    monkeypatch.setattr(github_app.settings, "github_app_id", "123")
    monkeypatch.setattr(github_app.settings, "github_app_slug", "devreason")

    assert await github_app.verify_app_configured() is True


def test_github_install_router_keeps_legacy_callback_alias():
    paths = {route.path for route in github_app_router.routes}

    assert "/github/setup" in paths
    assert "/github/callback" in paths