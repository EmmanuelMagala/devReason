"""Allowlisted measurements: never accept code, credentials, or arbitrary strings."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from fastapi import APIRouter, Depends
import structlog
import hashlib
from src.api.deps import get_current_user
from src.core.settings import settings

router=APIRouter()


class Measurement(BaseModel):
    model_config=ConfigDict(extra='forbid')
    event: Literal['connection_completed','review_opened','review_reconnected','navigation_loaded']
    duration_ms: int | None=Field(default=None,ge=0,le=3600000)


@router.post('',status_code=202)
async def record(body: Measurement,user=Depends(get_current_user)):
    actor=hashlib.sha256((settings.encryption_key+user['clerk_user_id']).encode()).hexdigest()[:16]
    payload=body.model_dump(exclude_none=True)
    payload['measurement']=payload.pop('event')
    structlog.get_logger().info('product_measurement',actor=actor,**payload)
    return {'accepted':True}
