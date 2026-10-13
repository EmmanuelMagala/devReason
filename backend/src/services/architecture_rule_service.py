from __future__ import annotations

import asyncio
import base64
import json
from pathlib import PurePosixPath

import httpx
import structlog
from cryptography.fernet import Fernet
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

from src.core.github_app import mint_installation_token
from src.core.llm import get_model
from src.core.settings import settings
from src.db.models import Repo, ArchRule
from src.db.repositories.repo_repo import delete_arch_rules_by_status, get_arch_rules
from src.services.memory_service import embed_and_store_rule

log = structlog.get_logger()

GITHUB_API_URL = "https://api.github.com"
MAX_REPO_SCAN_FILES = 12
MAX_FILE_CHARS = 5000

SOURCE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".cs", ".swift", ".scala", ".sql",
}

INTERESTING_MARKERS = (
    "/src/",
    "/app/",
    "/api/",
    "/routes/",
    "/controllers/",
    "/services/",
    "/models/",
    "/db/",
    "/socket",
    "/middleware",
    "/auth",
    "/hooks/",
    "/stores/",
)

HIGH_SIGNAL_MARKERS = (
    "/controller",
    "/controllers/",
    "/route",
    "/routes/",
    "/service",
    "/services/",
    "/model",
    "/models/",
)

EXCLUDED_MARKERS = (
    "/node_modules/",
    "/dist/",
    "/build/",
    "/coverage/",
    "/.next/",
    "/vendor/",
    "/tests/",
    "/test/",
    "/__tests__/",
)

SYSTEM_PROMPT = """You are a software architect deriving candidate architecture rules from an existing repository.
You will be given repository structure facts and representative code snippets.

Produce 4 to 8 candidate architecture rules that describe important boundaries, invariants, or conventions worth preserving.
The rules must be:
- specific and enforceable
- grounded in the observed code structure
- written as concise natural-language policy statements
- useful for future PR review

Avoid generic advice like 'write clean code' or 'use best practices'.
Avoid duplicating the same rule with different wording.

Return ONLY a JSON array of strings.
"""


async def suggest_architecture_rules(
    db: AsyncSession,
    repo: Repo,
    *,
    refresh: bool = False,
) -> list[ArchRule]:
    token = await _get_repo_access_token(repo)
    snapshot = await _fetch_repo_snapshot(repo.owner, repo.name, token)
    suggestions = await _generate_rule_suggestions(repo.owner, repo.name, snapshot)

    if refresh:
        await db.execute(delete(ArchRule).where(ArchRule.repo_id==repo.id,ArchRule.status=='suggested'))

    existing_rules = await get_arch_rules(db, repo.id)
    existing_contents = {rule.content.strip().lower() for rule in existing_rules}

    created_rules: list[ArchRule] = []
    for suggestion in suggestions:
        normalized = suggestion.strip()
        if not normalized or normalized.lower() in existing_contents:
            continue
        created_rule = await embed_and_store_rule(
            db,
            str(repo.id),
            normalized,
            status="suggested",
            source="suggested",
            commit=False,
        )
        created_rules.append(created_rule)
        existing_contents.add(normalized.lower())

    await db.commit()
    return created_rules


def select_representative_paths(paths: list[str], limit: int = MAX_REPO_SCAN_FILES) -> list[str]:
    ranked = sorted(paths, key=_score_repo_path, reverse=True)
    return ranked[:limit]


def parse_rule_suggestions(raw: str) -> list[str]:
    data = json.loads(raw.strip())
    if not isinstance(data, list):
        raise ValueError('Architecture suggestions must be an array')
    return [item.strip() for item in data if isinstance(item, str) and item.strip()]


async def _generate_rule_suggestions(owner: str, repo: str, snapshot: dict) -> list[str]:
    model = get_model(temperature=0.1)
    response = await asyncio.wait_for(
        model.ainvoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_build_repo_scan_context(owner, repo, snapshot)),
        ]),
        timeout=90.0,
    )
    try:
        return parse_rule_suggestions(response.content)
    except Exception as exc:
        log.error("architecture_rule_suggestion_parse_failed", error=str(exc))
        raise RuntimeError('Architecture suggestions could not be parsed. Please retry.') from None


def _build_repo_scan_context(owner: str, repo: str, snapshot: dict) -> str:
    root_dirs = "\n".join(f"- {item}" for item in snapshot["root_dirs"][:20])
    sample_files = []
    for file_entry in snapshot["files"]:
        sample_files.append(
            f"=== {file_entry['path']} ===\n{file_entry['content'][:MAX_FILE_CHARS]}"
        )
    joined_files = "\n\n".join(sample_files)
    return (
        f"REPOSITORY: {owner}/{repo}\n\n"
        f"ROOT DIRECTORIES:\n{root_dirs}\n\n"
        f"REPRESENTATIVE FILES:\n{joined_files}"
    )


async def _fetch_repo_snapshot(owner: str, repo: str, token: str) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(base_url=GITHUB_API_URL, headers=headers, timeout=30.0) as client:
        repo_response = await client.get(f"/repos/{owner}/{repo}")
        repo_response.raise_for_status()
        default_branch = repo_response.json()["default_branch"]

        tree_response = await client.get(
            f"/repos/{owner}/{repo}/git/trees/{default_branch}",
            params={"recursive": 1},
        )
        tree_response.raise_for_status()
        tree = tree_response.json().get("tree", [])

        blob_paths = [entry["path"] for entry in tree if entry.get("type") == "blob"]
        selected_paths = select_representative_paths(blob_paths)
        file_payloads = await asyncio.gather(
            *[_fetch_file_content(client, owner, repo, default_branch, path) for path in selected_paths],
            return_exceptions=True,
        )

    files = []
    for path, payload in zip(selected_paths, file_payloads):
        if isinstance(payload, Exception):
            log.warning("architecture_rule_scan_file_skipped", path=path, error=str(payload))
            continue
        if payload:
            files.append({"path": path, "content": payload})

    root_dirs = sorted({PurePosixPath(path).parts[0] for path in blob_paths if PurePosixPath(path).parts})
    return {
        "root_dirs": root_dirs,
        "files": files,
    }


async def _fetch_file_content(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    ref: str,
    path: str,
) -> str | None:
    response = await client.get(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": ref})
    response.raise_for_status()
    payload = response.json()
    if payload.get("type") != "file":
        return None
    if payload.get("encoding") == "base64":
        decoded = base64.b64decode(payload.get("content", "")).decode("utf-8", errors="ignore")
        return decoded[:MAX_FILE_CHARS]
    return str(payload.get("content", ""))[:MAX_FILE_CHARS]


def _score_repo_path(path: str) -> tuple[int, int, str]:
    pure_path = PurePosixPath(path)
    normalized_path = path.lower()
    file_name = pure_path.name
    normalized_file_name = file_name.lower()
    extension = pure_path.suffix.lower()

    score = 0
    if extension in SOURCE_EXTENSIONS:
        score += 100
    if any(marker in normalized_path for marker in INTERESTING_MARKERS):
        score += 40
    if any(marker in normalized_path for marker in HIGH_SIGNAL_MARKERS):
        score += 30
    if any(token in normalized_file_name for token in ("controller", "service", "route", "model")):
        score += 30
    if file_name in {"package.json", "pyproject.toml", "go.mod", "Cargo.toml"}:
        score += 25
    if any(marker in normalized_path for marker in EXCLUDED_MARKERS):
        score -= 80
    if ".test." in normalized_file_name or ".spec." in normalized_file_name or normalized_file_name.startswith("test_"):
        score -= 120
    if file_name in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}:
        score -= 120
    return (score, -len(path), path)


async def _get_repo_access_token(repo: Repo) -> str:
    if repo.github_installation_id:
        return await mint_installation_token(repo.github_installation_id)
    if repo.github_token_enc:
        return _decrypt_token(repo.github_token_enc)
    raise ValueError("Repository is not connected to GitHub. Reconnect it before scanning architecture.")


def _decrypt_token(encrypted: str) -> str:
    key = base64.urlsafe_b64encode(bytes.fromhex(settings.encryption_key))
    fernet = Fernet(key)
    return fernet.decrypt(encrypted.encode()).decode()
