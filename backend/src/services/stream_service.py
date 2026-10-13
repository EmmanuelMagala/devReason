import json
from src.schemas.stream import StreamEvent

TERMINAL={'completed','partial','failed','cancelled'}


async def push_event(redis, review_id, event: StreamEvent):
    try:
        key=f'review:{review_id}:events:v2'
        await redis.xadd(key,{'payload':event.model_dump_json()},maxlen=20000,approximate=True)
        await redis.expire(key,86400)
    except Exception:
        # The database is authoritative. HTTP clients can recover by polling.
        return None


async def set_status(redis, review_id, status):
    try: await redis.set(f'review:{review_id}:status',status,ex=86400)
    except Exception: pass


async def get_status(redis, review_id):
    try:
        value=await redis.get(f'review:{review_id}:status')
        return value.decode() if isinstance(value,bytes) else value
    except Exception: return None


async def read_events(redis, review_id, cursor='0-0'):
    groups=await redis.xread({f'review:{review_id}:events:v2':cursor},count=100,block=2000)
    events=[]
    for _, entries in groups:
        for event_id,fields in entries:
            event_id=event_id.decode() if isinstance(event_id,bytes) else event_id
            payload=fields.get(b'payload',fields.get('payload'))
            payload=payload.decode() if isinstance(payload,bytes) else payload
            events.append((event_id,payload))
    return events
