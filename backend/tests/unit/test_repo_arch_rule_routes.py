from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.deps import get_current_user, get_db
from src.api.routes import repos as repos_route


def _build_repo(repo_id, clerk_user_id: str = "user_123") -> SimpleNamespace:
    return SimpleNamespace(
        id=repo_id,
        clerk_user_id=clerk_user_id,
        owner="acme",
        name="widget-service",
        github_installation_id=123,
        github_token_enc=None,
    )


def _build_rule(rule_id, repo_id, *, status: str = "suggested", source: str = "suggested") -> SimpleNamespace:
    return SimpleNamespace(
        id=rule_id,
        repo_id=repo_id,
        content="Route handlers must delegate persistence to service functions.",
        status=status,
        source=source,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def repo_test_app(monkeypatch) -> FastAPI:
    async def authorized(*args): return 'fixture-token'
    from src.services import github_connection_service
    monkeypatch.setattr(github_connection_service,'authorize_repo',authorized)
    app = FastAPI()
    app.include_router(repos_route.router, prefix="/api/repos")

    async def override_get_current_user() -> dict[str, str]:
        return {"clerk_user_id": "user_123"}

    async def override_get_db():
        yield SimpleNamespace()

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.mark.asyncio
async def test_suggest_repo_arch_rules_returns_suggested_rules(
    repo_test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_id = uuid4()
    suggested_rule = _build_rule(uuid4(), repo_id)

    async def fake_get_repo_by_id(db, lookup_repo_id):
        assert lookup_repo_id == repo_id
        return _build_repo(repo_id)

    async def fake_suggest_architecture_rules(db, repo, refresh: bool):
        assert repo.id == repo_id
        assert refresh is True
        return [suggested_rule]

    monkeypatch.setattr(repos_route, "get_repo_by_id", fake_get_repo_by_id)
    monkeypatch.setattr(repos_route, "suggest_architecture_rules", fake_suggest_architecture_rules)

    transport = ASGITransport(app=repo_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(f"/api/repos/{repo_id}/rules/suggest", json={"refresh": True})

    assert response.status_code == 201
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == str(suggested_rule.id)
    assert payload[0]["content"] == suggested_rule.content
    assert payload[0]["status"] == "suggested"
    assert payload[0]["source"] == "suggested"
    assert payload[0]["created_at"]


@pytest.mark.asyncio
async def test_list_arch_rules_passes_optional_status_filter(
    repo_test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_id = uuid4()
    approved_rule = _build_rule(uuid4(), repo_id, status="approved", source="manual")
    captured: dict[str, object] = {}

    async def fake_get_repo_by_id(db, lookup_repo_id):
        return _build_repo(lookup_repo_id)

    async def fake_get_arch_rules(db, lookup_repo_id, *, status=None):
        captured["repo_id"] = lookup_repo_id
        captured["status"] = status
        return [approved_rule]

    monkeypatch.setattr(repos_route, "get_repo_by_id", fake_get_repo_by_id)
    monkeypatch.setattr(repos_route, "get_arch_rules", fake_get_arch_rules)

    transport = ASGITransport(app=repo_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/repos/{repo_id}/rules", params={"status": "approved"})

    assert response.status_code == 200
    assert captured == {"repo_id": repo_id, "status": "approved"}
    assert response.json()[0]["status"] == "approved"
    assert response.json()[0]["source"] == "manual"


@pytest.mark.asyncio
async def test_update_arch_rule_changes_status_for_matching_repo(
    repo_test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_id = uuid4()
    rule_id = uuid4()
    existing_rule = _build_rule(rule_id, repo_id)
    approved_rule = _build_rule(rule_id, repo_id, status="approved")
    captured: dict[str, object] = {}

    async def fake_get_repo_by_id(db, lookup_repo_id):
        return _build_repo(lookup_repo_id)

    async def fake_get_arch_rule_by_id(db, lookup_rule_id):
        assert lookup_rule_id == rule_id
        return existing_rule

    async def fake_update_arch_rule_status(db, rule, status: str):
        captured["rule_id"] = rule.id
        captured["status"] = status
        return approved_rule

    monkeypatch.setattr(repos_route, "get_repo_by_id", fake_get_repo_by_id)
    monkeypatch.setattr(repos_route, "get_arch_rule_by_id", fake_get_arch_rule_by_id)
    monkeypatch.setattr(repos_route, "update_arch_rule_status", fake_update_arch_rule_status)

    transport = ASGITransport(app=repo_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            f"/api/repos/{repo_id}/rules/{rule_id}",
            json={"status": "approved"},
        )

    assert response.status_code == 200
    assert captured == {"rule_id": rule_id, "status": "approved"}
    assert response.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_update_arch_rule_returns_404_for_rule_in_other_repo(
    repo_test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_id = uuid4()
    other_repo_id = uuid4()
    rule_id = uuid4()

    async def fake_get_repo_by_id(db, lookup_repo_id):
        return _build_repo(lookup_repo_id)

    async def fake_get_arch_rule_by_id(db, lookup_rule_id):
        return _build_rule(lookup_rule_id, other_repo_id)

    monkeypatch.setattr(repos_route, "get_repo_by_id", fake_get_repo_by_id)
    monkeypatch.setattr(repos_route, "get_arch_rule_by_id", fake_get_arch_rule_by_id)

    transport = ASGITransport(app=repo_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            f"/api/repos/{repo_id}/rules/{rule_id}",
            json={"status": "approved"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Rule not found"}