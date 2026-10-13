
from langchain_openai import ChatOpenAI
from src.core.settings import settings


def get_model(temperature: float = 0.1) -> ChatOpenAI:
    """
    Returns the configured LLM.
    temperature=0.1 keeps analysis deterministic and structured.
    temperature=0.3 for the report writer to allow some natural language variation.
    """
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=temperature,
        api_key=settings.openai_api_key,
        streaming=True,
    )