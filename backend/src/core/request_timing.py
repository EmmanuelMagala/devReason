"""Expose request processing time without recording query strings or content."""
from time import perf_counter
import structlog

log = structlog.get_logger()


class RequestTimingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        start = perf_counter()

        async def timed_send(message):
            if message['type'] == 'http.response.start':
                duration = (perf_counter()-start)*1000
                message['headers'] = list(message.get('headers', [])) + [(b'server-timing', f'app;dur={duration:.1f}'.encode())]
                if duration > 1000:
                    route = getattr(scope.get('route'), 'path', 'unmatched')
                    log.info('slow_request', route=route, method=scope['method'], status=message['status'], duration_ms=round(duration))
            await send(message)

        await self.app(scope, receive, timed_send)
