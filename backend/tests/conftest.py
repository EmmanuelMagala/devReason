from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
import pytest


@dataclass(frozen=True)
class LiveSmokeConfig:
	base_url: str
	clerk_bearer_token: str | None
	clerk_user_id: str | None
	clerk_email: str | None
	clerk_webhook_secret: str | None
	github_owner: str | None
	github_repo: str | None
	github_pat: str | None
	github_pr_url: str | None
	chat_message: str
	rule_content: str


def _get_env(name: str) -> str | None:
	value = os.getenv(name)
	if value is None:
		return None
	stripped = value.strip()
	return stripped or None


@pytest.fixture(scope="session")
def live_smoke_config() -> LiveSmokeConfig:
	return LiveSmokeConfig(
		base_url=os.getenv("LIVE_SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
		clerk_bearer_token=_get_env("LIVE_SMOKE_CLERK_BEARER_TOKEN"),
		clerk_user_id=_get_env("LIVE_SMOKE_CLERK_USER_ID"),
		clerk_email=_get_env("LIVE_SMOKE_CLERK_EMAIL"),
		clerk_webhook_secret=_get_env("LIVE_SMOKE_CLERK_WEBHOOK_SECRET"),
		github_owner=_get_env("LIVE_SMOKE_GITHUB_OWNER"),
		github_repo=_get_env("LIVE_SMOKE_GITHUB_REPO"),
		github_pat=_get_env("LIVE_SMOKE_GITHUB_PAT"),
		github_pr_url=_get_env("LIVE_SMOKE_GITHUB_PR_URL"),
		chat_message=os.getenv(
			"LIVE_SMOKE_CHAT_MESSAGE",
			"Summarize the most common findings for this repository.",
		),
		rule_content=os.getenv(
			"LIVE_SMOKE_RULE_CONTENT",
			"Background jobs must not perform blocking I/O in route handlers.",
		),
	)


@pytest.fixture(scope="function")
async def live_client(live_smoke_config: LiveSmokeConfig):
	timeout = httpx.Timeout(120.0, connect=10.0)
	async with httpx.AsyncClient(base_url=live_smoke_config.base_url, timeout=timeout) as client:
		yield client


@pytest.fixture(scope="session")
def auth_headers(live_smoke_config: LiveSmokeConfig) -> dict[str, str]:
	if not live_smoke_config.clerk_bearer_token:
		pytest.skip("LIVE_SMOKE_CLERK_BEARER_TOKEN is required for protected route smoke tests")
	return {"Authorization": f"Bearer {live_smoke_config.clerk_bearer_token}"}
