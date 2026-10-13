"""Bounded GitHub SDK requests with explicit pagination and no token logging."""
from contextlib import AsyncExitStack
from contextvars import ContextVar
from functools import wraps
from githubkit import GitHub
from fastapi import HTTPException

_scope = ContextVar('github_request_scope', default=None)


def pooled_requests(operation):
    """Reuse one client per token within an operation, never between accounts."""
    @wraps(operation)
    async def wrapped(*args, **kwargs):
        if _scope.get() is not None:
            return await operation(*args, **kwargs)
        async with AsyncExitStack() as stack:
            reset = _scope.set((stack, {}))
            try:
                return await operation(*args, **kwargs)
            finally:
                _scope.reset(reset)
    return wrapped


async def request(token: str, method: str, path: str, *, params=None, json=None):
    try:
        # SDK defaults allow unbounded requests and rate-limit sleeps. Return an
        # actionable error to the user; durable jobs own recovery instead.
        scope = _scope.get()
        if scope is not None:
            stack, clients = scope
            client = clients.get(token)
            if client is None:
                client = await stack.enter_async_context(GitHub(token, timeout=15, auto_retry=False, http_cache=False))
                clients[token] = client
            response = await client.arequest(method, path, params=params, json=json)
            return response.json()
        async with GitHub(token, timeout=15, auto_retry=False, http_cache=False) as client:
            response = await client.arequest(method, path, params=params, json=json)
            return response.json()
    except Exception as error:
        status = getattr(getattr(error, 'response', None), 'status_code', None) or getattr(error, 'status_code', None)
        headers=getattr(getattr(error,'response',None),'headers',{})
        if status==429 or (status==403 and (headers.get('x-ratelimit-remaining')=='0' or headers.get('retry-after'))):
            raise HTTPException(429,'GitHub rate limit reached. Please retry shortly.') from None
        if status in (401,403): raise HTTPException(409, 'GitHub access expired or requires organization approval. Reconnect GitHub.') from None
        if status == 404: raise HTTPException(404, 'GitHub repository or target is unavailable.') from None
        raise HTTPException(502, 'GitHub is temporarily unavailable. Please try again.') from None


@pooled_requests
async def paginate(token: str, path: str, *, collection=None, params=None, max_pages=1000, allow_limit=False):
    items = []
    for page in range(1, max_pages+1):
        payload = await request(token,'GET',path,params={**(params or {}),'per_page':100,'page':page})
        batch = payload.get(collection,[]) if collection else payload
        items.extend(batch)
        if len(batch) < 100: return items
    if allow_limit: return items
    raise HTTPException(422,'GitHub listing exceeds the supported page limit; narrow the selection.')
