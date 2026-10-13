import base64
import hashlib
import json
import secrets
import uuid
import asyncio
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl, unquote
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from src.api.deps import get_current_user, get_db, get_redis
from src.core.settings import settings
from src.db.models import GitHubConnection, GitHubInstallation
from src.db.repositories.repo_repo import upsert_installation_repositories, get_repos_for_user
from src.schemas.repo import RepoRead, GitHubAppInstallSync
from src.services.github_connection_service import exchange_token, save_connection, connection_token, verified_installation
from src.core.github_api import paginate, pooled_requests
from src.core.crypto import encrypt, decrypt

router = APIRouter()
INSTALL_COOKIE = 'devreason_github_install'
INSTALL_COOKIE_PATH = '/api/auth/github/setup'


class ConnectRequest(BaseModel):
    return_to: str = '/repositories'


class CompleteConnection(BaseModel):
    ticket: str


def safe_return(value):
    if not isinstance(value,str) or len(value)>2048: return '/repositories'
    decoded=unquote(value)
    if not decoded.startswith('/') or decoded.startswith('//') or '\\' in decoded or any(ord(char)<32 for char in decoded): return '/repositories'
    try:
        parsed=urlsplit(value)
        return value if not parsed.scheme and not parsed.netloc else '/repositories'
    except ValueError: return '/repositories'


def frontend_origin(value=None):
    allowed={origin.strip().rstrip('/') for origin in settings.allowed_origins.split(',')}
    allowed.add(settings.frontend_base_url.rstrip('/'))
    return value if value in allowed else settings.frontend_base_url.rstrip('/')


def frontend_redirect(path=None, *, origin=None, **params):
    # Missing installation state can occur when updating an existing grant.
    # The frontend restores navigation intent only; it still verifies access.
    if path is None:
        path='/settings/integrations'; params['github_return']='1'
    parsed=urlsplit(safe_return(path))
    query=[(key,value) for key,value in parse_qsl(parsed.query,keep_blank_values=True) if key not in params]+list(params.items())
    location=urlunsplit(('', '', parsed.path, urlencode(query), parsed.fragment))
    return RedirectResponse(frontend_origin(origin)+location)


@router.post('/github/start')
async def start(body: ConnectRequest, request: Request, user=Depends(get_current_user), redis=Depends(get_redis)):
    if not settings.github_app_client_id or not settings.github_app_client_secret:
        raise HTTPException(503,'GitHub OAuth is not configured. Set the App client ID and client secret on the backend.')
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    payload={'clerk_user_id':user['clerk_user_id'],'verifier':verifier,'return_to':safe_return(body.return_to),'frontend_origin':frontend_origin(request.headers.get('origin'))}
    try: await redis.setex('github_oauth:'+state,600,json.dumps(payload))
    except Exception: raise HTTPException(503,'GitHub connection is temporarily unavailable. Please retry shortly.') from None
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    url='https://github.com/login/oauth/authorize?'+urlencode({'client_id':settings.github_app_client_id,'redirect_uri':settings.github_oauth_callback_url,'state':state,'code_challenge':challenge,'code_challenge_method':'S256','prompt':'select_account'})
    return {'authorize_url':url,'install_url':url}


@router.get('/github/callback')
async def callback(state: str=Query(...), code: str|None=None, error: str|None=None, redis=Depends(get_redis), db=Depends(get_db)):
    try: raw=await redis.getdel('github_oauth:'+state)
    except Exception: return frontend_redirect(github_error='Connection service unavailable. Please retry.')
    if not raw: return frontend_redirect(github_error='Connection expired or was already used. Connect again.')
    payload=json.loads(raw)
    if error or not code: return frontend_redirect(payload['return_to'],origin=payload.get('frontend_origin'),github_error='GitHub authorization was cancelled.')
    try:
        tokens=await exchange_token(code=code,code_verifier=payload['verifier'],redirect_uri=settings.github_oauth_callback_url)
        # Final binding requires the currently signed-in Clerk user. A shared
        # authorization link must never connect another browser's GitHub identity.
        ticket=secrets.token_urlsafe(32)
        await redis.setex('github_pending:'+ticket,600,json.dumps({'clerk_user_id':payload['clerk_user_id'],'tokens_enc':encrypt(json.dumps(tokens))}))
        return frontend_redirect(payload['return_to'],origin=payload.get('frontend_origin'),github_ticket=ticket)
    except Exception: return frontend_redirect(payload['return_to'],origin=payload.get('frontend_origin'),github_error='GitHub could not be connected. Please retry.')


@router.post('/github/complete')
async def complete(body: CompleteConnection,user=Depends(get_current_user),redis=Depends(get_redis),db=Depends(get_db)):
    raw=await redis.get('github_pending:'+body.ticket)
    if not raw: raise HTTPException(409,'GitHub connection expired or was already completed. Connect again.')
    pending=json.loads(raw)
    if pending['clerk_user_id']!=user['clerk_user_id']: raise HTTPException(403,'Sign in to the account that started this GitHub connection.')
    raw=await redis.getdel('github_pending:'+body.ticket)
    if not raw: raise HTTPException(409,'GitHub connection was already completed.')
    pending=json.loads(raw)
    connection=await save_connection(db,user['clerk_user_id'],json.loads(decrypt(pending['tokens_enc'])))
    return {'connected':True,'connection_id':str(connection.id)}


@router.get('/github/status')
async def status(user=Depends(get_current_user),db=Depends(get_db)):
    connections=(await db.execute(select(GitHubConnection).where(GitHubConnection.clerk_user_id==user['clerk_user_id']))).scalars().all()
    return {'configured':bool(settings.github_app_client_id and settings.github_app_client_secret),'connections':[{'id':str(c.id),'login':c.login,'avatar_url':c.avatar_url,'status':c.status} for c in connections]}


@router.get('/github/installations')
async def installations(connection_id: uuid.UUID, user=Depends(get_current_user),db=Depends(get_db)):
    _,token=await connection_token(db,connection_id,user['clerk_user_id'])
    return {'items':[{'id':i['id'],'account':i['account']['login'],'avatar_url':i['account'].get('avatar_url'),'status':'suspended' if i.get('suspended_at') else 'connected'} for i in await paginate(token,'/user/installations',collection='installations')]}


@router.post('/github/install')
async def install(request: Request, connection_id: uuid.UUID, return_to: str='/repositories', installation_id: int|None=Query(None,ge=1), user=Depends(get_current_user), db=Depends(get_db), redis=Depends(get_redis)):
    _,token=await connection_token(db,connection_id,user['clerk_user_id'])
    install_url=f'https://github.com/apps/{settings.github_app_slug}/installations/new'
    if installation_id is not None:
        items=await paginate(token,'/user/installations',collection='installations')
        installation=next((item for item in items if item['id']==installation_id),None)
        if not installation: raise HTTPException(403,'This installation is not accessible to your connected GitHub account.')
        if installation.get('suspended_at'): raise HTTPException(409,'This installation is suspended. Ask its administrator to restore access.')
        manage_url=installation.get('html_url','')
        parsed=urlsplit(manage_url)
        if parsed.scheme!='https' or parsed.netloc!='github.com': raise HTTPException(502,'GitHub did not return a valid installation settings page. Use Grant repository access instead.')
        install_url=manage_url
    state=secrets.token_urlsafe(32)
    try:
        await redis.setex('github_install:'+state,600,json.dumps({'clerk_user_id':user['clerk_user_id'],'connection_id':str(connection_id),'return_to':safe_return(return_to),'frontend_origin':frontend_origin(request.headers.get('origin'))}))
    except Exception: raise HTTPException(503,'GitHub connection is temporarily unavailable. Please retry shortly.') from None
    separator='&' if '?' in install_url else '?'
    response=JSONResponse({'install_url':install_url+separator+urlencode({'state':state})})
    # Existing-installation settings do not always forward the query state.
    # Store only the opaque one-use state; ownership remains verified below.
    response.set_cookie(INSTALL_COOKIE,state,max_age=600,path=INSTALL_COOKIE_PATH,httponly=True,samesite='lax',secure=urlsplit(settings.api_base_url).scheme=='https')
    return response


async def sync_verified(db,user_id,installation_id,connection_id=None):
    connection,_,repositories=await verified_installation(db,user_id,installation_id,connection_id)
    # Connected accounts can see different subsets of the same organization.
    # Import their union so synchronizing one cannot remove another's access.
    others=(await db.execute(select(GitHubConnection).where(GitHubConnection.clerk_user_id==user_id,GitHubConnection.status=='connected',GitHubConnection.id!=connection.id))).scalars().all()
    for other in others:
        try:
            _,_,additional=await verified_installation(db,user_id,installation_id,other.id)
            repositories+=additional
        except HTTPException as error:
            if error.status_code not in (401,403,409): raise
    repositories=list({repository['id']:repository for repository in repositories}.values())
    normalized=[{'id':r['id'],'owner':r['owner']['login'],'name':r['name']} for r in repositories]
    synced,count=await upsert_installation_repositories(db,user_id,installation_id,normalized,commit=False)
    details={item['id']:item for item in repositories}
    for repo in synced:
        item=details[repo.github_repo_id]
        repo.details={key:item.get(key) for key in ('description','private','language','default_branch','updated_at','html_url')}
    await db.commit()
    return {'imported_count':count,'repositories':[RepoRead.model_validate(r).model_dump(mode='json') for r in await get_repos_for_user(db,user_id)]}


@router.get('/github/setup')
async def setup(request: Request, installation_id: int|None=Query(None,ge=1), state: str|None=None, setup_action: str='install', redis=Depends(get_redis),db=Depends(get_db)):
    # Setup URL parameters alone are never accepted as proof of ownership.
    def redirect(path=None, origin=None, **params):
        response=frontend_redirect(path,origin=origin,**params)
        response.delete_cookie(INSTALL_COOKIE,path=INSTALL_COOKIE_PATH)
        return response
    if setup_action not in ('install','update','request'):
        return redirect(github_notice='Verify your GitHub connection to load newly granted repositories.')
    state=state or request.cookies.get(INSTALL_COOKIE)
    try: raw=await redis.getdel('github_install:'+state) if state else None
    except Exception: return redirect(github_error='Connection service unavailable. Please retry.')
    payload=json.loads(raw) if raw else None
    return_to=payload['return_to'] if payload else None
    origin=payload.get('frontend_origin') if payload else None
    if setup_action=='request': return redirect(return_to,origin,github_notice='Repository access is awaiting organization approval. Ask an administrator to approve the App.')
    if not payload:
        return redirect(github_notice='Verify your GitHub connection to load newly granted repositories.')
    if installation_id is None:
        return redirect(return_to,origin,github_error='GitHub did not return an installation. Grant repository access again.')
    try:
        await sync_verified(db,payload['clerk_user_id'],installation_id,uuid.UUID(payload['connection_id']))
        return redirect(return_to,origin,github_connected='1')
    except HTTPException as error:
        message='Your connected GitHub account cannot access this installation. Reconnect the correct account.' if error.status_code in (401,403,404,409) else 'GitHub access could not be verified. Return to Settings and retry.'
        return redirect(return_to,origin,github_error=message)
    except Exception:
        return redirect(return_to,origin,github_error='GitHub access could not be verified. Return to Settings and retry.')


@router.post('/github/sync')
async def sync(body: GitHubAppInstallSync,user=Depends(get_current_user),db=Depends(get_db)):
    return await sync_verified(db,user['clerk_user_id'],body.installation_id,body.connection_id)


@router.get('/github/repositories')
async def repositories(installation_id: int,user=Depends(get_current_user),db=Depends(get_db)):
    _,_,items=await verified_installation(db,user['clerk_user_id'],installation_id)
    return {'installation_id':installation_id,'repositories':[{'id':r['id'],'owner':r['owner']['login'],'name':r['name'],'full_name':r['full_name']} for r in items]}


@router.post('/github/refresh')
async def refresh(user=Depends(get_current_user),db=Depends(get_db)):
    try:
        async with asyncio.timeout(45):
            return await refresh_connections(db,user['clerk_user_id'])
    except TimeoutError:
        await db.rollback()
        raise HTTPException(504,'GitHub access refresh took too long. Your saved reviews remain available. Please retry.') from None


@pooled_requests
async def refresh_connections(db,user_id):
    connections=(await db.execute(select(GitHubConnection).where(GitHubConnection.clerk_user_id==user_id,GitHubConnection.status=='connected'))).scalars().all()
    bindings=(await db.execute(select(GitHubInstallation).join(GitHubConnection,GitHubInstallation.connection_id==GitHubConnection.id).where(GitHubConnection.clerk_user_id==user_id))).scalars().all()
    notices=[]; accounts=[]; repositories_by_installation={}; verified_bindings=[]
    unsafe_installations=set()
    for connection in connections:
        try:
            _,token=await connection_token(db,connection.id,user_id)
            items=await paginate(token,'/user/installations',collection='installations')
            active_ids={i['id'] for i in items if not i.get('suspended_at')}
            for binding in bindings:
                if binding.connection_id==connection.id and binding.installation_id not in active_ids: binding.status='revoked'
            for item in items:
                accounts.append({'account':item['account']['login'],'connection_id':str(connection.id),'installation_id':item['id'],'status':'suspended' if item.get('suspended_at') else 'connected','manage_url':item.get('html_url')})
                if item.get('suspended_at'): continue
                # Each account proves its own installation and repository access
                # once. Union accounts before updating a shared organization.
                repositories=await paginate(token,f"/user/installations/{item['id']}/repositories",collection='repositories')
                repositories_by_installation.setdefault(item['id'],{}).update({r['id']:r for r in repositories})
                verified_bindings.append({'id':uuid.uuid4(),'connection_id':connection.id,'installation_id':item['id'],'account_login':item['account']['login'],'status':'connected'})
            if not items: notices.append('Grant repository access to this App. Organization access may require an administrator’s approval.')
        except HTTPException as error:
            if error.status_code in (429,502,503): raise
            notices.append(error.detail)
            # A failed account must not erase another account's shared repo set.
            unsafe_installations.update(b.installation_id for b in bindings if b.connection_id==connection.id)
            if error.status_code in (403,409):
                connection.status='reconnect_required'
    if verified_bindings:
        statement=insert(GitHubInstallation).values(verified_bindings)
        await db.execute(statement.on_conflict_do_update(index_elements=['connection_id','installation_id'],set_={'status':statement.excluded.status,'account_login':statement.excluded.account_login}))
    for installation_id,repositories in repositories_by_installation.items():
        if installation_id in unsafe_installations: continue
        normalized=[{'id':r['id'],'owner':r['owner']['login'],'name':r['name']} for r in repositories.values()]
        synced,_=await upsert_installation_repositories(db,user_id,installation_id,normalized,commit=False)
        for repo in synced:
            item=repositories[repo.github_repo_id]
            repo.details={key:item.get(key) for key in ('description','private','language','default_branch','updated_at','html_url')}
    await db.commit()
    return {'accounts':accounts,'notices':notices}


@router.delete('/github/connections/{connection_id}',status_code=204)
async def disconnect(connection_id: uuid.UUID,user=Depends(get_current_user),db=Depends(get_db)):
    result=await db.execute(delete(GitHubConnection).where(GitHubConnection.id==connection_id,GitHubConnection.clerk_user_id==user['clerk_user_id']))
    if not result.rowcount: raise HTTPException(404,'Connection not found')
    await db.commit()
