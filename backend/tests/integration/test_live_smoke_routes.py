"""Live acceptance against an already connected account; never imports PATs."""
import asyncio
import os
import pytest

pytestmark=[pytest.mark.asyncio,pytest.mark.integration,pytest.mark.live_smoke]


async def test_public_routes(live_client):
    assert (await live_client.get('/')).json()['status']=='ok'
    assert (await live_client.get('/api/health')).json()=={'status':'ok'}
    ready=await live_client.get('/api/ready')
    assert ready.status_code==200,ready.text
    assert ready.json()['redis']==ready.json()['supabase']=='ok'
    assert ready.json().get('worker')=='ok'


async def test_protected_discovery_and_history(live_client,auth_headers):
    invalid=await live_client.get('/api/repos/browse',headers={'Authorization':'Bearer invalid'})
    assert invalid.status_code==401
    connection=await live_client.get('/api/auth/github/status',headers=auth_headers)
    assert connection.status_code==200
    listing=await live_client.get('/api/repos/browse?page_size=100',headers=auth_headers)
    assert listing.status_code==200
    assert len(listing.json()['items'])<=100
    history=await live_client.get('/api/reviews?page_size=20',headers=auth_headers)
    assert history.status_code==200 and len(history.json()['items'])<=20
    malformed=await live_client.get('/api/reviews/not-a-uuid',headers=auth_headers)
    assert malformed.status_code==422
    for repo in listing.json()['items'][:1]:
        pulls=await live_client.get(f"/api/repos/{repo['id']}/pulls",headers=auth_headers)
        assert pulls.status_code==200,pulls.text
        branches=await live_client.get(f"/api/repos/{repo['id']}/branches",headers=auth_headers)
        assert branches.status_code==200,branches.text


async def test_designated_pr_review(live_client,live_smoke_config,auth_headers):
    if os.getenv('LIVE_SMOKE_RUN_ANALYSIS','').lower()!='true':
        pytest.skip('Set LIVE_SMOKE_RUN_ANALYSIS=true to run a paid live analysis')
    url=live_smoke_config.github_pr_url
    if not url: pytest.skip('LIVE_SMOKE_GITHUB_PR_URL must designate an authorized test PR')
    from src.core.urls import parse_pr_url
    owner,name,_,_=parse_pr_url(url)
    page=1; repo=None
    while True:
        response=await live_client.get('/api/repos/browse',headers=auth_headers,params={'q':name,'page':page,'page_size':100})
        assert response.status_code==200,response.text
        data=response.json()
        repo=next((r for r in data['items'] if r['owner'].lower()==owner.lower() and r['name'].lower()==name.lower()),None)
        if repo or page*100>=data['total']: break
        page+=1
    assert repo,'Connect GitHub and grant access to the designated repository first'
    started=await live_client.post('/api/reviews',headers=auth_headers,json={'repo_id':repo['id'],'pr_url':url,'post_to_github':False})
    assert started.status_code==202,started.text
    review_id=started.json()['id']
    for _ in range(180):
        row=(await live_client.get('/api/reviews/'+review_id,headers=auth_headers)).json()
        if row['status'] not in ('pending','running'): break
        await asyncio.sleep(5)
    assert row['status'] in ('completed','partial'),row.get('error_message')
    assert row['commit_sha'] and row['coverage']['reviewed_files']>0 and row['report_markdown']
    assert row['posting_status']=='not_requested' and not row['github_comment_url']
