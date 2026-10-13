
import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from src.core.llm import get_model
from src.db.models import Conversation, ConversationMessage
from sqlalchemy.dialects.postgresql import insert
import uuid

log = structlog.get_logger()

SYSTEM_PROMPT = """You are a helpful engineering assistant using this repository's saved code review history and findings. You do not have access to the full source code.
Answer questions about recurring issues, patterns, fixed bugs, and code quality trends.
Be specific — reference actual findings when you can. Keep answers concise and actionable."""


async def get_conversation(db,user_id,repo_id):
    await db.execute(insert(Conversation).values(id=uuid.uuid4(),clerk_user_id=user_id,repo_id=uuid.UUID(str(repo_id))).on_conflict_do_nothing(index_elements=['clerk_user_id','repo_id']))
    await db.commit()
    return (await db.execute(select(Conversation).where(Conversation.clerk_user_id==user_id,Conversation.repo_id==uuid.UUID(str(repo_id))))).scalar_one()


async def handle_chat(
    db: AsyncSession,
    store,
    clerk_user_id: str,
    repo_id: str,
    user_message: str,
) -> str:
    """
    Handles one chat message for a repo conversation.
    Loads conversation history + repo insights + recent findings.
    Calls LLM directly (no agent graph needed).
    Returns the assistant reply string.
    """
    # 1. Get or create conversation
    conv = await get_conversation(db,clerk_user_id,repo_id)

    # 2. Load last 20 messages
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conv_id == conv.id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(20)
    )
    history = list(reversed(result.scalars().all()))

    # 3. Load repo insights from Store
    insights_text = ""
    try:
        namespace = ("repos", repo_id, "insights")
        item = await store.aget(namespace, "aggregated")
        if item and item.value:
            insights = item.value
            top_issues = sorted(
                insights.get("common_issue_types", {}).items(),
                key=lambda x: x[1], reverse=True
            )[:5]
            insights_text = f"\nRepo stats: {insights.get('total_reviews', 0)} total reviews. Top issues: {', '.join(f'{k}({v})' for k, v in top_issues)}"
    except Exception:
        pass

    # 4. Load recent findings from Postgres
    findings_result = await db.execute(
        text("""
            SELECT agent, severity, type, file, message
            FROM findings f
            JOIN reviews r ON r.id = f.review_id
            WHERE r.repo_id = :repo_id
            ORDER BY f.created_at DESC
            LIMIT 30
        """),
        {"repo_id": repo_id},
    )
    findings_rows = findings_result.fetchall()
    findings_text = "\n".join(
        f"[{r.severity.upper()}] {r.agent}: {r.message}" for r in findings_rows
    ) if findings_rows else "No findings yet."

    # 5. Build and call LLM
    model = get_model(temperature=0.3)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT + insights_text),
    ]
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        else:
            from langchain_core.messages import AIMessage
            messages.append(AIMessage(content=msg.content))

    messages.append(HumanMessage(
        content=f"Recent findings:\n{findings_text}\n\nUser question: {user_message}"
    ))

    response = await model.ainvoke(messages)
    reply = response.content

    # 6. Save both messages
    db.add(ConversationMessage(id=uuid.uuid4(), conv_id=conv.id, role="user", content=user_message))
    db.add(ConversationMessage(id=uuid.uuid4(), conv_id=conv.id, role="assistant", content=reply))
    await db.commit()

    return reply


async def stream_chat(
    db: AsyncSession,
    store,
    clerk_user_id: str,
    repo_id: str,
    user_message: str,
):
    """
    Streams the assistant reply while persisting the completed conversation turn.
    """
    conv = await get_conversation(db,clerk_user_id,repo_id)

    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conv_id == conv.id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(20)
    )
    history = list(reversed(result.scalars().all()))

    insights_text = ""
    if store is not None:
        try:
            namespace = ("repos", repo_id, "insights")
            item = await store.aget(namespace, "aggregated")
            if item and item.value:
                insights = item.value
                top_issues = sorted(
                    insights.get("common_issue_types", {}).items(),
                    key=lambda item: item[1], reverse=True,
                )[:5]
                insights_text = (
                    f"\nRepo stats: {insights.get('total_reviews', 0)} total reviews. "
                    f"Top issues: {', '.join(f'{key}({value})' for key, value in top_issues)}"
                )
        except Exception:
            pass

    findings_result = await db.execute(
        text("""
            SELECT agent, severity, type, file, message
            FROM findings f
            JOIN reviews r ON r.id = f.review_id
            WHERE r.repo_id = :repo_id
            ORDER BY f.created_at DESC
            LIMIT 30
        """),
        {"repo_id": repo_id},
    )
    findings_rows = findings_result.fetchall()
    findings_text = "\n".join(
        f"[{row.severity.upper()}] {row.agent}: {row.message}" for row in findings_rows
    ) if findings_rows else "No findings yet."

    model = get_model(temperature=0.3)
    messages = [SystemMessage(content=SYSTEM_PROMPT + insights_text)]
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        else:
            messages.append(AIMessage(content=msg.content))

    messages.append(HumanMessage(
        content=f"Recent findings:\n{findings_text}\n\nUser question: {user_message}"
    ))

    db.add(ConversationMessage(id=uuid.uuid4(), conv_id=conv.id, role="user", content=user_message))
    await db.commit()
    chunks: list[str] = []
    finished=False
    try:
        async for chunk in model.astream(messages):
            text_chunk = _chunk_to_text(chunk)
            if text_chunk:
                chunks.append(text_chunk)
                yield text_chunk
        finished=True
    finally:
        import asyncio
        from src.db.base import AsyncSessionLocal
        async def persist_response():
            reply="".join(chunks)
            if not finished: reply += "\n\n[Response stopped. You can retry your question.]"
            async with AsyncSessionLocal() as save_db:
                save_db.add(ConversationMessage(id=uuid.uuid4(), conv_id=conv.id, role="assistant", content=reply))
                await save_db.commit()
        await asyncio.shield(persist_response())



def _chunk_to_text(chunk) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") for item in content if isinstance(item, dict)
        )
    return ""
