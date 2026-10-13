import json
from unittest.mock import AsyncMock
import pytest
from src.core.urls import parse_pr_url
from src.tools.osv_search import _extract_cvss, _parse_osv_result
from src.tools.dependencies import extract_packages
from src.agents.analysis import parse_findings


def test_url_rejects_foreign_hosts_and_normalizes_tabs():
    with pytest.raises(ValueError): parse_pr_url('https://example.com/a/b/pull/1')
    assert parse_pr_url('https://github.com/a/b/pull/42/files?x=1') == ('a','b',42,'https://github.com/a/b/pull/42')
    with pytest.raises(ValueError): parse_pr_url('https://github.com@evil.test/a/b/pull/1')


def test_cvss_vectors_and_unknown_severity():
    assert _extract_cvss({'severity':[{'score':'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H'}]}) == 9.8
    assert _extract_cvss({}) is None
    item=_parse_osv_result({'name':'lodash','version':'4.17.20'},{'vulns':[{'id':'GHSA-example','aliases':['CVE-2021-23337']}]})[0]
    assert item['cve_id']=='CVE-2021-23337' and item['cvss_score'] is None


def test_resolved_manifests():
    assert extract_packages({'path':'package.json','content':'{"dependencies":{"x":"^1.0.0"}}'}) == []
    packages=extract_packages({'path':'package-lock.json','content':json.dumps({'packages':{'node_modules/@scope/x':{'version':'1.2.3'}}})})
    assert packages[0]['name']=='@scope/x' and packages[0]['version']=='1.2.3'
    assert extract_packages({'path':'Cargo.lock','content':'[[package]]\nname="serde"\nversion="1.0.0"'})[0]['ecosystem']=='crates.io'
    assert extract_packages({'path':'go.mod','content':'require golang.org/x/net v0.1.0'})[0]['name']=='golang.org/x/net'


def test_invalid_model_output_is_not_clean_analysis():
    with pytest.raises(ValueError): parse_findings('not JSON','code_analyst')
    with pytest.raises(ValueError): parse_findings('{}','code_analyst')


@pytest.mark.asyncio
async def test_atomic_embedding_rolls_back_on_failure(monkeypatch):
    from src.services import memory_service
    db=AsyncMock(); db.add=lambda rule: None
    db.execute.side_effect=RuntimeError('write failed')
    monkeypatch.setattr(memory_service,'get_embedder',lambda: type('E',(),{'aembed_query':AsyncMock(return_value=[0.0]*1536)})())
    with pytest.raises(RuntimeError): await memory_service.embed_and_store_rule(db,'00000000-0000-0000-0000-000000000001','Rule')
    db.rollback.assert_awaited_once(); db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unverified_installation_rejected(monkeypatch):
    from src.services.github_connection_service import verified_installation
    db=AsyncMock()
    result=type('R',(),{'scalars':lambda self:self,'all':lambda self:[]})()
    db.execute.return_value=result
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error: await verified_installation(db,'user_attacker',123)
    assert error.value.status_code==403


@pytest.mark.asyncio
async def test_github_rate_limit_returns_actionable_error_without_waiting(monkeypatch):
    import asyncio
    import time
    import httpx
    from githubkit import GitHub
    from fastapi import HTTPException
    from src.core import github_api
    calls=[]
    async def respond(request):
        calls.append(request.url.path)
        return httpx.Response(403,headers={'x-ratelimit-remaining':'0','x-ratelimit-reset':str(int(time.time())+3600)},json={'message':'API rate limit exceeded'})
    transport=httpx.MockTransport(respond)
    monkeypatch.setattr(github_api,'GitHub',lambda token,**kwargs: GitHub(token,async_transport=transport,**kwargs))
    with pytest.raises(HTTPException) as error:
        await asyncio.wait_for(github_api.request('fixture-token','GET','/user'),2)
    assert error.value.status_code==429 and calls==['/user']


def test_snapshot_context_does_not_duplicate_source_and_preserves_position():
    from src.agents.state import RepoConfig, ReviewState
    from src.agents.nodes import code_analyst, semantic_security_agent
    source='def continuation_at_line_50():\n    return True\n'
    config=RepoConfig(repo_id='fixture',review_id='fixture',owner='acme',name='widget',github_token='fixture',mode='snapshot')
    state=ReviewState(repo_config=config,pr_url='',pr_number=0,pr_diff=source,analysis_diff=source,changed_files=[{'path':'src/api.py','content':source,'start_line':50}])
    for node in (code_analyst,semantic_security_agent):
        context=node._build_context(state)
        assert context.count(source)==1 and 'first source line: 50' in context


def test_checkpoint_serializer_restores_registered_application_types_only():
    from src.core.checkpointer import checkpoint_serializer
    from src.agents.state import RepoConfig
    from pydantic import SecretStr
    serde=checkpoint_serializer()
    config=RepoConfig(repo_id='fixture',review_id='fixture',owner='acme',name='widget',github_token='fixture')
    restored=serde.loads_typed(serde.dumps_typed({'config':config,'token':SecretStr('fixture')}))
    assert restored['config'].owner=='acme' and restored['token'].get_secret_value()=='fixture'
    # Unregistered constructors remain blocked even if their module is importable.
    import ormsgpack
    from types import SimpleNamespace
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    payload=ormsgpack.packb(('types','SimpleNamespace',{'flag':'fixture'}))
    encoded=('msgpack',ormsgpack.packb(ormsgpack.Ext(2,payload)))
    assert isinstance(JsonPlusSerializer(allowed_msgpack_modules=True).loads_typed(encoded),SimpleNamespace)
    assert serde.loads_typed(encoded)=={'flag':'fixture'}
    assert type(serde.loads_typed(encoded)) is dict
