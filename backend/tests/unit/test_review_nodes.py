import json

import pytest

from src.agents.context_selection import build_analysis_diff, prioritize_changed_file_entries
from src.agents.nodes import (
    architecture_agent,
    complete_review,
    fetch_pr,
    persist_review,
    post_to_github,
    supervisor,
)
from src.agents.state import RepoConfig, ReviewState
from src.schemas.review import Finding as ReviewFinding


class FakeTool:
    def __init__(self, handler):
        self._handler = handler

    async def ainvoke(self, payload):
        return await self._handler(payload)


class DummySessionContext:
    def __init__(self, value=object()):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_state(**kwargs) -> ReviewState:
    return ReviewState(
        pr_url=kwargs.get("pr_url", "https://github.com/octo/repo/pull/7"),
        pr_diff=kwargs.get("pr_diff", "diff --git a/app.py b/app.py"),
        repo_config=RepoConfig(
            repo_id="11111111-1111-1111-1111-111111111111",
            review_id="22222222-2222-2222-2222-222222222222",
            owner="octo",
            name="repo",
            github_token="secret-token",
            post_to_github=kwargs.get("post_to_github", True),
        ),
        merged_findings=kwargs.get("merged_findings", []),
        final_report=kwargs.get("final_report", "review body"),
    )


@pytest.mark.asyncio
async def test_fetch_pr_preserves_pinned_context_and_coverage(monkeypatch):
    async def context(token,owner,name,number,sha,scope):
        assert (owner,name,number)==("octo","repo",7)
        return {"title":"Add realtime updates","head":{"sha":"abc123"}},[{"path":"app.py","content":"print('new')"}],"=== app.py ===\npatch",{"total_files":101,"reviewed_files":1,"scope_complete":False}
    monkeypatch.setattr(fetch_pr,"pr_context",context)
    result=await fetch_pr.run(_build_state(post_to_github=False))
    assert result["pr_number"]==7
    assert result["coverage"]["total_files"]==101
    assert result["changed_files"][0]["path"]=="app.py"
    assert result["agent_status"]["fetch_pr"]["status"]=="completed"


@pytest.mark.asyncio
async def test_fetch_pr_fails_when_target_changed(monkeypatch):
    async def context(*args): raise ValueError("This pull request changed after submission")
    monkeypatch.setattr(fetch_pr,"pr_context",context)
    result=await fetch_pr.run(_build_state(post_to_github=False))
    assert result["changed_files"]==[]
    assert "changed after submission" in result["error"]
    assert result["agent_status"]["fetch_pr"]["status"]=="failed"


@pytest.mark.asyncio
async def test_post_to_github_uses_pull_request_review_write(monkeypatch):
    captured = {}

    async def review_handler(payload):
        captured.update(payload)
        return [{"type": "text", "text": json.dumps({"html_url": "https://github.com/octo/repo/pull/7#pullrequestreview-1"})}]

    async def fake_get_mcp_tools(_token):
        return {"pull_request_review_write": FakeTool(review_handler)}

    monkeypatch.setattr(post_to_github, "get_mcp_tools", fake_get_mcp_tools)

    result = await post_to_github.run(_build_state())

    assert captured["method"] == "create"
    assert captured["event"] == "COMMENT"
    assert captured["pullNumber"] == 0
    assert result["github_comment_url"] == "https://github.com/octo/repo/pull/7#pullrequestreview-1"
    assert result["agent_status"]["post_to_github"]["status"] == "completed"


@pytest.mark.asyncio
async def test_architecture_agent_marks_no_rules(monkeypatch):
    import src.db.base as db_base
    import src.tools.vector_search as vector_search

    monkeypatch.setattr(db_base, "AsyncSessionLocal", lambda: DummySessionContext())

    async def fake_search_arch_rules(db, repo_id, query, limit=10):
        return []

    monkeypatch.setattr(vector_search, "search_arch_rules", fake_search_arch_rules)

    result = await architecture_agent.run(_build_state(post_to_github=False))

    assert result["arch_findings"] == []
    assert result["completed_agents"] == ["architecture_agent"]
    assert result["agent_status"]["architecture_agent"]["status"] == "no_rules"


@pytest.mark.asyncio
async def test_architecture_agent_marks_rule_lookup_failure(monkeypatch):
    import src.db.base as db_base
    import src.tools.vector_search as vector_search

    monkeypatch.setattr(db_base, "AsyncSessionLocal", lambda: DummySessionContext())

    async def failing_search_arch_rules(db, repo_id, query, limit=10):
        raise RuntimeError("vector store unavailable")

    monkeypatch.setattr(vector_search, "search_arch_rules", failing_search_arch_rules)

    result = await architecture_agent.run(_build_state(post_to_github=False))

    assert result["arch_findings"] == []
    assert result["completed_agents"] == ["architecture_agent"]
    assert result["agent_status"]["architecture_agent"]["status"] == "rule_lookup_failed"
    assert "vector store unavailable" in result["agent_status"]["architecture_agent"]["error"]


def test_review_schema_accepts_semantic_security_agent():
    finding = ReviewFinding(
        agent="semantic_security_agent",
        severity="high",
        type="authz",
        message="Missing authorization check",
    )

    assert finding.agent == "semantic_security_agent"


@pytest.mark.asyncio
async def test_persist_review_saves_report_and_semantic_findings(monkeypatch):
    captured = {}
    from unittest.mock import AsyncMock
    fake_db = AsyncMock()
    state = _build_state(
        merged_findings=[
            {
                "agent": "semantic_security_agent",
                "severity": "high",
                "type": "authz",
                "file": "backend/src/socket/index.ts",
                "line": 14,
                "message": "Missing authorization check",
                "suggestion": "Validate room membership before join.",
            }
        ],
        final_report="final report",
    )

    monkeypatch.setattr(persist_review, "AsyncSessionLocal", lambda: DummySessionContext(fake_db))

    async def fake_update_review_status(db, review_id, status, report_markdown=None, github_comment_url=None, error_message=None, commit=True):
        captured["update"] = {
            "db": db,
            "review_id": str(review_id),
            "status": status,
            "report_markdown": report_markdown,
            "github_comment_url": github_comment_url,
            "error_message": error_message,
        }

    async def fake_save_findings(db, review_id, repo_id, pr_number, findings, commit=True):
        captured["save"] = {
            "db": db,
            "review_id": str(review_id),
            "repo_id": str(repo_id),
            "pr_number": pr_number,
            "findings": findings,
        }

    monkeypatch.setattr(persist_review, "update_review_status", fake_update_review_status)
    monkeypatch.setattr(persist_review, "save_findings", fake_save_findings)

    result = await persist_review.run(state)

    assert captured["update"]["db"] is fake_db
    assert captured["update"]["status"] == "running"
    assert captured["update"]["report_markdown"] == "final report"
    assert captured["save"]["db"] is fake_db
    assert captured["save"]["pr_number"] == 0
    assert captured["save"]["findings"][0].agent == "semantic_security_agent"
    assert result["agent_status"]["persist_review"]["status"] == "completed"


@pytest.mark.asyncio
async def test_complete_review_marks_review_completed(monkeypatch):
    captured = {}
    from unittest.mock import AsyncMock
    fake_db = AsyncMock()
    state = _build_state()
    state.github_comment_url = "https://github.com/octo/repo/pull/7#pullrequestreview-1"

    monkeypatch.setattr(complete_review, "AsyncSessionLocal", lambda: DummySessionContext(fake_db))

    async def fake_update_review_status(db, review_id, status, report_markdown=None, github_comment_url=None, error_message=None, commit=True):
        captured.update(
            {
                "db": db,
                "review_id": str(review_id),
                "status": status,
                "report_markdown": report_markdown,
                "github_comment_url": github_comment_url,
            }
        )

    monkeypatch.setattr(complete_review, "update_review_status", fake_update_review_status)

    result = await complete_review.run(state)

    assert captured["db"] is fake_db
    assert captured["status"] == "completed"
    assert captured["github_comment_url"] == state.github_comment_url
    assert result["agent_status"]["complete_review"]["status"] == "completed"


@pytest.mark.asyncio
async def test_vector_search_reports_missing_arch_rule_migration(monkeypatch):
    import src.tools.vector_search as vector_search

    class FakeEmbedder:
        async def aembed_query(self, query):
            return [0.1, 0.2]

    class FakeDb:
        async def execute(self, sql, params):
            raise RuntimeError('UndefinedColumnError: column "status" does not exist')

    monkeypatch.setattr(vector_search, "get_embedder", lambda: FakeEmbedder())

    with pytest.raises(RuntimeError) as exc_info:
        await vector_search.search_arch_rules(FakeDb(), "repo-123", "socket diff")

    assert "alembic upgrade head" in str(exc_info.value)


def test_prioritize_changed_file_entries_prefers_source_files_over_lockfiles():
    entries = [
        {"filename": "backend/package-lock.json", "changes": 2000, "patch": "lock diff"},
        {"filename": "backend/src/tasks/controller.ts", "changes": 40, "patch": "controller diff"},
        {"filename": "backend/src/socket/index.ts", "changes": 15, "patch": "socket diff"},
        {"filename": "backend/package.json", "changes": 6, "patch": "manifest diff"},
    ]

    prioritized = prioritize_changed_file_entries(entries, limit=3)

    assert [entry["filename"] for entry in prioritized] == [
        "backend/src/tasks/controller.ts",
        "backend/src/socket/index.ts",
        "backend/package.json",
    ]


def test_build_analysis_diff_uses_selected_patches_only():
    entries = [
        {"filename": "backend/src/tasks/controller.ts", "patch": "@@ -1 +1 @@\n-old\n+new"},
        {"filename": "backend/src/socket/index.ts", "patch": "@@ -3 +3 @@\n-before\n+after"},
    ]

    focused_diff = build_analysis_diff(entries)

    assert "=== backend/src/tasks/controller.ts ===" in focused_diff
    assert "=== backend/src/socket/index.ts ===" in focused_diff
    assert "package-lock.json" not in focused_diff


def test_supervisor_router_skips_semantic_security_for_low_risk_changes():
    state = _build_state(
        post_to_github=False,
    )
    state.changed_files = [
        {"path": "backend/package-lock.json", "content": "lockfile update"},
        {"path": "backend/src/utils/format.ts", "content": "export const format = () => {}"},
    ]

    targets = supervisor.supervisor_router(state)

    target_names = [target.node for target in targets]
    assert "semantic_security_agent" not in target_names
    assert target_names == ["code_analyst", "security_agent", "architecture_agent"]


def test_supervisor_router_triggers_semantic_security_for_high_risk_changes():
    state = _build_state(post_to_github=False)
    state.changed_files = [
        {"path": "backend/src/socket/index.ts", "content": "io.emit('task.updated', task)"},
    ]

    targets = supervisor.supervisor_router(state)

    target_names = [target.node for target in targets]
    assert "semantic_security_agent" in target_names
