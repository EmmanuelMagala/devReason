
from langchain_openai import OpenAIEmbeddings
from src.core.settings import settings


def get_embedder() -> OpenAIEmbeddings:
    """
    Returns the embeddings model used for:
    - Storing architecture rules in pgvector
    - Searching architecture rules by semantic similarity
    Dimension: 1536 (matches arch_rules.embedding column definition)
    """
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        dimensions=settings.openai_embedding_dimensions,
        api_key=settings.openai_api_key,
    )
