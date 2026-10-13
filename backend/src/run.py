"""Cross-platform API launcher: python -m src.run."""
import asyncio
import os
import sys
import uvicorn


def main():
    # OAuth callback query strings contain one-use codes; omit raw access logs.
    server = uvicorn.Server(uvicorn.Config('src.main:app', host='127.0.0.1', port=int(os.getenv('PORT', '8000')), access_log=False))
    factory = asyncio.SelectorEventLoop if sys.platform == 'win32' else asyncio.new_event_loop
    asyncio.run(server.serve(), loop_factory=factory)


if __name__ == '__main__':
    main()
