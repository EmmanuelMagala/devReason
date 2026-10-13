
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.embeddings import get_embedder
from src.db.models import ArchRule
from sqlalchemy import text
import uuid
from src.core.settings import settings

log = structlog.get_logger()


async def embed_and_store_rule(
    db: AsyncSession,
    repo_id: str,
    content: str,
    *,
    status: str = "approved",
    source: str = "manual",
    commit: bool = True,
) -> ArchRule:
    """
    Embeds the rule content with text-embedding-3-small and stores it in pgvector.
    Called when a user adds a new architecture rule via the UI.
    """
    embedder = get_embedder()
    embedding = await embedder.aembed_query(content)

    if len(embedding) != settings.openai_embedding_dimensions:
        raise ValueError('Embedding dimensions do not match the configured database vector size')
    rule = ArchRule(id=uuid.uuid4(), repo_id=uuid.UUID(str(repo_id)), content=content.strip(), status=status, source=source)
    vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
    try:
        db.add(rule)
        await db.flush()
        await db.execute(text("UPDATE arch_rules SET embedding = CAST(:emb AS vector) WHERE id = :id"), {"emb": vector_str, "id": str(rule.id)})
        if commit: await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(rule)
    log.info("Architecture rule embedded and stored", repo_id=repo_id)
    return rule
