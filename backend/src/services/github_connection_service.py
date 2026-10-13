from datetime import datetime, timedelta, timezone
import uuid
import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from fastapi import HTTPException
from src.core.settings import settings
from src.core.crypto import encrypt, decrypt
from src.core.github_api import request, paginate, pooled_requests
from src.db.models import GitHubConnection, GitHubInstallation


async def exchange_token(**values):
    if not settings.github_app_client_id or not settings.github_app_client_secret:
        raise HTTPException(503,'GitHub connection is not configured. Ask the administrator to configure the OAuth client secret.')
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post('https://github.com/login/oauth/access_token',headers={'Accept':'application/json'},json={'client_id':settings.github_app_client_id,'client_secret':settings.github_app_client_secret,**values})
        response.raise_for_status()
        result = response.json()
        if not result.get('access_token'): raise HTTPException(409,'GitHub authorization expired or was declined. Connect again.')
        return result


def apply_tokens(connection, tokens):
    now = datetime.now(timezone.utc)
    connection.access_token_enc = encrypt(tokens['access_token'])
    if tokens.get('refresh_token'): connection.refresh_token_enc = encrypt(tokens['refresh_token'])
    connection.expires_at = now+timedelta(seconds=tokens['expires_in']) if tokens.get('expires_in') else None
    if tokens.get('refresh_token_expires_in'): connection.refresh_expires_at = now+timedelta(seconds=tokens['refresh_token_expires_in'])
    connection.status = 'connected'


async def save_connection(db, user_id, tokens):
    profile = await request(tokens['access_token'],'GET','/user')
    existing = (await db.execute(select(GitHubConnection).where(GitHubConnection.clerk_user_id==user_id,GitHubConnection.github_user_id==profile['id']).with_for_update())).scalar_one_or_none()
    connection = existing or GitHubConnection(id=uuid.uuid4(),clerk_user_id=user_id,github_user_id=profile['id'])
    connection.login, connection.avatar_url = profile['login'], profile.get('avatar_url')
    apply_tokens(connection,tokens)
    if not existing: db.add(connection)
    await db.commit()
    return connection


async def connection_token(db, connection_id, user_id):
    query=select(GitHubConnection).where(GitHubConnection.id==connection_id,GitHubConnection.clerk_user_id==user_id)
    connection = (await db.execute(query)).scalar_one_or_none()
    if not connection: raise HTTPException(404,'GitHub connection not found')
    if connection.status != 'connected': raise HTTPException(409,'Reconnect GitHub to continue.')
    if connection.expires_at and connection.expires_at <= datetime.now(timezone.utc)+timedelta(seconds=60):
        # Serialize token renewal only. Normal metadata requests must not hold
        # the account row locked while waiting on paginated GitHub responses.
        connection=(await db.execute(query.with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not connection: raise HTTPException(404,'GitHub connection not found')
        if connection.status!='connected': raise HTTPException(409,'Reconnect GitHub to continue.')
        if not connection.expires_at or connection.expires_at > datetime.now(timezone.utc)+timedelta(seconds=60):
            await db.commit()
            return connection,decrypt(connection.access_token_enc)
        if not connection.refresh_token_enc or (connection.refresh_expires_at and connection.refresh_expires_at <= datetime.now(timezone.utc)):
            connection.status='reconnect_required'; await db.commit()
            raise HTTPException(409,'Reconnect GitHub to renew access.')
        try: apply_tokens(connection,await exchange_token(grant_type='refresh_token',refresh_token=decrypt(connection.refresh_token_enc)))
        except Exception:
            connection.status='reconnect_required'; await db.commit()
            raise HTTPException(409,'Reconnect GitHub to renew access.') from None
        await db.commit()
    return connection, decrypt(connection.access_token_enc)


@pooled_requests
async def verified_installation(db, user_id, installation_id, connection_id=None, repo_id=None, persist_binding=True):
    query = select(GitHubConnection).where(GitHubConnection.clerk_user_id==user_id,GitHubConnection.status=='connected')
    if connection_id: query=query.where(GitHubConnection.id==connection_id)
    connections = (await db.execute(query)).scalars().all()
    for connection in connections:
        try:
            _, token = await connection_token(db,connection.id,user_id)
            installations = await paginate(token,'/user/installations',collection='installations')
        except HTTPException as error:
            if connection_id or error.status_code not in (401,403,409): raise
            continue
        installation = next((item for item in installations if item['id']==installation_id),None)
        if installation:
            if installation.get('suspended_at'):
                raise HTTPException(409,'This installation is suspended. Ask the account administrator to restore access.')
            # Use user-scoped listing: the App alone may access repos the user cannot.
            repositories = await paginate(token,f'/user/installations/{installation_id}/repositories',collection='repositories')
            if repo_id is not None and not any(repo['id']==repo_id for repo in repositories): continue
            if persist_binding:
                statement=insert(GitHubInstallation).values(id=uuid.uuid4(),connection_id=connection.id,installation_id=installation_id,account_login=installation['account']['login'],status='connected')
                await db.execute(statement.on_conflict_do_update(index_elements=['connection_id','installation_id'],set_={'status':'connected','account_login':installation['account']['login']}))
                await db.commit()
            return connection, token, repositories
    raise HTTPException(403,'This GitHub installation is not accessible to your connected account.')


async def authorize_repo(db, user_id, repo):
    if not repo.github_installation_id: raise HTTPException(409,'Connect this repository through the verified GitHub App flow.')
    _, token, repositories = await verified_installation(db,user_id,int(repo.github_installation_id),repo_id=repo.github_repo_id,persist_binding=False)
    if not any(item['id']==repo.github_repo_id and item['owner']['login'].lower()==repo.owner.lower() and item['name'].lower()==repo.name.lower() for item in repositories):
        raise HTTPException(403,'Repository access was removed. Grant access in GitHub before reviewing it.')
    return token
