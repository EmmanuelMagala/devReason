
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.embeddings import get_embedder

log = structlog.get_logger()


def _rewrite_vector_search_error(error: Exception) -> RuntimeError:
    message = str(error)
    lowered = message.lower()
    if "column \"status\" does not exist" in lowered or "undefinedcolumnerror" in lowered:
        return RuntimeError(
            "arch_rules.status is missing in the database schema; run `alembic upgrade head` before running architecture reviews"
        )
    return RuntimeError(message)


async def search_arch_rules(
    db: AsyncSession,
    repo_id: str,
    query: str,
    limit: int = 10,
) -> list[str]:
    """
    Finds the most relevant architecture rules for the current diff.
    Uses pgvector cosine similarity on the query embedding.
    Returns a list of rule content strings (not model objects).
    """
    try:
        approved=await db.execute(text("SELECT content, embedding IS NOT NULL AS indexed FROM arch_rules WHERE repo_id=:repo_id AND status='approved' ORDER BY created_at"),{'repo_id':repo_id})
        rows=approved.fetchall()
        if not rows: return []
        if len(rows)>limit: raise RuntimeError('Too many approved rules for this review; reduce the active rule set')
        legacy=[row[0] for row in rows if not row[1]]
        if len(legacy)==len(rows): return legacy
        embedder = get_embedder()
        query_embedding = await embedder.aembed_query(query)

        # Format as PostgreSQL vector literal
        vector_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        sql = text("""
            SELECT content
            FROM arch_rules
            WHERE repo_id = :repo_id
                            AND status = 'approved'
              AND embedding IS NOT NULL
                        ORDER BY embedding <-> CAST(:embedding AS vector)
            LIMIT :limit
        """)

        result = await db.execute(
            sql,
            {"repo_id": repo_id, "embedding": vector_str, "limit": limit},
        )
        rules = [row[0] for row in result.fetchall()]+legacy
        log.info("Architecture rules retrieved", repo_id=repo_id, count=len(rules))
        return rules

    except Exception as e:
        rewritten = _rewrite_vector_search_error(e)
        log.error("Vector search failed", repo_id=repo_id, error=str(rewritten))
        raise rewritten from e
