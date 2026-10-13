
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text, or_, and_
from src.db.models import Conversation, ConversationMessage, ArchRule
from src.api.deps import get_db, get_current_user
from src.schemas.repo import (
    RepoRead,
    ArchRuleCreate,
    ArchRuleRead,
    ArchRuleSuggestionRequest,
    ArchRuleUpdate,
)
from src.schemas.chat import ChatRequest
from src.db.repositories.repo_repo import (
    get_repos_for_user,
    get_repo_by_id,
    get_arch_rule_by_id,
    get_arch_rules,
    update_arch_rule_status,
)
from src.services.architecture_rule_service import suggest_architecture_rules
from src.services.memory_service import embed_and_store_rule
from src.services.chat_service import stream_chat
import structlog

log = structlog.get_logger()
router = APIRouter()


@router.get("")
async def list_repos(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RepoRead]:
    repos = await get_repos_for_user(db, user["clerk_user_id"])
    return [RepoRead.model_validate(r) for r in repos]


@router.post("/{repo_id}/rules", status_code=201)
async def add_arch_rule(
    repo_id: uuid.UUID,
    body: ArchRuleCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ArchRuleRead:
    repo = await get_repo_by_id(db, uuid.UUID(str(repo_id)))
    if not repo or repo.clerk_user_id != user["clerk_user_id"]:
        raise HTTPException(status_code=404, detail="Repo not found")

    rule = await embed_and_store_rule(db, repo_id, body.content)
    return ArchRuleRead.model_validate(rule)


@router.post("/{repo_id}/rules/suggest", status_code=201)
async def suggest_repo_arch_rules(
    repo_id: uuid.UUID,
    body: ArchRuleSuggestionRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ArchRuleRead]:
    repo = await get_repo_by_id(db, uuid.UUID(str(repo_id)))
    if not repo or repo.clerk_user_id != user["clerk_user_id"]:
        raise HTTPException(status_code=404, detail="Repo not found")

    from src.services.github_connection_service import authorize_repo
    await authorize_repo(db,user['clerk_user_id'],repo)
    try: rules = await suggest_architecture_rules(db, repo, refresh=body.refresh)
    except Exception:
        await db.rollback()
        raise HTTPException(502,'Architecture suggestions could not be generated. Please retry.') from None
    return [ArchRuleRead.model_validate(rule) for rule in rules]


@router.get("/{repo_id}/rules")
async def list_arch_rules(
    repo_id: uuid.UUID,
    status: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ArchRuleRead]:
    repo = await get_repo_by_id(db, uuid.UUID(str(repo_id)))
    if not repo or repo.clerk_user_id != user["clerk_user_id"]:
        raise HTTPException(status_code=404, detail="Repo not found")
    rules = await get_arch_rules(db, uuid.UUID(str(repo_id)), status=status)
    return [ArchRuleRead.model_validate(r) for r in rules]


@router.patch("/{repo_id}/rules/{rule_id}")
async def update_arch_rule(
    repo_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: ArchRuleUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ArchRuleRead:
    repo = await get_repo_by_id(db, uuid.UUID(str(repo_id)))
    if not repo or repo.clerk_user_id != user["clerk_user_id"]:
        raise HTTPException(status_code=404, detail="Repo not found")

    rule = await get_arch_rule_by_id(db, uuid.UUID(str(rule_id)))
    if not rule or rule.repo_id != uuid.UUID(str(repo_id)):
        raise HTTPException(status_code=404, detail="Rule not found")

    if body.content is None:
        updated_rule = await update_arch_rule_status(db, rule, body.status)
    else:
        from src.core.embeddings import get_embedder
        from src.core.settings import settings
        embedding=await get_embedder().aembed_query(body.content.strip())
        if len(embedding)!=settings.openai_embedding_dimensions: raise HTTPException(502,'Rule embedding could not be generated')
        try:
            rule.content=body.content.strip()
            if body.status: rule.status=body.status
            await db.execute(text('UPDATE arch_rules SET embedding=CAST(:emb AS vector) WHERE id=:id'),{'emb':str(embedding),'id':str(rule.id)})
            await db.commit(); await db.refresh(rule)
        except Exception:
            await db.rollback(); raise
        updated_rule=rule
    return ArchRuleRead.model_validate(updated_rule)


@router.delete('/{repo_id}/rules/{rule_id}',status_code=204)
async def delete_rule(repo_id: uuid.UUID,rule_id: uuid.UUID,user=Depends(get_current_user),db=Depends(get_db)):
    repo=await get_repo_by_id(db,repo_id)
    if not repo or repo.clerk_user_id!=user['clerk_user_id']: raise HTTPException(404,'Repository not found')
    result=await db.execute(delete(ArchRule).where(ArchRule.id==rule_id,ArchRule.repo_id==repo_id))
    if not result.rowcount: raise HTTPException(404,'Rule not found')
    await db.commit()


@router.get('/{repo_id}/conversation')
async def conversation(repo_id: uuid.UUID,before: uuid.UUID|None=None,user=Depends(get_current_user),db=Depends(get_db)):
    repo=await get_repo_by_id(db,repo_id)
    if not repo or repo.clerk_user_id!=user['clerk_user_id']: raise HTTPException(404,'Repository not found')
    query=select(ConversationMessage).join(Conversation,ConversationMessage.conv_id==Conversation.id).where(Conversation.clerk_user_id==user['clerk_user_id'],Conversation.repo_id==repo_id)
    if before:
        cursor=(await db.execute(query.where(ConversationMessage.id==before))).scalar_one_or_none()
        if not cursor: raise HTTPException(422,'Invalid conversation cursor')
        query=query.where(or_(ConversationMessage.created_at<cursor.created_at,and_(ConversationMessage.created_at==cursor.created_at,ConversationMessage.id<cursor.id)))
    rows=list((await db.execute(query.order_by(ConversationMessage.created_at.desc(),ConversationMessage.id.desc()).limit(101))).scalars())
    has_more=len(rows)>100; rows=rows[:100]
    return {'items':[{'id':str(row.id),'role':row.role,'content':row.content,'timestamp':row.created_at.isoformat()} for row in reversed(rows)],'has_more':has_more,'next_cursor':str(rows[-1].id) if has_more else None}


@router.post("/{repo_id}/chat")
async def repo_chat(
    repo_id: uuid.UUID,
    body: ChatRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    repo = await get_repo_by_id(db, uuid.UUID(str(repo_id)))
    if not repo or repo.clerk_user_id != user["clerk_user_id"]:
        raise HTTPException(status_code=404, detail="Repo not found")

    stream = stream_chat(
        db=db,
        store=getattr(request.app.state, "store", None),
        clerk_user_id=user["clerk_user_id"],
        repo_id=str(repo_id),
        user_message=body.message,
    )
    return StreamingResponse(stream, media_type="text/plain")
