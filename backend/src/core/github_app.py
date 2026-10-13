from functools import lru_cache

import structlog
from githubkit import GitHub
from githubkit.auth import AppAuthStrategy, AppInstallationAuthStrategy

from src.core.settings import settings

log = structlog.get_logger()


@lru_cache(maxsize=1)
def _load_private_key() -> str:
    path = settings.github_app_private_key_path
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            return file_obj.read()
    except FileNotFoundError as exc:
        raise RuntimeError(f"GitHub App private key not found at {path}") from exc


@lru_cache(maxsize=1)
def _get_app_client() -> GitHub:
    return GitHub(
        AppAuthStrategy(
            app_id=settings.github_app_id,
            private_key=_load_private_key(),
        ), timeout=15, auto_retry=False,
    )


def _get_installation_client(installation_id: int) -> GitHub:
    return GitHub(
        AppInstallationAuthStrategy(
            app_id=settings.github_app_id,
            private_key=_load_private_key(),
            installation_id=installation_id,
        ), timeout=15, auto_retry=False,
    )


def get_install_url(state: str) -> str:
    if not settings.github_app_slug:
        raise RuntimeError("github_app_slug is not configured")
    return f"https://github.com/apps/{settings.github_app_slug}/installations/new?state={state}"


def get_installation_manage_url(installation_id: int) -> str:
    return f"https://github.com/settings/installations/{installation_id}"


async def verify_app_configured() -> bool:
    if not settings.github_app_id or not settings.github_app_slug:
        log.warning("github_app_not_fully_configured")
        return False

    try:
        _load_private_key()
    except RuntimeError as exc:
        log.error("github_app_private_key_missing", error=str(exc))
        return False

    try:
        app_info = await _get_app_client().rest.apps.async_get_authenticated()
    except Exception as exc:
        log.error("github_app_auth_probe_failed", error=str(exc))
        return False

    permissions = app_info.parsed_data.permissions
    configured_permissions = (
        permissions.model_dump(exclude_unset=True)
        if hasattr(permissions, "model_dump")
        else {}
    )
    if not configured_permissions:
        log.warning(
            "github_app_no_permissions_configured",
            message=(
                "GitHub App has no repository permissions configured. "
                "GitHub will not offer repository selection during installation."
            ),
        )
        return False

    return True


async def mint_installation_token(installation_id: int) -> str:
    response = await _get_app_client().rest.apps.async_create_installation_access_token(
        installation_id
    )
    return response.parsed_data.token


async def list_installation_repositories(installation_id: int) -> list[dict[str, int | str]]:
    installation_client = _get_installation_client(installation_id)
    repos_response = (
        await installation_client.rest.apps.async_list_repos_accessible_to_installation(
            per_page=100
        )
    )

    repositories: list[dict[str, int | str]] = []
    for accessible_repo in repos_response.parsed_data.repositories:
        repo_owner = getattr(accessible_repo.owner, "login", None)
        if not repo_owner:
            continue
        repositories.append(
            {
                "id": int(accessible_repo.id),
                "owner": repo_owner,
                "name": accessible_repo.name,
                "full_name": f"{repo_owner}/{accessible_repo.name}",
            }
        )

    return repositories


async def validate_installation_access(
    installation_id: int,
    owner: str,
    repo: str,
) -> int:
    app_client = _get_app_client()
    installation = await app_client.rest.apps.async_get_installation(installation_id)
    installation_account = getattr(installation.parsed_data.account, "login", None)
    if installation_account and installation_account.lower() != owner.lower():
        raise ValueError(
            f"GitHub App installation belongs to {installation_account}, not {owner}."
        )

    for accessible_repo in await list_installation_repositories(installation_id):
        if (
            str(accessible_repo["owner"]).lower() == owner.lower()
            and str(accessible_repo["name"]).lower() == repo.lower()
        ):
            return int(accessible_repo["id"])

    repository_selection = getattr(installation.parsed_data, "repository_selection", None)
    if repository_selection == "selected":
        raise ValueError(
            f"GitHub App installation does not have access to {owner}/{repo}. "
            "Update the installation and grant that repository, then try again."
        )

    raise ValueError(
        f"GitHub App installation could not find {owner}/{repo}. "
        "Reinstall the app for the correct account or repository, then try again."
    )
