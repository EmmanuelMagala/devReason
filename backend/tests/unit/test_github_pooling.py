"""Clients may reuse sockets but must keep authorization tokens isolated."""
from types import SimpleNamespace
import pytest
from src.core import github_api


async def test_request_scope_reuses_connections_without_sharing_credentials(monkeypatch):
    opened=[]; closed=[]
    class Client:
        def __init__(self, token, **options):
            self.token=token
            assert options['http_cache'] is False
        async def __aenter__(self): opened.append(self.token); return self
        async def __aexit__(self,*args): closed.append(self.token)
        async def arequest(self,*args,**kwargs): return SimpleNamespace(json=lambda: self.token)
    monkeypatch.setattr(github_api,'GitHub',Client)
    @github_api.pooled_requests
    async def operation():
        assert await github_api.request('account-a','GET','/user')=='account-a'
        assert await github_api.request('account-b','GET','/user')=='account-b'
        assert await github_api.request('account-a','GET','/user/installations')=='account-a'
    await operation()
    assert opened==['account-a','account-b']
    assert sorted(closed)==sorted(opened)
    assert github_api._scope.get() is None


async def test_failed_operation_closes_clients_and_resets_scope(monkeypatch):
    closed=[]
    class Client:
        def __init__(self,token,**options): self.token=token
        async def __aenter__(self): return self
        async def __aexit__(self,*args): closed.append(self.token)
        async def arequest(self,*args,**kwargs): raise RuntimeError('Fixture failure')
    monkeypatch.setattr(github_api,'GitHub',Client)
    @github_api.pooled_requests
    async def operation(): await github_api.request('account-a','GET','/user')
    with pytest.raises(Exception): await operation()
    assert closed==['account-a'] and github_api._scope.get() is None
