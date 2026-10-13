"""Provisioning caches must never bypass signed-token authentication."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request
from src.core import clerk


@pytest.fixture(autouse=True)
def clear_profiles():
    clerk._local_profiles.clear()
    clerk._profile_inflight.clear()
    yield
    clerk._local_profiles.clear()
    clerk._profile_inflight.clear()


class Session:
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass


def setup(monkeypatch):
    monkeypatch.setattr(clerk, 'AsyncSessionLocal', Session)
    read = AsyncMock(return_value=SimpleNamespace(email='fixture@example.test'))
    provision = AsyncMock()
    monkeypatch.setattr(clerk, 'get_user', read)
    monkeypatch.setattr(clerk, 'upsert_user', provision)
    return read, provision


async def test_existing_profile_cache_coalesces_simultaneous_requests(monkeypatch):
    read, provision = setup(monkeypatch)
    async def lookup(*args):
        await asyncio.sleep(.01)
        return SimpleNamespace(email='fixture@example.test')
    read.side_effect = lookup
    state = SimpleNamespace(payload={'sub':'fixture-user'})
    emails = await asyncio.gather(*(clerk._local_email('fixture-user', state) for _ in range(8)))
    assert emails == ['fixture@example.test']*8
    assert await clerk._local_email('fixture-user', state) == emails[0]
    assert read.await_count == 1 and provision.await_count == 0


async def test_expired_and_other_user_profiles_are_read_again(monkeypatch):
    read, _ = setup(monkeypatch)
    state = SimpleNamespace(payload={})
    await clerk._local_email('first', state)
    clerk._local_profiles['first'] = (0, 'old@example.test')
    await clerk._local_email('first', state)
    await clerk._local_email('second', state)
    assert read.await_count == 3


async def test_cached_profile_does_not_accept_an_invalid_jwt(monkeypatch):
    read, _ = setup(monkeypatch)
    verifier = AsyncMock(return_value=SimpleNamespace(is_authenticated=True, payload={'sub':'first'}))
    monkeypatch.setattr(clerk.clerk_client, 'authenticate_request_async', verifier)
    request = Request({'type':'http','headers':[], 'method':'GET', 'path':'/api/reviews'})
    credentials = HTTPAuthorizationCredentials(scheme='Bearer', credentials='fixture-signed-token')
    await clerk.get_current_user(request, credentials)
    await clerk.get_current_user(request, credentials)
    verifier.return_value = SimpleNamespace(is_authenticated=False, payload=None, message='Expired')
    with pytest.raises(HTTPException) as error:
        await clerk.get_current_user(request, credentials)
    assert error.value.status_code == 401
    assert verifier.await_count == 3 and read.await_count == 1


async def test_verification_timeout_is_a_service_failure(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(clerk.clerk_client, 'authenticate_request_async', AsyncMock(side_effect=TimeoutError))
    request = Request({'type':'http','headers':[], 'method':'GET', 'path':'/api/reviews'})
    with pytest.raises(HTTPException) as error:
        await clerk.get_current_user(request, HTTPAuthorizationCredentials(scheme='Bearer', credentials='fixture'))
    assert error.value.status_code == 503


async def test_existing_user_is_never_reinserted(monkeypatch):
    _, provision = setup(monkeypatch)
    await clerk._ensure_local_user('first', 'fixture@example.test')
    provision.assert_not_awaited()
