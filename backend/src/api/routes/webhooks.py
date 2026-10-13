
from fastapi import APIRouter, Request, HTTPException, Depends
from svix.webhooks import Webhook, WebhookVerificationError
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.settings import settings
from src.api.deps import get_db
from src.api.deps import get_redis
from src.db.repositories.user_repo import upsert_user
import structlog

log = structlog.get_logger()
router = APIRouter()


@router.post("/clerk")
async def clerk_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receives Clerk webhook events and syncs users to the database.
    Clerk fires this on user.created and user.updated events.
    Svix signature verification ensures the request is genuinely from Clerk.
    """
    if not settings.clerk_webhook_secret:
        raise HTTPException(status_code=503, detail='Clerk webhook is not configured')
    body = await request.body()
    headers = dict(request.headers)

    try:
        wh = Webhook(settings.clerk_webhook_secret)
        payload = wh.verify(body, headers)
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = payload.get("type")
    if event_type in ("user.created", "user.updated"):
        data = payload.get("data", {})
        clerk_user_id = data.get("id")
        email_addresses = data.get("email_addresses", [])
        email = email_addresses[0].get("email_address", "") if email_addresses else ""

        if clerk_user_id and email:
            await upsert_user(db, clerk_user_id, email)
            log.info("User synced from Clerk", clerk_user_id=clerk_user_id)

    return {"received": True}


@router.post('/github')
async def github_webhook(request: Request,db: AsyncSession=Depends(get_db),redis=Depends(get_redis)):
    import hashlib, hmac, json
    from sqlalchemy import update
    from src.db.models import GitHubInstallation, GitHubConnection, Repo
    if not settings.github_app_webhook_secret: raise HTTPException(503,'GitHub webhook is not configured')
    body=await request.body()
    if len(body)>2_000_000: raise HTTPException(413,'Webhook payload too large')
    expected='sha256='+hmac.new(settings.github_app_webhook_secret.encode(),body,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,request.headers.get('x-hub-signature-256','')): raise HTTPException(400,'Invalid webhook signature')
    delivery=request.headers.get('x-github-delivery')
    if not delivery: raise HTTPException(400,'Missing delivery ID')
    if not await redis.set('github_delivery:'+delivery,'processing',nx=True,ex=60): return {'received':True}
    try:
        payload=json.loads(body); event=request.headers.get('x-github-event'); action=payload.get('action')
        if event=='installation' and action in ('deleted','suspend','unsuspend'):
            installation_id=payload['installation']['id']; status='connected' if action=='unsuspend' else 'revoked' if action=='deleted' else 'suspended'
            await db.execute(update(GitHubInstallation).where(GitHubInstallation.installation_id==installation_id).values(status=status))
            if action=='deleted': await db.execute(update(Repo).where(Repo.github_installation_id==installation_id).values(github_installation_id=None,github_repo_id=None))
        elif event=='installation_repositories':
            removed=[item['id'] for item in payload.get('repositories_removed',[])]
            if removed: await db.execute(update(Repo).where(Repo.github_installation_id==payload['installation']['id'],Repo.github_repo_id.in_(removed)).values(github_installation_id=None,github_repo_id=None))
            # Added repositories are discovered on the next user-verified sync.
        elif event=='github_app_authorization' and action=='revoked':
            await db.execute(update(GitHubConnection).where(GitHubConnection.github_user_id==payload['sender']['id']).values(status='reconnect_required'))
        await db.commit(); await redis.set('github_delivery:'+delivery,'done',ex=86400)
        return {'received':True}
    except Exception:
        await db.rollback(); await redis.delete('github_delivery:'+delivery)
        raise HTTPException(503,'Webhook processing unavailable; retry delivery') from None
