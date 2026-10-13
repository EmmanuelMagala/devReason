
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000, pattern=r'\S')


class ChatResponse(BaseModel):
    message: str
    role: str = "assistant"
