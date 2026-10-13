
import uuid
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Repo, ArchRule


async def create_repo(
    db: AsyncSession,
    clerk_user_id: str,
    owner: str,
    name: str,
    github_token_enc: str,
) -> Repo:
    repo = Repo(
        id=uuid.uuid4(),
        clerk_user_id=clerk_user_id,
        owner=owner,
        name=name,
        github_token_enc=github_token_enc,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo


async def upsert_repo_installation(
    db: AsyncSession,
    clerk_user_id: str,
    owner: str,
    name: str,
    installation_id: int,
    github_repo_id: int,
) -> Repo:
    result = await db.execute(
        select(Repo).where(
            Repo.clerk_user_id == clerk_user_id,
            Repo.owner == owner,
            Repo.name == name,
        )
    )
    repo = result.scalar_one_or_none()

    if repo is None:
        repo = Repo(
            id=uuid.uuid4(),
            clerk_user_id=clerk_user_id,
            owner=owner,
            name=name,
            github_installation_id=installation_id,
            github_repo_id=github_repo_id,
            github_token_enc=None,
        )
        db.add(repo)
    else:
        repo.github_installation_id = installation_id
        repo.github_repo_id = github_repo_id

    await db.commit()
    await db.refresh(repo)
    return repo


async def upsert_installation_repositories(
    db: AsyncSession,
    clerk_user_id: str,
    installation_id: int,
    repositories: list[dict[str, int | str]],
    commit: bool = True,
) -> tuple[list[Repo], int]:
    result = await db.execute(
        select(Repo).where(Repo.clerk_user_id == clerk_user_id)
    )
    existing_repos = list(result.scalars().all())
    existing_by_identity = {
        (repo.owner, repo.name): repo for repo in existing_repos
    }

    synced_repos: list[Repo] = []
    imported_count = 0
    granted_repo_keys: set[tuple[str, str]] = set()

    for repository in repositories:
        owner = str(repository["owner"])
        name = str(repository["name"])
        github_repo_id = int(repository["id"])
        repo_key = (owner, name)
        granted_repo_keys.add(repo_key)

        repo = existing_by_identity.get(repo_key)

        if repo is None:
            repo = Repo(
                id=uuid.uuid4(),
                clerk_user_id=clerk_user_id,
                owner=owner,
                name=name,
                github_installation_id=installation_id,
                github_repo_id=github_repo_id,
                github_token_enc=None,
            )
            imported_count += 1
            db.add(repo)
            existing_by_identity[repo_key] = repo
        else:
            repo.github_installation_id = installation_id
            repo.github_repo_id = github_repo_id

        synced_repos.append(repo)

    for repo in existing_repos:
        if (
            repo.github_installation_id == installation_id
            and (repo.owner, repo.name) not in granted_repo_keys
        ):
            repo.github_installation_id = None
            repo.github_repo_id = None

    if commit:
        await db.commit()

    # IDs are assigned here and AsyncSessionLocal uses expire_on_commit=False.
    # Refreshing each row added one remote query per repository on every sync.
    return synced_repos, imported_count


async def get_repos_for_user(db: AsyncSession, clerk_user_id: str) -> list[Repo]:
    result = await db.execute(
        select(Repo).where(
            Repo.clerk_user_id == clerk_user_id,
            or_(
                Repo.github_installation_id.is_not(None),
                Repo.github_token_enc.is_not(None),
            ),
        )
    )
    return list(result.scalars().all())


async def get_repo_by_id(db: AsyncSession, repo_id: uuid.UUID) -> Repo | None:
    result = await db.execute(select(Repo).where(Repo.id == repo_id))
    return result.scalar_one_or_none()


async def get_repo_by_identity(
    db: AsyncSession,
    clerk_user_id: str,
    owner: str,
    name: str,
) -> Repo | None:
    result = await db.execute(
        select(Repo).where(
            Repo.clerk_user_id == clerk_user_id,
            Repo.owner == owner,
            Repo.name == name,
        )
    )
    return result.scalar_one_or_none()


async def create_arch_rule(
    db: AsyncSession,
    repo_id: uuid.UUID,
    content: str,
    *,
    status: str = "approved",
    source: str = "manual",
) -> ArchRule:
    rule = ArchRule(
        id=uuid.uuid4(),
        repo_id=repo_id,
        content=content,
        status=status,
        source=source,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def get_arch_rules(
    db: AsyncSession,
    repo_id: uuid.UUID,
    *,
    status: str | None = None,
) -> list[ArchRule]:
    query = select(ArchRule).where(ArchRule.repo_id == repo_id)
    if status:
        query = query.where(ArchRule.status == status)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_arch_rule_by_id(db: AsyncSession, rule_id: uuid.UUID) -> ArchRule | None:
    result = await db.execute(
        select(ArchRule).where(ArchRule.id == rule_id)
    )
    return result.scalar_one_or_none()


async def update_arch_rule_status(
    db: AsyncSession,
    rule: ArchRule,
    status: str,
) -> ArchRule:
    rule.status = status
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_arch_rules_by_status(
    db: AsyncSession,
    repo_id: uuid.UUID,
    status: str,
) -> None:
    await db.execute(
        delete(ArchRule).where(
            ArchRule.repo_id == repo_id,
            ArchRule.status == status,
        )
    )
    await db.commit()
